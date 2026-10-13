"""M1 · GT RHCIO (planning/11 TESTING §0 — chế độ pitching: đường chính + một ca lỗi + chống rò nhãn)."""
import ast
from pathlib import Path

import pytest

from c4.data.nusc import NuscTables
from c4.rare.config import load_rare_def
from c4.rare.gt_rhcio import (RareDefNotFrozen, fit_reference, frame_context, label_gt,
                              load_boxes)
from tests.fixtures.make_nuscenes import make_nuscenes

C4 = Path(__file__).resolve().parents[2] / "c4"


def _tables(tmp_path):
    root = make_nuscenes(tmp_path, n_scenes=2, frames_per_scene=6, rare_frames={
        (0, 1): [("human.pedestrian.adult", (6.0, 1.0, 0.0), 40)],
        (0, 2): [("human.pedestrian.adult", (8.0, 1.0, 0.0), 30)],
        (1, 3): [("human.pedestrian.child", (5.0, 0.0, 0.0), 20)]})
    return NuscTables.load(root)


def test_fit_on_V_then_label_pool_marks_unseen_as_unknown(tmp_path):
    t = _tables(tmp_path)
    cfg, _ = load_rare_def()
    scene_of = {tok: t.scene[s["scene_token"]]["name"] for tok, s in t.sample.items()}
    v = sorted(tok for tok, sc in scene_of.items() if sc.endswith("0"))
    ref = fit_reference(load_boxes(t, v), frame_context(t, v), cfg)
    frame, inst = label_gt(t, sorted(t.sample), ref, cfg)
    assert len(frame) == len(t.sample)
    child = [tok for tok in t.sample if any(b["cls"] == "human.pedestrian.child"
                                            for b in load_boxes(t, [tok])[tok])]
    assert child and frame.set_index("sample_token").loc[child, "unknown"].all()
    assert (frame["is_target"] == frame["r2_combo"]).all()
    assert set(inst["vru_group"]) <= {"pedestrian", "bicycle", "motorcycle"}


def test_label_without_reference_raises(tmp_path):
    t = _tables(tmp_path)
    cfg, _ = load_rare_def()
    with pytest.raises(RareDefNotFrozen):
        label_gt(t, sorted(t.sample), None, cfg)


def test_only_gt_module_reads_labels():
    """Bất biến A1/B2: trong c4/rare và c4/context chỉ gt_rhcio.py đọc annotation/description."""
    forbidden = ["sample_annotation", "description", "attribute_tokens", "num_lidar_pts"]
    allowed = {"gt_rhcio.py", "eval.py"}
    for d in ("rare", "context"):
        for p in (C4 / d).glob("*.py"):
            if p.name in allowed:
                continue
            src = p.read_text(encoding="utf-8")
            code = "\n".join(ln for ln in src.splitlines() if not ln.lstrip().startswith("#"))
            code = code.replace(ast.get_docstring(ast.parse(src)) or "", "")
            hits = [s for s in forbidden if s in code]
            assert not hits, f"{p.name} chứa {hits}"
