import math

import numpy as np
import pandas as pd

from c4.analysis.overview import analyze, duplicate_groups
from c4.config import load_config
from c4.params import SelectParams, resolve


def ang(deg):
    t = math.radians(deg)
    return [math.cos(t), math.sin(t), 0.0]


def test_duplicate_groups_union_find():
    th = math.degrees(math.acos(0.97))
    Z = np.array([ang(0), ang(th), ang(2 * th), [0, 0, 1]], np.float32)
    g = duplicate_groups(Z, theta=0.95)
    assert g[0] == g[1] == g[2] != g[3]


def build(n=5):
    toks = [f"f{i}" for i in range(n)]
    fs = pd.DataFrame(dict(
        sample_token=toks, scene_token=["s0", "s0", "s1", "s1", "s2"][:n],
        best_cam="CAM_FRONT", emb_row_best=np.arange(n), frame_emb_row=np.arange(n),
        r_nov=[0.1, 0.2, 0.9, 0.5, 0.0], r_unc=[0.1, 0.9, 0.85, 0.15, 0.0],
        r_qry=[0.2, 0.3, 0.95, 0.9, 0.0], qry_best="night_rain",
        S_hybrid=[0.1, 0.4, 0.9, 0.5, 0.0], det_n_conf_best=[1, 1, 2, 0, 0],
        q_ok=[True, True, True, True, False]))
    feat = pd.DataFrame(dict(
        sample_token=toks, cam="CAM_FRONT", emb_row=np.arange(n),
        q_bright=[120.0, 120, 120, 120, 3], q_blur=80.0, det_n=[3, 3, 3, 3, 0]))
    Z = np.eye(n, dtype=np.float32)
    Z[1] = Z[0]  # f1 trùng f0
    sel = pd.DataFrame(dict(rank=[1, 2, 3], sample_token=["f2", "f0", "f1"],
                            S=[0.9, 0.1, 0.4], reason=["novelty p90 · query night_rain p95",
                                                         "điểm tổng hợp cao", "uncertainty p90"]))
    return fs, feat, Z, sel


def run(gt=None, budget_B=3, **kw):
    fs, feat, Z, sel = build()
    r = resolve(SelectParams(), load_config())
    return analyze(fs, feat, Z, sel, budget_B, gt, r, load_config(), **kw)


def test_too_safe_and_easy_counts():
    out = run()["pool"]
    assert out["tooSafe"]["count"] == 2  # f0, f1 (f4 không hợp lệ nên không tính)
    assert out["easy"]["count"] == 1  # f0 (f3 không có detection chắc chắn)
    assert out["tooSafe"]["pct"] == 0.4


def test_unlabelable_reasons():
    fs, feat, Z, sel = build()
    fs.loc[[0, 1], "q_ok"] = False
    feat.loc[0, "q_bright"] = 2.0  # f0 quá tối
    feat.loc[1, "q_blur"] = 5.0  # f1 mờ
    feat.loc[4, "q_bright"] = 120.0  # f4 đủ sáng nhưng không có vật thể (det_n = 0)
    r = resolve(SelectParams(), load_config())
    u = analyze(fs, feat, Z, sel, 3, None, r, load_config())["pool"]["unlabelable"]
    assert (u["total"]["count"], u["dark"], u["blurry"], u["noObjects"]) == (3, 1, 1, 1)


def test_histogram_sums_to_frames():
    h = run()["histogram"]
    assert len(h["bins"]) == 21 and sum(h["counts"]) == 5
    assert h["budgetThreshold"] == 0.4


def test_tags_and_selected_stats():
    out = run()
    tags = out["tags"]
    assert tags["f2"] == ["Hiếm", "Khó", "Kịch bản: night_rain"]
    assert "Trùng với #2" in tags["f1"]
    s = out["selected"]
    assert s["scenesCovered"] == 2 and s["duplicatesInSelection"] == 1
    assert s["reasons"] == {"novelty": 1, "uncertainty": 1, "query": 0, "other": 1}
    assert out["pool"]["duplicates"] == {"frames": {"count": 1, "pct": 0.2}, "groups": 1}


def test_analyze_without_gt():
    assert run()["pool"]["rareGt"] is None


def test_analyze_with_gt():
    gt = pd.DataFrame(dict(sample_token=[f"f{i}" for i in range(5)],
                           is_rare=[False, False, True, True, False],
                           A_night=[False, False, True, False, False], A_rain=False,
                           B_rare_class=[False, False, False, True, False], C_crowd=False,
                           C_low_vis=False, C_far=False))
    out = run(gt=gt)
    assert out["pool"]["rareGt"] == {
        "total": {"count": 2, "pct": 0.4}, "A": {"count": 1, "pct": 0.2},
        "B": {"count": 1, "pct": 0.2}, "C": {"count": 0, "pct": 0.0}}
    assert "Rare GT: A_night" in out["tags"]["f2"]


def test_counts_only_eligible_frames():
    fs, feat, Z, sel = build()
    fs["q_ok"] = False
    fs[["r_nov", "r_unc", "r_qry", "S_hybrid"]] = 0.0
    r = resolve(SelectParams(), load_config())
    pool = analyze(fs, feat, Z, sel, 3, None, r, load_config())["pool"]
    assert pool["tooSafe"]["count"] == pool["easy"]["count"] == pool["highValue"]["count"] == 0


def test_camera_filter_is_not_unlabelable():
    fs, feat, Z, sel = build()
    fs.loc[[0, 1], "q_ok"] = False  # f0, f1 có ảnh tốt nhưng bị lọc camera
    feat_ok = feat.assign(q_ok=[True, True, True, True, False])
    r = resolve(SelectParams(), load_config())
    pool = analyze(fs, feat_ok, Z, sel, 3, None, r, load_config())["pool"]
    u = pool["unlabelable"]
    assert u["total"]["count"] == 1 and u["dark"] + u["blurry"] + u["noObjects"] == 1
    assert pool["excludedByCamera"]["count"] == 2


def test_tags_cover_every_selected_row_beyond_budget_b():
    out = run(budget_B=1)  # chọn 3 dòng, ngân sách chỉ 1: slider 8 % vẫn cần tag cho cả 3
    assert set(out["tags"]) == {"f2", "f0", "f1"}
    assert "Trùng với #2" in out["tags"]["f1"]
    assert out["selected"]["duplicatesInSelection"] == 0  # thống kê vẫn tính trong ngân sách
    assert out["selected"]["reasons"]["novelty"] == 1
