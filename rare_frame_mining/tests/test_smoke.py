"""Smoke tests — chạy: python tests/test_smoke.py (không cần pytest)."""
import math
import os
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import numpy as np

from rare_mining.utils import bev_iou, rank_pct, wilson_ci, average_precision, Mahalanobis
from rare_mining.weather import parse_desc, lidar_rain_proxy, rain_score_combine
from rare_mining.m6_evaluate import gt_rare_object, gt_frame_flags
from rare_mining.data import GTBox


def test_bev_iou():
    a = (0, 0, 4, 2, 0.0)
    assert abs(bev_iou(a, a) - 1.0) < 1e-6, "IoU của box với chính nó phải = 1"
    assert bev_iou(a, (100, 100, 4, 2, 0.0)) == 0.0, "box rời nhau → IoU 0"
    assert abs(bev_iou(a, (0, 0, 4, 2, math.pi)) - 1.0) < 1e-6, "quay 180° vẫn là box đó"
    half = bev_iou(a, (1, 0, 4, 2, 0.0))
    assert 0.4 < half < 0.9, f"IoU dịch 1m phải trong (0.4, 0.9): {half}"
    print("  test_bev_iou OK")


def test_rank_pct():
    r = rank_pct([0.1, 0.5, 0.9, 0.5])
    assert r[2] == 1.0 and r[0] == 0.25, f"rank sai: {r}"
    assert abs(r[1] - r[3]) < 1e-9 and abs(r[1] - 0.625) < 1e-9, "phần tử bằng nhau nhận rank trung bình"
    print("  test_rank_pct OK")


def test_stats():
    lo, hi = wilson_ci(8, 10)  # Wilson 8/10: (≈0.490, ≈0.943) — khớp tính tay
    assert 0.44 < lo < 0.56 and 0.90 < hi < 0.96 and lo < 0.8 < hi, f"wilson sai: {(lo, hi)}"
    assert abs(average_precision([1, 0, 1, 1]) - (1 + 2 / 3 + 3 / 4) / 3) < 1e-9
    X = np.random.default_rng(0).normal(size=(50, 3))
    m = Mahalanobis().fit(X)
    s = m.score(X)
    assert s.min() >= 0 and np.isfinite(s).all()
    print("  test_stats OK")


def test_weather():
    w = parse_desc("Night, after rain.")
    assert w["night"] and w["rain"]
    w2 = parse_desc("Sunny daytime.")
    assert not w2["night"] and not w2["rain"]
    # point cloud sạch: ground + vài vật → proxy ~0
    rng = np.random.default_rng(0)
    pts = np.column_stack([
        rng.uniform(-40, 40, 3000), rng.uniform(-40, 40, 3000),
        rng.uniform(-0.5, 0.2, 3000), rng.uniform(0.2, 0.6, 3000)])
    assert lidar_rain_proxy(pts) == 0.0
    assert rain_score_combine(True, 0.3) > rain_score_combine(False, 0.3)
    print("  test_weather OK")


def test_gt_rule():
    cfg_like = type("O", (), {"far_m": 30.0, "few_points": 10})()
    bike_far = GTBox((40, 0, 0.8), (1.7, 0.6, 1.5), 0.0, "bicycle", num_lidar_pts=50)
    ped_close = GTBox((5, 2, 0.9), (0.5, 0.5, 1.7), 0.0, "pedestrian", num_lidar_pts=200)
    car_near = GTBox((10, -3, 0.8), (4.3, 1.9, 1.6), 0.0, "car", num_lidar_pts=600)
    ped_sparse = GTBox((10, 0, 0.9), (0.5, 0.5, 1.7), 0.0, "pedestrian", num_lidar_pts=6)
    assert gt_rare_object(bike_far, cfg_like)
    assert not gt_rare_object(ped_close, cfg_like)
    assert not gt_rare_object(car_near, cfg_like)
    assert gt_rare_object(ped_sparse, cfg_like), "<10 điểm → hiếm dù gần"
    car_far = GTBox((45, 0, 0.8), (4.3, 1.9, 1.6), 0.0, "car", num_lidar_pts=4)
    assert not gt_rare_object(car_far, cfg_like), "mặc định far/few chỉ tính VRU"
    cfg_all = type("O", (), {"far_m": 30.0, "few_points": 10, "far_few_scope": "all"})()
    assert gt_rare_object(car_far, cfg_all)
    frame = {"desc": "Night, clear.", "gt": [bike_far] + [ped_close] * 6}
    fl = gt_frame_flags(frame, cfg_like, type("F", (), {"crowd_n": 5})())
    assert fl["rare_frame"] and fl["night"] and fl["crowd"] and not fl["rain"]
    assert fl["slices"]["rare_class"] and fl["slices"]["night"]
    print("  test_gt_rule OK")


def test_end2end_tiny():
    from rare_mining import PipelineConfig, SyntheticSource, run_pipeline, evaluate
    cfg = PipelineConfig()
    cfg.tta.enabled = False
    cfg.evalcfg.budgets = (10, 20)
    cfg.split.val_frac = 0.5
    with tempfile.TemporaryDirectory() as td:
        cfg.out_dir = td
        src = SyntheticSource(n_scenes=2, frames_per_scene=6, seed=1)
        artifacts = run_pipeline(src, cfg, budget=10, verbose=False)
        for fn in ("frames_ranked_T.csv", "frames_ranked_V.csv", "objects_T.csv",
                   "summary.json", "artifacts.pkl", "config_used.json"):
            assert os.path.exists(os.path.join(td, fn)), f"thiếu {fn}"
        report = evaluate(artifacts["frames"], artifacts["cands"], cfg)
        for m in ("pipeline", "random_mean", "slices", "object_level", "lift_over_random"):
            assert m in report
        p = report["pipeline"]
        assert 0.0 <= p["P@10"] <= 1.0 and 0.0 <= p["R@10"] <= 1.0
        assert p["R@10"] >= report["random_mean"]["R@10"] - 0.35, "pipeline không được thua random quá xa"
    print("  test_end2end_tiny OK")


def test_pilot_sanity():
    from rare_mining import PipelineConfig, SyntheticSource
    from rare_mining.detectors import make_detector
    from rare_mining.m05_pilot import pick_pilot, run_sanity
    cfg = PipelineConfig()
    src = SyntheticSource(n_scenes=2, frames_per_scene=4, seed=3)
    frames = src.frames()
    det = make_detector(cfg)
    picks = pick_pilot(frames, cfg, n_random=3, n_strat=2, seed=0, max_scan=8)
    fids = picks["random"] + picks["stratified"]
    assert len(fids) >= 3, "phải chọn được ít nhất 3 frame pilot"
    rep = run_sanity(frames, fids, det, cfg)
    assert {"per_class", "schema", "decisions"} <= set(rep)
    ped = rep["per_class"].get("pedestrian")
    assert ped is not None and ped["gt"] > 0 and ped["recall"] >= 0.1, \
        f"sanity recall pedestrian phải dương: {ped}"
    print("  test_pilot_sanity OK")


def test_select_scenes():
    """Chống leak: checkpoint công khai (train trên nuScenes train) chỉ được chạy trên val."""
    from rare_mining.data import select_scenes
    splits = {"train": ["s1", "s2", "s3"], "val": ["s4", "s5"],
              "mini_train": ["s1"], "mini_val": ["s4"]}
    names = ["s1", "s2", "s3", "s4", "s5"]
    assert select_scenes(names, "v1.0-trainval", "auto", splits) == ["s4", "s5"]
    assert select_scenes(["s1", "s4"], "v1.0-mini", "auto", splits) == ["s4"]
    for bad in ("all", "train"):
        try:
            select_scenes(names, "v1.0-trainval", bad, splits)
            raise AssertionError(f"split={bad} với checkpoint công khai phải bị chặn")
        except ValueError:
            pass
    # Model Seed / ngoài: được phép dùng mọi scene (frame Seed loại qua ledger)
    assert select_scenes(names, "v1.0-trainval", "all", splits, "seed") == names
    print("  test_select_scenes OK")


def test_model_toggle():
    """Công tắc retrain + phương án B: explore=1 chỉ khi retrain bật, không trùng selected."""
    from rare_mining import PipelineConfig, SyntheticSource, run_pipeline
    for retrain in (False, True):
        cfg = PipelineConfig()
        cfg.tta.enabled = False
        cfg.split.val_frac = 0.5
        cfg.model.retrain = retrain
        cfg.model.explore_frac = 0.5
        with tempfile.TemporaryDirectory() as td:
            cfg.out_dir = td
            src = SyntheticSource(n_scenes=2, frames_per_scene=8, seed=2)
            art = run_pipeline(src, cfg, budget=4, verbose=False)
            sel = [f for f in art["ranked_T"] if f["selected"]]
            exp = [f for f in art["ranked_T"] if f.get("explore")]
            assert len(sel) <= 4
            if retrain:
                assert len(exp) == min(2, len(art["ranked_T"]) - len(sel))
                assert not ({f["fid"] for f in sel} & {f["fid"] for f in exp})
            else:
                assert not exp, "explore phải trống khi retrain tắt"
    print("  test_model_toggle OK")


def test_outlier_gate():
    """Cổng ngoại lai: lỗi dữ liệu rõ ràng (thưa điểm, NaN, điểm dưới mặt đường) không được lọt
    vào nhóm Hợp lệ; frame Ngoại lai/Nghi ngờ không bao giờ có selected=1; OOD không cộng điểm."""
    from rare_mining import PipelineConfig, SyntheticSource, run_pipeline
    from rare_mining.outlier_gate import raw_point_stats, corrupt_points
    rng = np.random.default_rng(0)
    pts = np.c_[rng.uniform(-30, 30, (5000, 2)), rng.uniform(-0.1, 0.1, 5000), rng.uniform(0, 1, 5000)]
    assert raw_point_stats(corrupt_points(pts, "nan", rng))["nonfinite_frac"] > 0
    assert raw_point_stats(corrupt_points(pts, "below", rng))["frac_below_ground"] > 0.05
    cfg = PipelineConfig()
    cfg.tta.enabled = False
    cfg.split.val_frac = 0.5
    cfg.gate.corruption_test_n = 4
    assert cfg.frame.w_ood == 0.0, "OOD mặc định chỉ là cờ"
    with tempfile.TemporaryDirectory() as td:
        cfg.out_dir = td
        art = run_pipeline(SyntheticSource(n_scenes=4, frames_per_scene=6, seed=5), cfg,
                           budget=6, verbose=False)
        assert os.path.exists(os.path.join(td, "review_T.csv"))
        for f in art["ranked_T"]:
            assert f["gate"] in ("valid", "suspect", "outlier")
            if f["gate"] != "valid":
                assert not f["selected"], "frame Nghi ngờ/Ngoại lai không được chọn"
        ct = art["gate"]["corruption_test"]
        for kind in ("sparse", "nan", "below"):
            assert ct[kind]["n"] > 0 and ct[kind]["valid"] == 0, f"lỗi '{kind}' lọt cổng: {ct[kind]}"
    print("  test_outlier_gate OK")


if __name__ == "__main__":
    print("Chạy smoke tests...")
    test_bev_iou()
    test_rank_pct()
    test_stats()
    test_weather()
    test_gt_rule()
    test_end2end_tiny()
    test_pilot_sanity()
    test_select_scenes()
    test_model_toggle()
    test_outlier_gate()
    print("TẤT CẢ SMOKE TESTS ĐẠT ✓")
