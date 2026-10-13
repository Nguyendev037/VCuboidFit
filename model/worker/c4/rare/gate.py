"""M2a · cổng frame valid/suspect/outlier (planning/11 SPEC-P05 §4). Không đọc nhãn/GT/mô tả scene (A1, A2).
outlier và suspect KHÔNG BAO GIỜ vào lô chọn (A5)."""
import numpy as np
import pandas as pd


def gate_frame(objects: list[dict], keep: bool, z0_row: np.ndarray, z0_mean: np.ndarray,
               z0_std: float, cfg: dict) -> tuple[str, str, bool]:
    """-> (gate, gate_fail, ood_flag). Thứ tự: lọc LiDAR -> không ứng viên -> OOD -> mọi vật dưới min_pts.

    `cfg`: `gate_ood_sigma` (mặc định 3.0), `min_pts` (mặc định 1). `z0_std` = bán kính RMS của z0 quanh trung bình
    trên frame keep=True (độ lệch chuẩn tổng, một số vô hướng). ‖z0 - mean‖ > sigma*std => ood_flag; > 2*sigma*std
    => suspect "ood"."""
    if not keep:
        return "outlier", "lidar_filtered", False
    if len(objects) == 0:
        return "suspect", "no_candidates", False
    sigma = float(cfg.get("gate_ood_sigma", 3.0))
    dev = float(np.linalg.norm(np.asarray(z0_row, np.float64) - z0_mean))
    ood = bool(z0_std > 0 and dev > sigma * z0_std)
    if z0_std > 0 and dev > 2 * sigma * z0_std:
        return "suspect", "ood", True
    if all(o["pts"] < int(cfg.get("min_pts", 1)) for o in objects):
        return "suspect", "all_below_min_pts", ood
    return "valid", "", ood


def gate_all(rare_objects: pd.DataFrame, index: pd.DataFrame, z0: np.ndarray, keep: np.ndarray,
             cfg: dict) -> pd.DataFrame:
    """-> {sample_token, gate, gate_fail, ood_flag} theo thứ tự `index`. z0_mean/z0_std tính trên frame keep=True."""
    keep = np.asarray(keep, bool)
    z0 = np.asarray(z0, np.float64)
    mean = z0[keep].mean(0) if keep.any() else np.zeros(z0.shape[1])
    std = float(np.sqrt(((z0[keep] - mean) ** 2).sum(1).mean())) if keep.any() else 0.0
    per_frame = {t: g.to_dict("records") for t, g in rare_objects.groupby("sample_token")}
    rows = []
    for i, tok in enumerate(index["sample_token"]):
        g, why, ood = gate_frame(per_frame.get(tok, []), bool(keep[i]), z0[i], mean, std, cfg)
        rows.append(dict(sample_token=tok, gate=g, gate_fail=why, ood_flag=ood))
    return pd.DataFrame(rows, columns=["sample_token", "gate", "gate_fail", "ood_flag"])
