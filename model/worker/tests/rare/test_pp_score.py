"""P06a: filter PP confidence before conversion and merging."""

from dataclasses import replace

import numpy as np
import pandas as pd
import pytest
import yaml

from c4.config import CONFIG_DIR
from c4.rare import candidates
from c4.rare.config import load_candidate_cfg, load_rare_def


def test_pp_score_boundary_before_conversion():
    cfg, _ = load_candidate_cfg()
    # Rejected box has unusable coordinates: it must never reach conversion.
    preds = dict(boxes=np.array([["bad"] * 7, [6, 0, 1, 4, 2, 2, 0]], dtype=object),
                 labels=np.array([1, 1]), scores=np.array([0.29, 0.30]))
    boxes = candidates.pp_candidates(preds, candidates.load_class_map(),
                                     pp_min_score=cfg.pp_min_score)
    assert len(boxes) == 1
    assert boxes[0]["object_id"] == "p001"
    assert boxes[0]["pp_score"] == 0.30


def test_missing_pp_min_score_is_error(tmp_path):
    raw = yaml.safe_load((CONFIG_DIR / "candidates_v1.yaml").read_text(encoding="utf-8"))
    raw.pop("pp_min_score", None)
    path = tmp_path / "missing.yaml"
    path.write_text(yaml.safe_dump(raw), encoding="utf-8")
    with pytest.raises(ValueError, match="pp_min_score"):
        load_candidate_cfg(path)


def test_build_uses_configured_pp_min_score(tmp_path, monkeypatch):
    cfg, _ = load_rare_def()
    cand = replace(load_candidate_cfg()[0], pp_min_score=0.7)
    index = pd.DataFrame([dict(sample_token="sample", scene_token="scene", lidar_path="unused",
                               ego_x=0.0, ego_y=0.0, ego_yaw=0.0, timestamp=0)])
    monkeypatch.setattr(candidates, "read_table", lambda *a: index)
    monkeypatch.setattr(candidates, "load_filter", lambda *a: np.array([True]))
    monkeypatch.setattr(candidates, "_cluster_job", lambda *a: [])
    (tmp_path / "t1").mkdir()
    (tmp_path / "t1" / "preds_orig.pkl").touch()
    preds = dict(boxes=np.array([[6, 0, 1, 4, 2, 2, 0], [10, 0, 1, 4, 2, 2, 0]]),
                 labels=np.array([1, 1]), scores=np.array([0.69, 0.7]))
    monkeypatch.setattr(candidates, "load_preds", lambda *a: [preds])
    original_merge = candidates.merge_candidates

    def check_merge(t0, t1, *args, **kwargs):
        assert [b["pp_score"] for b in t1] == [0.7]
        return original_merge(t0, t1, *args, **kwargs)

    monkeypatch.setattr(candidates, "merge_candidates", check_merge)
    result = candidates.build_candidates(tmp_path, tmp_path, {}, cfg, candidates.load_class_map(),
                                         cand_cfg=cand)
    assert len(result) == 1
    assert result.iloc[0].cx == 10


def test_rare_def_v24_unchanged_since_freeze():
    """rare_def_v24.yaml đã freeze cùng benchmark T (Đ10): giữ nguyên byte bản base (so dạng LF)."""
    import hashlib
    raw = (CONFIG_DIR / "rare_def_v24.yaml").read_bytes().replace(b"\r\n", b"\n")
    assert hashlib.sha256(raw).hexdigest().startswith("7fda4aac1bf3fe99")
