"""M2 — Điểm VẬT THỂ: s_shape + s_unc + s_slice + s_vru (đúng 4 thành phần của đề).

Sửa theo phản biện:
- Các thành phần chỉ tính RAW ở đây; rank-aggregation (Borda có trọng số) thực hiện
  trong phạm vi từng split (V hoặc T) — không cộng đại số thô các thước khác scale.
- s_unc trọng số THẤP (rareness ≠ uncertainty — REM ECCV'22: uncertainty dò cả
  case 'hard' bị che/khoảng cách, không chỉ 'rare').
- Shape model (IsolationForest) CHỈ fit trên tập V — không chạm T.
"""
import math
from typing import List, Optional

import numpy as np

from .features import vru_prior


def _shape_matrix(cands: List[dict]) -> np.ndarray:
    rows = []
    for c in cands:
        rows.append([c["L"], c["W"], c["H"], c["eig1"], c["eig2"], c["eig3"],
                     c["density"], math.log1p(c["n_points"]), c["height"]])
    return np.asarray(rows, dtype=float)


def score_candidates(cands: List[dict], obj_cfg, fit_cands: List[dict]) -> None:
    """Tính các thành phần RAW cho mọi candidate. fit_cands = candidates của tập V
    (chỉ dùng để fit thống kê, không phải nhãn). Ghi trực tiếp vào dict candidate."""
    X = _shape_matrix(cands)
    Xf = _shape_matrix(fit_cands) if fit_cands else X

    # ---- s_shape: độ hiếm hình dạng trong không gian đặc trưng ----
    method = "iforest"
    raw_shape = None
    try:
        from sklearn.ensemble import IsolationForest
        if Xf.shape[0] >= 30:
            model = IsolationForest(n_estimators=100, contamination="auto",
                                    random_state=0).fit(Xf)
            raw_shape = -model.score_samples(X)  # lớn = hiếm hơn
            method = "iforest"
    except Exception:
        raw_shape = None
    if raw_shape is None:
        # fallback: khoảng cách kNN đến tập fit
        try:
            from sklearn.neighbors import NearestNeighbors
            k = min(10, max(2, Xf.shape[0] - 1))
            nn = NearestNeighbors(n_neighbors=k).fit(Xf)
            raw_shape = np.asarray(nn.kneighbors(X)[0]).mean(axis=1)
            method = "knn"
        except Exception:
            mu = Xf.mean(axis=0)
            sd = Xf.std(axis=0) + 1e-6
            raw_shape = np.sqrt(((X - mu) / sd) ** 2).mean(axis=1)
            method = "zdist"
    for c, r in zip(cands, raw_shape):
        c["s_shape_raw"] = float(r)
        c["shape_method"] = method

    # ---- s_unc: TTA variance + entropy; missed-by-model = uncertain nhất ----
    raw_unc = np.array([c["tta_std_xy"] * 2.0 + c["tta_std_size"] * 2.0 + c["tta_entropy"]
                        for c in cands], dtype=float)
    missed = np.array([bool(c["missed"]) for c in cands])
    if missed.any():
        cap = float(np.nanmax(raw_unc[~missed])) + 0.5 if (~missed).any() else 1.0
        raw_unc[missed] = max(cap, 1.0)
    for c, r in zip(cands, raw_unc):
        c["s_unc_raw"] = float(r)

    # ---- flags cứng & s_slice_raw & s_vru ----
    pairs = {frozenset(p) for p in obj_cfg.confusing_pairs}
    for c in cands:
        far = c["dist"] > obj_cfg.far_m
        few = c["n_points"] < obj_cfg.few_points
        confusion = False
        if c["probs"] is not None:
            p = np.asarray(c["probs"], dtype=float)
            top2 = np.argsort(p)[::-1][:2]
            names = ["pedestrian", "bicycle", "motorcycle", "vehicle", "other"]
            confusion = frozenset((names[top2[0]], names[top2[1]])) in pairs
        c["far"], c["few"], c["confusion"] = bool(far), bool(few), bool(confusion)
        c["s_slice_raw"] = float(np.mean([far, few, confusion]))
        c["s_vru_raw"] = float(vru_prior(c, obj_cfg))


def aggregate_object_scores(cands: List[dict], obj_cfg) -> None:
    """Rank-aggregation trong phạm vi 1 split → s_obj."""
    comps = {
        "shape": np.array([c["s_shape_raw"] for c in cands]),
        "unc": np.array([c["s_unc_raw"] for c in cands]),
        "slice": np.array([c["s_slice_raw"] for c in cands]),
        "vru": np.array([c["s_vru_raw"] for c in cands]),
    }
    weights = {"shape": obj_cfg.w_shape, "unc": obj_cfg.w_unc,
               "slice": obj_cfg.w_slice, "vru": obj_cfg.w_vru}
    from .utils import weighted_rank_agg
    agg = weighted_rank_agg(comps, weights)
    for c, s in zip(cands, agg):
        hard = int(c["far"]) + int(c["few"]) + int(c["confusion"])
        c["s_obj"] = float(min(1.0, s + obj_cfg.hard_boost * hard))
