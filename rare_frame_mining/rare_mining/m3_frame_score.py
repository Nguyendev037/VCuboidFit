"""M3 — Điểm FRAME: s_obj_agg + s_crowd + s_weather + s_ood.

Sửa theo phản biện:
- OOD reference fit trên V (subset 'comfort' = frame model tự tin nhất) — không chạm T.
- Thời tiết: metadata (desc) là kênh chính; mưa có cường độ liên tục từ proxy LiDAR;
  'đêm' KHÔNG bao giờ suy từ hình dạng point cloud (LiDAR chủ động, không suy giảm đêm).
- Rank-aggregation thay tổng tuyến tính.
"""
import math
from typing import List

import numpy as np

from . import features as F
from .weather import parse_desc, rain_score_combine


def frame_raw_features(frame: dict, cands: List[dict], frame_cfg) -> dict:
    """Đặc trưng thô của frame — gọi sau khi candidates đã có s_obj."""
    crowd = sum(1 for c in cands
                if (c["class_name"] == "pedestrian")
                or (F.person_like({"H": c["H"], "W": c["W"], "n_points": c["n_points"]}, frame_cfg)))
    flags_desc = parse_desc(frame.get("desc", ""))
    night = 1.0 if flags_desc["night"] else 0.0
    rain = rain_score_combine(flags_desc["rain"], frame["aux"]["rain_proxy"])
    # nếu có ảnh camera → dùng làm kênh bổ sung cho 'đêm'
    if frame.get("camera_paths"):
        from .weather import camera_brightness, night_from_brightness
        b = camera_brightness(frame["camera_paths"])
        night = max(night, night_from_brightness(b))

    s_obj_vals = [c["s_obj"] for c in cands] or [0.0]
    s_obj_vals_sorted = sorted(s_obj_vals, reverse=True)
    topk = s_obj_vals_sorted[: frame_cfg.topk]
    obj_agg = 0.5 * max(s_obj_vals) + 0.5 * float(np.mean(topk))

    far_few_flag = any((c["far"] or c["few"]) for c in cands)
    rare_class_flag = any(c["class_name"] in ("bicycle", "motorcycle") for c in cands)

    # vector cho OOD
    ood_vec = np.array([
        math.log1p(frame["aux"]["n_total"]), math.log1p(frame["aux"]["n_fg"]),
        frame["aux"]["frac_air"], frame["aux"]["mean_int"],
        math.log1p(len(cands)), float(crowd),
        math.log1p(np.mean([c["dist"] for c in cands]) if cands else 0.0),
        frame["aux"]["rain_proxy"],
    ])
    return {
        "crowd_count": int(crowd), "night": float(night), "rain_score": float(rain),
        "obj_agg": float(obj_agg), "far_few_flag": bool(far_few_flag),
        "rare_class_flag": bool(rare_class_flag), "ood_vec": ood_vec,
    }


def fit_ood_reference(frame_dicts: List[dict], frame_cfg, seed: int = 0) -> object:
    """Fit Mahalanobis trên tập V. ood_ref='comfort': chỉ lấy nửa frame có model
    tự tin nhất — xấp xỉ 'phân phối model đã học' mà không cần tập train."""
    from .utils import Mahalanobis
    Vs = [f for f in frame_dicts if f["split"] == "V"]
    if not Vs:
        return None
    if frame_cfg.ood_ref == "comfort":
        Vs = sorted(Vs, key=lambda f: -f["mean_det_score"])[: max(1, len(Vs) // 2)]
    X = np.stack([f["ood_vec"] for f in Vs])
    return Mahalanobis().fit(X)


def aggregate_frame_scores(frame_dicts: List[dict], frame_cfg, ood_model) -> None:
    """Rank-aggregation trong phạm vi 1 split → s_frame + rule_only + slice_primary."""
    if ood_model is not None:
        X = np.stack([f["ood_vec"] for f in frame_dicts])
        ood_raw = ood_model.score(X)
    else:
        ood_raw = np.zeros(len(frame_dicts))
    for f, o in zip(frame_dicts, ood_raw):
        f["ood_raw"] = float(o)

    comps = {
        "obj": np.array([f["obj_agg"] for f in frame_dicts]),
        "crowd": np.array([min(1.0, f["crowd_count"] / 10.0) for f in frame_dicts]),
        "weather": np.array([max(f["night"], f["rain_score"]) for f in frame_dicts]),
        "ood": np.array([f["ood_raw"] for f in frame_dicts]),
    }
    weights = {"obj": frame_cfg.w_obj, "crowd": frame_cfg.w_crowd,
               "weather": frame_cfg.w_weather, "ood": frame_cfg.w_ood}
    from .utils import weighted_rank_agg
    agg = weighted_rank_agg(comps, weights)

    order = ["rare_class", "crowd", "night", "rain", "far_few"]
    for f, s in zip(frame_dicts, agg):
        hard = int(f["crowd_count"] >= frame_cfg.crowd_n) + int(f["night"] > 0) \
            + int(f["rain_score"] > 0.5)
        f["s_frame"] = float(min(1.0, s + frame_cfg.hard_boost * hard))
        # điểm 'rule-only' cho ablation (phản biện: tautology) — chỉ dùng tín hiệu
        # mã hoá được bằng luật, không có shape/unc/ood
        f["rule_only"] = float(
            int(f["far_few_flag"]) + int(f["crowd_count"] >= frame_cfg.crowd_n)
            + int(f["night"] > 0) + int(f["rain_score"] > 0.5))
        # slice chính cho quota đa dạng hoá
        sl = "typical"
        for name in order:
            ok = {
                "rare_class": f["rare_class_flag"],
                "crowd": f["crowd_count"] >= frame_cfg.crowd_n,
                "night": f["night"] > 0,
                "rain": f["rain_score"] > 0.5,
                "far_few": f["far_few_flag"],
            }[name]
            if ok:
                sl = name
                break
        f["slice_primary"] = sl
