"""P01: sensor-to-ego PP boxes and exclusion before merging/tracking."""

import math

import numpy as np
import pandas as pd
import pytest
import yaml

from c4.config import CONFIG_DIR
from c4.data.geometry import quat_to_mat
from c4.rare import candidates
from c4.rare.config import load_candidate_cfg, load_rare_def

# nuScenes-mini sample ca9a282c9e77460f8360f564131a8af5,
# calibrated_sensor a183049901c24361a6b0b11b8013137c (LIDAR_TOP).
ROTATION = [0.7077955119163518, -0.006492242056004365,
            0.010646214713995808, -0.7063073142877817]
TRANSLATION = [0.943713, 0.0, 1.84023]


def test_pp_real_mini_calibration():
    R = quat_to_mat(ROTATION)
    t = np.array(TRANSLATION)
    center_ego = np.array([10.0, 2.0, 0.9])
    center_sensor = R.T @ (center_ego - t)
    preds = dict(boxes=np.array([[*center_sensor, 4.0, 2.0, 1.8, -2.8]]),
                 labels=np.array([1]), scores=np.array([0.9]))
    box = candidates.pp_candidates(preds, candidates.load_class_map(),
                                   lidar_calib={"R": R.reshape(-1).tolist(), "t": t.tolist()})[0]
    np.testing.assert_allclose([box[k] for k in ("cx", "cy", "cz")], center_ego, atol=1e-9)
    assert -0.6 <= box["cz"] - box["h"] / 2 <= 0.6
    assert [box[k] for k in ("l", "w", "h")] == [4.0, 2.0, 1.8]
    expected = -2.8 + math.atan2(R[1, 0], R[0, 0])
    assert box["yaw"] == pytest.approx(math.atan2(math.sin(expected), math.cos(expected)))
    assert box["dist_m"] == pytest.approx(math.hypot(10, 2))


@pytest.mark.parametrize("source", ["cluster", "pointpillars"])
def test_build_filters_ego_before_merge(tmp_path, monkeypatch, source):
    index = pd.DataFrame([dict(sample_token="sample", scene_token="scene", lidar_path="unused",
                               ego_x=0.0, ego_y=0.0, ego_yaw=0.0, timestamp=0)])
    monkeypatch.setattr(candidates, "read_table", lambda *a: index)
    monkeypatch.setattr(candidates, "load_filter", lambda *a: np.array([True]))
    class_map = candidates.load_class_map()
    # Include all rectangle edges, outside-y near ego, and the requested near/far examples.
    centers = [(0.5, 0), (-1.5, 0), (3.5, 0), (0, -1.2), (0, 1.2), (6, 0), (0, 1.21)]
    preds = dict(boxes=np.array([[x, y, 1, 0.5, 0.5, 1, 0] for x, y in centers]),
                 labels=np.ones(len(centers), dtype=int), scores=np.ones(len(centers)))
    boxes = candidates.pp_candidates(preds, class_map)
    for box in boxes:
        box.update(source=source, pts=10)
    monkeypatch.setattr(candidates, "_cluster_job", lambda *a: boxes if source == "cluster" else [])
    if source == "pointpillars":
        (tmp_path / "t1").mkdir()
        (tmp_path / "t1" / "preds_orig.pkl").touch()
        monkeypatch.setattr(candidates, "load_preds", lambda *a: [preds])
    original_merge = candidates.merge_candidates

    def check_merge(t0, t1, *args, **kwargs):
        incoming = t0 + t1
        assert [(b["cx"], b["cy"]) for b in incoming] == [(6, 0), (0, 1.21)]
        return original_merge(t0, t1, *args, **kwargs)

    monkeypatch.setattr(candidates, "merge_candidates", check_merge)
    cfg, _ = load_rare_def()
    result = candidates.build_candidates(tmp_path, tmp_path, {}, cfg, class_map)
    assert len(result) == 2


def test_missing_ego_exclusion_is_error(tmp_path):
    raw = yaml.safe_load((CONFIG_DIR / "candidates_v1.yaml").read_text(encoding="utf-8"))
    raw.pop("ego_exclusion", None)
    path = tmp_path / "missing.yaml"
    path.write_text(yaml.safe_dump(raw), encoding="utf-8")
    with pytest.raises(ValueError, match="ego_exclusion"):
        load_candidate_cfg(path)
