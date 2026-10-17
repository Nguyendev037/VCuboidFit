"""Adapter acceptance cases. Written for H03; execution requires separate authorization."""
import json
import math

import numpy as np
import pandas as pd
import pytest
from PIL import Image

from c4.data.adapters import pandaset
from c4.data.adapters.common import AdapterError, box_axis_check, normalize_image, pose, sha256, validate_output, yaw_q
from c4.data.geometry import quat_to_mat
from c4.data.index import build_frames
from c4.data.nusc import NuscTables
from c4.data.project import project_boxes
from tests.fixtures.make_pandaset import POINT_COUNT, YAW_OFFSET, make_pandaset


def test_pandaset_roundtrip_projection_geometry(tmp_path):
    src = make_pandaset(tmp_path / "src")
    out = tmp_path / "out"
    report = pandaset.adapt(src, out)
    t = NuscTables.load(out)
    assert len(t.scene) == 2 and len(t.sample) == 4
    assert len(t.sample_data) == 44  # 20 LiDAR (4 key,16 sweep) + 24 cameras
    assert len(t.calibrated_sensor) == len(t.sample_data)
    assert all(sc["description"] == "" and sc["nbr_samples"] == 2 for sc in t.scene.values())
    assert all(a["visibility_token"] == "" and a["size"] == [2., 4., 1.6]
               and a["num_lidar_pts"] == POINT_COUNT for a in t.sample_annotation.values())
    assert len(t.sample_annotation) == 4 and len(t.instance) == 2
    frames = build_frames(t, out)
    b2, b3 = project_boxes(t, frames)
    assert len(b3) == 4 and len(b2) >= 4
    assert (b2.num_lidar_pts >= 5).all()
    assert (b2.x1 + b2.x2).between(0, 3200, inclusive="left").all()
    assert report["validation"]["car_length_ratio"] == 1
    assert report["validation"]["projected_near_cars"] == 4
    assert max(report["ego_axis_angles_deg"].values()) < 5
    assert report["yaw_offset"] == YAW_OFFSET
    assert all(np.isclose(d, -.2) for d in report["ego_mounting_delta"].values())
    assert not any(report["delta_borrowed"].values())
    assert all(c["eligible_boxes"] == 2 and c["aligned_ratio"] == 1
               for c in report["box_axis_checks"].values())
    assert all(len(candidates) == 4 for candidates in report["yaw_offset_stats"].values())
    for sd in t.sample_data.values():
        cal = t.calibrated_sensor[sd["calibrated_sensor_token"]]
        scene = t.scene[t.sample[sd["sample_token"]]["scene_token"]]["name"].removeprefix("pandaset-")
        times = json.loads((src / scene / "lidar/timestamps.json").read_text())
        source_poses = [pandaset.source_pose(p) for p in json.loads((src / scene / "lidar/poses.json").read_text())]
        # Independently derive expected yaw from known fixture mounting, unwrapping
        # through 180 degrees before interpolation at the +25ms camera timestamp.
        lidar_yaws = np.unwrap([math.atan2(quat_to_mat(p["rotation"])[1, 0],
                                          quat_to_mat(p["rotation"])[0, 0]) for p in source_poses])
        expected_yaw = np.interp(sd["timestamp"] / 1e6, times, lidar_yaws - .2)
        ego = t.ego_pose[sd["ego_pose_token"]]
        assert np.allclose(quat_to_mat(ego["rotation"]), quat_to_mat(yaw_q(expected_yaw)), atol=1e-6)
        if t.sensor[cal["sensor_token"]]["channel"] == "LIDAR_TOP":
            points = np.fromfile(out / sd["filename"], np.float32).reshape(-1, 5)
            assert points.shape == (POINT_COUNT, 5)
            ego_points = points[:, :3] @ quat_to_mat(cal["rotation"]).T + cal["translation"]
            world = ego_points @ quat_to_mat(ego["rotation"]).T + ego["translation"]
            index = round((sd["timestamp"] / 1e6 - times[0]) * 10)
            original = pd.read_pickle(src / scene / f"lidar/{index:02d}.pkl.gz")
            assert np.allclose(world, original.loc[original.d == 0, ["x", "y", "z"]], atol=1e-5)
    turning = [p for p in t.ego_pose.values() if p["translation"][1] > 90]
    turning_yaws = np.unwrap([math.atan2(quat_to_mat(p["rotation"])[1, 0],
                                        quat_to_mat(p["rotation"])[0, 0]) for p in turning])
    assert np.ptp(turning_yaws) >= math.radians(45)
    for a in t.sample_annotation.values():
        sample = t.sample[a["sample_token"]]
        scene = t.scene[sample["scene_token"]]["name"].removeprefix("pandaset-")
        times = json.loads((src / scene / "lidar/timestamps.json").read_text())
        index = round((sample["timestamp"] / 1e6 - times[0]) * 10)
        b = pd.read_pickle(src / scene / f"annotations/cuboids/{index:02d}.pkl.gz").iloc[0]
        assert a["size"] == [b["dimensions.x"], b["dimensions.y"], b["dimensions.z"]]
        assert np.allclose(quat_to_mat(a["rotation"]), quat_to_mat(yaw_q(b["yaw"] + YAW_OFFSET)))
    for row in pd.read_parquet(out / "media_manifest.parquet").to_dict("records"):
        with Image.open(out / row["img_path"]) as im:
            assert im.size == (1600, 900)
        assert sha256(out / row["img_path"]) == row["sha256"]
    pandaset.adapt(src, tmp_path / "again")
    for file in out.rglob("*.json"):
        assert file.read_bytes() == (tmp_path / "again" / file.relative_to(out)).read_bytes()


def test_pandaset_reject_untrusted_before_pickle(tmp_path, monkeypatch):
    src = make_pandaset(tmp_path / "src", n_sequences=1)
    path = src / "000/lidar/00.pkl.gz"
    path.write_bytes(b"untrusted")
    def forbidden(*args, **kwargs):
        raise AssertionError("pickle reader invoked before trust check")
    monkeypatch.setattr(pd, "read_pickle", forbidden)
    with pytest.raises(AdapterError, match="untrusted pickle"):
        pandaset.adapt(src, tmp_path / "out")
    assert not (tmp_path / "out").exists()


def test_pandaset_swapped_dimensions_rejected(tmp_path):
    src = make_pandaset(tmp_path / "src", n_sequences=1)
    out = tmp_path / "out"
    report = pandaset.adapt(src, out)
    path = out / "v1.0-pandaset/sample_annotation.json"
    anns = json.loads(path.read_text())
    for ann in anns:
        ann["size"][:2] = ann["size"][:2][::-1]
    path.write_text(json.dumps(anns))
    with pytest.raises(AdapterError) as error:
        validate_output(out, report)
    assert error.value.code == "PROJ_FAIL"


def test_resize_intrinsics_principal_point(tmp_path):
    src, dst = tmp_path / "in.jpg", tmp_path / "out.jpg"
    Image.new("RGB", (1920, 1080)).save(src)
    k = normalize_image(src, dst, [[1200, 0, 960], [0, 1200, 540], [0, 0, 1]])
    assert np.allclose(k, [[1000, 0, 800], [0, 1000, 450], [0, 0, 1]])


def test_pandaset_sync_low_not_published(tmp_path):
    src = make_pandaset(tmp_path / "src", n_sequences=1)
    path = src / "000/camera/front_camera/timestamps.json"
    values = json.loads(path.read_text())
    path.write_text(json.dumps([v + 100 for v in values]))
    with pytest.raises(AdapterError) as error:
        pandaset.adapt(src, tmp_path / "out")
    assert error.value.code == "SYNC_LOW"
    assert not (tmp_path / "out").exists()


def test_pandaset_fixed_yaw_mutation_rejected(tmp_path, monkeypatch):
    src = make_pandaset(tmp_path / "src")  # includes 60-degree turn
    original = pandaset.sequence_egos
    def fixed_yaw(times, poses, previous_delta):
        egos, delta, borrowed = original(times, poses, previous_delta)
        return [pose(e["translation"], egos[0]["rotation"]) for e in egos], delta, borrowed
    monkeypatch.setattr(pandaset, "sequence_egos", fixed_yaw)
    with pytest.raises(AdapterError) as error:
        pandaset.adapt(src, tmp_path / "out")
    assert error.value.code == "EGO_AXIS" and error.value.exit_code == 3
    assert not (tmp_path / "out").exists()


def test_stationary_delta_borrowing_and_missing_predecessor():
    times = [0., .1, .2]
    poses = [pose([0, 0, 0], yaw_q(.7)) for _ in times]
    egos, delta, borrowed = pandaset.sequence_egos(times, poses, -.2)
    assert borrowed and delta == -.2
    assert pandaset.check_ego_axes(times, poses, egos) is None
    assert np.allclose(quat_to_mat(egos[0]["rotation"]), quat_to_mat(yaw_q(.5)))
    with pytest.raises(AdapterError) as error:
        pandaset.sequence_egos(times, poses, None)
    assert error.value.code == "EGO_AXIS"


def test_yaw_family_requires_evidence_and_consistency(tmp_path, monkeypatch):
    src = make_pandaset(tmp_path / "src")
    original = pandaset.measure_yaw_offset
    def inconsistent(seq, *args):
        offset, stats, check = original(seq, *args)
        return (0. if seq.name == "001" else offset), stats, check
    monkeypatch.setattr(pandaset, "measure_yaw_offset", inconsistent)
    with pytest.raises(AdapterError) as error:
        pandaset.adapt(src, tmp_path / "out")
    assert error.value.code == "PROJ_FAIL"
    assert not (tmp_path / "out").exists()


def test_yaw_measurement_without_dense_cars_fails(tmp_path, monkeypatch):
    src = make_pandaset(tmp_path / "src", n_sequences=1)
    monkeypatch.setattr(pandaset, "box_axis_angles", lambda *args: [])
    with pytest.raises(AdapterError) as error:
        pandaset.adapt(src, tmp_path / "out")
    assert error.value.code == "PROJ_FAIL"
    assert not (tmp_path / "out").exists()


@pytest.mark.parametrize("yaw,size", [(math.pi / 2, [2., 4., 1.6]), (0., [4., 2., 1.6])])
def test_box_axis_rejects_yaw_and_dimension_mutations(yaw, size):
    points = np.array([(x, y, z) for x in np.linspace(-1.6, 1.6, 9)
                       for y in np.linspace(-.6, .6, 5) for z in [-.3, 0., .3]])
    with pytest.raises(AdapterError) as error:
        box_axis_check(points, [dict(**pose([0, 0, 0], yaw_q(yaw)), size=size, category="vehicle.car")])
    assert error.value.code == "PROJ_FAIL" and error.value.exit_code == 3


def test_box_axis_pools_frames_at_eighty_percent():
    points = np.array([(x, y, z) for x in np.linspace(-1.6, 1.6, 9)
                       for y in np.linspace(-.6, .6, 5) for z in [-.3, 0., .3]])
    good = dict(**pose([0, 0, 0], yaw_q(0)), size=[2., 4., 1.6], category="vehicle.car")
    bad = dict(good, rotation=yaw_q(math.pi / 2))
    result = box_axis_check([points] * 5, [[good]] * 4 + [[bad]])
    assert result["eligible_boxes"] == 5 and result["aligned_ratio"] == .8
    with pytest.raises(AdapterError) as error:
        box_axis_check([points] * 5, [[good]] * 3 + [[bad]] * 2)
    assert error.value.code == "PROJ_FAIL"


def test_yaw_measurement_ambiguous_axis_families_fail(tmp_path, monkeypatch):
    src = make_pandaset(tmp_path / "src", n_sequences=1)
    monkeypatch.setattr(pandaset, "box_axis_angles", lambda *args: [0.])
    with pytest.raises(AdapterError) as error:
        pandaset.adapt(src, tmp_path / "out")
    assert error.value.code == "PROJ_FAIL"
    assert not (tmp_path / "out").exists()
