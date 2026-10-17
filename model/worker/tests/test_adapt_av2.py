"""Source-shaped AV2 fixtures, crop geometry, selection and determinism."""
import json
import math

import numpy as np
import pandas as pd
import pytest
from PIL import Image

from c4.data.adapters import av2
from c4.data.adapters.common import AdapterError, normalize_image, pose, qmul, sha256, validate_output, yaw_q
from c4.data.geometry import quat_to_mat
from c4.data.index import build_frames
from c4.data.nusc import NuscTables
from c4.data.project import project_boxes
from tests.fixtures.make_av2 import YAW, make_av2

EXPECTED = dict(CAM_FRONT="ring_front_center", CAM_FRONT_LEFT="ring_front_left",
                CAM_FRONT_RIGHT="ring_front_right", CAM_BACK_LEFT="ring_side_left",
                CAM_BACK_RIGHT="ring_side_right", CAM_BACK="ring_rear_left")


def test_camera_yaw_from_optical_axis_and_tie():
    cal = {cam: pose([0, 0, 0], qmul(yaw_q(math.radians(yaw)), [.5, -.5, .5, -.5]))
           for cam, yaw in YAW.items()}
    selected, dropped = av2.select_cameras(cal)
    assert selected == EXPECTED and dropped == ["ring_rear_right"]
    assert av2.select_cameras(dict(reversed(list(cal.items())))) == (selected, dropped)


def test_av2_roundtrip_projection_geometry(tmp_path):
    src = make_av2(tmp_path / "src")
    out = tmp_path / "out"
    report = av2.adapt(src, out)
    t = NuscTables.load(out)
    assert len(t.scene) == 2 and len(t.sample) == 4 and len(t.sample_data) == 44
    assert len(t.calibrated_sensor) == 44
    assert report["camera_assignment"] == {"log-0": EXPECTED, "log-1": EXPECTED}
    assert all(c["eligible_boxes"] == 2 and c["aligned_ratio"] == 1
               for c in report["box_axis_checks"].values())
    assert all(a["size"] == [2., 4., 1.6] and a["num_lidar_pts"] == 135
               and a["visibility_token"] == "" for a in t.sample_annotation.values())
    b2, b3 = project_boxes(t, build_frames(t, out))
    assert len(b3) == 4 and len(b2) >= 4
    assert report["validation"]["projected_near_cars"] == 4
    assert report["validation"]["projection_ratio"] == 1
    for sd in t.sample_data.values():
        cal = t.calibrated_sensor[sd["calibrated_sensor_token"]]
        if t.sensor[cal["sensor_token"]]["channel"] == "LIDAR_TOP":
            points = np.fromfile(out / sd["filename"], np.float32).reshape(-1, 5)
            assert set(points[:, 4]) == {0, 1}
            ego_points = points[:, :3] @ quat_to_mat(cal["rotation"]).T + cal["translation"]
            assert np.allclose(ego_points.mean(axis=0), [12, 0, 1], atol=1e-5)
    for row in pd.read_parquet(out / "media_manifest.parquet").to_dict("records"):
        with Image.open(out / row["img_path"]) as im:
            assert im.size == (1600, 900)
        assert sha256(out / row["img_path"]) == row["sha256"]
    av2.adapt(src, tmp_path / "again")
    for file in out.rglob("*.json"):
        assert file.read_bytes() == (tmp_path / "again" / file.relative_to(out)).read_bytes()


@pytest.mark.parametrize("size,crop", [((2048, 1550), (2048, 1152)), ((1550, 2048), (1550, 872))])
def test_av2_crop_and_intrinsic(tmp_path, size, crop):
    path = tmp_path / "in.jpg"
    Image.new("RGB", size).save(path)
    width, height = size
    k = normalize_image(path, tmp_path / "out.jpg", [[1100, 0, width/2], [0, 1100, height/2], [0, 0, 1]])
    y0 = round(height/2 - crop[1]/2)
    assert np.isclose(k[0][0], 1100 * 1600 / crop[0])
    assert np.isclose(k[1][2], (height/2 - y0) * 900 / crop[1])


def test_av2_swapped_dimensions_rejected(tmp_path):
    src = make_av2(tmp_path / "src", n_sequences=1)
    out = tmp_path / "out"
    report = av2.adapt(src, out)
    path = out / "v1.0-av2/sample_annotation.json"
    anns = json.loads(path.read_text())
    for ann in anns:
        ann["size"][:2] = ann["size"][:2][::-1]
    path.write_text(json.dumps(anns))
    with pytest.raises(AdapterError) as error:
        validate_output(out, report)
    assert error.value.code == "PROJ_FAIL"


def test_av2_sync_low_not_published(tmp_path):
    src = make_av2(tmp_path / "src", n_sequences=1)
    # Images exist but all front-center timestamps are >50 ms from every keyframe.
    camera = src / "val/log-0/sensors/cameras/ring_front_center"
    for image in list(camera.glob("*.jpg")):
        image.rename(image.with_name(f"{int(image.stem) + 10_000_000_000}.jpg"))
    with pytest.raises(AdapterError) as error:
        av2.adapt(src, tmp_path / "out")
    assert error.value.code == "SYNC_LOW"
    assert not (tmp_path / "out").exists()


def test_av2_wrong_yaw_rejected_by_shared_axis_gate(tmp_path):
    src = make_av2(tmp_path / "src", n_sequences=1)
    path = src / "val/log-0/annotations.feather"
    anns = pd.read_feather(path)
    anns["qw"], anns["qz"] = math.cos(math.pi / 4), math.sin(math.pi / 4)
    anns.to_feather(path)
    with pytest.raises(AdapterError) as error:
        av2.adapt(src, tmp_path / "out")
    assert error.value.code == "PROJ_FAIL" and error.value.exit_code == 3
    assert not (tmp_path / "out").exists()


def test_pooled_axis_tolerates_one_partial_view_sequence():
    from c4.data.adapters.common import pooled_axis_check
    weak = dict(angles_deg=[30.] * 3 + [1.] * 7, aligned_ratio=.7)
    good = dict(angles_deg=[1.] * 20, aligned_ratio=1.)
    got = pooled_axis_check({"a": weak, "b": good})
    assert got["aligned_ratio"] == pytest.approx(27 / 30) and got["sequences_below_80"] == ["a"]
    with pytest.raises(AdapterError) as error:
        pooled_axis_check({"a": weak, "b": weak})
    assert error.value.code == "PROJ_FAIL"


@pytest.mark.parametrize("yaw,fails", [(0., False), (math.pi, False), (math.pi / 2, True)])
def test_motion_heading_catches_rotated_boxes(yaw, fails):
    from c4.data.adapters.common import motion_heading_check
    tracks = pd.DataFrame(dict(uuid="t", ts_ns=[k * 500_000_000 for k in range(6)],
                               x=[2.5 * k for k in range(6)], y=0., yaw=yaw))
    if fails:
        with pytest.raises(AdapterError) as error:
            motion_heading_check(tracks)
        assert error.value.code == "PROJ_FAIL"
    else:
        assert motion_heading_check(tracks)["median_deg"] == pytest.approx(0, abs=1e-9)
    assert motion_heading_check(tracks.assign(x=0.))["n"] == 0
