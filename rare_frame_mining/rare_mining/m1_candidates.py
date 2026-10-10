"""M1 — Sinh ứng viên vật thể KHÔNG cần nhãn (2 nguồn):
  (a) clustering class-agnostic  → bắt cả vật model bỏ sót;
  (b) detections của PointPillars (chỉ inference) + TTA → s_unc.
Hai nguồn được match theo BEV-IoU để không đếm đôi (phản biện: M1 phải gộp tường minh).
"""
import math
from typing import List, Optional, Tuple

import numpy as np

from . import features as F
from .detectors import (BaseDetector, Detection, augment_points,
                        tta_passes, untransform_box)


def _local_bottom(pts: np.ndarray, cands: List[dict], radius: float) -> None:
    """Đáy vật so với mặt đất CỤC BỘ (p5 z trong bán kính `radius`) → c['bottom_ag'].
    Dùng cho phép thử hình học của cổng ngoại lai (mặt đất toàn frame sai khi đường dốc)."""
    if not cands or pts.shape[0] == 0:
        return
    xy, z = pts[:, :2], pts[:, 2]
    r2 = radius * radius
    for c in cands:
        cx, cy, cz = (float(v) for v in c["center"][:3])
        m = (xy[:, 0] - cx) ** 2 + (xy[:, 1] - cy) ** 2 < r2
        if m.sum() >= 5:
            c["bottom_ag"] = float(cz - c["H"] / 2.0 - np.percentile(z[m], 5))


def _default_candidate(fid: str, cid: int, f: dict, dist: float) -> dict:
    return {
        "fid": fid, "cid": cid,
        "source": "cluster",
        "center": np.array(f["centroid"]),
        "size": np.array([f["L"], f["W"], f["H"]]),
        "yaw": f["yaw"],
        "dist": float(dist),
        "n_points": int(f["n_points"]),
        "L": f["L"], "W": f["W"], "H": f["H"],
        "eig1": f["eig1"], "eig2": f["eig2"], "eig3": f["eig3"],
        "density": f["density"], "height": f["height"],
        "mean_intensity": f["mean_intensity"],
        "class_name": None, "probs": None, "det_score": None,
        "tta_std_xy": 0.0, "tta_std_size": 0.0, "tta_entropy": 0.0,
        "tta_passes": 0, "missed": True,
        # flag cứng (điểm yếu model / slice của đề)
        "far": False, "few": False, "confusion": False,
    }


def _entropy(probs: Optional[np.ndarray]) -> float:
    if probs is None:
        return 0.0
    p = np.asarray(probs, dtype=float)
    p = p / max(p.sum(), 1e-9)
    return float(-(p * np.log(p + 1e-12)).sum() / math.log(len(p) + 1e-9))


def _match_dets_to_clusters(cands: List[dict], dets: List[Detection],
                            iou_thresh: float = 0.25) -> List[Detection]:
    """Greedy match detection↔cluster theo BEV-IoU; detection không khớp ai
    sẽ được thêm thành candidate riêng (nguồn 'det')."""
    from .utils import bev_iou
    unmatched = []
    used_det = set()
    for c in cands:
        best, best_iou = -1, iou_thresh
        for di, d in enumerate(dets):
            if di in used_det:
                continue
            box_c = (c["center"][0], c["center"][1], c["size"][0], c["size"][1], c["yaw"])
            box_d = (d.center[0], d.center[1], d.size[0], d.size[1], d.yaw)
            iou = bev_iou(box_c, box_d)
            if iou > best_iou:
                best, best_iou = di, iou
        if best >= 0:
            used_det.add(best)
            d = dets[best]
            c["source"] = "cluster+det"
            c["class_name"] = d.class_name
            c["probs"] = None if d.probs is None else np.asarray(d.probs)
            c["det_score"] = float(d.score)
            c["missed"] = False
            if d.n_points > 0:
                c["n_points"] = int(d.n_points)
        # không khớp → giữ nguyên (missed=True) — đúng ý: model bỏ sót → hiếm
    for di, d in enumerate(dets):
        if di not in used_det:
            unmatched.append(d)
    return unmatched


def build_frame(points: np.ndarray, fid: str, det: BaseDetector, cfg,
                rng: np.random.Generator, pose=None) -> Tuple[List[dict], dict, float]:
    """Trả về (candidates, aux_frame, mean_det_score).

    aux chứa thống kê điểm cho M3 (OOD, rain proxy...). KHÔNG dùng nhãn.
    """
    from .outlier_gate import raw_point_stats
    raw_stats = raw_point_stats(points)          # cho cổng ngoại lai (phép thử 1)
    pts = F.crop_roi(points, cfg.roi)
    aux = {"n_total": int(pts.shape[0]), "n_fg": 0, "frac_air": 0.0,
           "mean_int": -1.0, "rain_proxy": 0.0, **raw_stats}
    if pts.shape[0] == 0:
        return [], aux, 0.0

    # --- rain proxy trên toàn frame (trước khi cắt fg) ---
    from .weather import lidar_rain_proxy
    aux["rain_proxy"] = lidar_rain_proxy(pts)
    if pts.shape[1] >= 4:
        aux["mean_int"] = float(pts[:, 3].mean())

    # --- (a) clustering class-agnostic ---
    fg = F.remove_ground(pts, cfg.cluster.ground_cell, cfg.cluster.ground_h_thresh)
    aux["n_fg"] = int(fg.shape[0])
    if fg.shape[0]:
        air = fg[:, 2] > 0.8
        aux["frac_air"] = float(air.mean()) if fg.shape[0] else 0.0
    if pose is not None and fg.shape[0]:
        from .outlier_gate import occupancy_cells
        aux["fg_cells"] = occupancy_cells(fg[:, :2], pose, cfg.gate.cell_m)   # cho phép thử 2
    labels = F.cluster_points(fg, cfg.cluster)
    ground_ref = float(np.percentile(fg[:, 2], 5)) if fg.shape[0] else 0.0

    cands: List[dict] = []
    if labels.size:
        for lab in np.unique(labels):
            if lab < 0:
                continue
            cpts = fg[labels == lab]
            if cpts.shape[0] < cfg.cluster.min_cluster_points:
                continue
            f = F.cluster_features(cpts, ground_ref)
            dist = math.hypot(f["centroid"][0], f["centroid"][1])
            cands.append(_default_candidate(fid, len(cands), f, dist))

    # --- (b) detector canonical pass ---
    dets = det.detect(pts) if det is not None else []
    unmatched = _match_dets_to_clusters(cands, dets)
    for d in unmatched:
        c = _default_candidate(
            fid, len(cands),
            {"centroid": tuple(d.center), "L": d.size[0], "W": d.size[1], "H": d.size[2],
             "eig1": 0.0, "eig2": 0.0, "eig3": 0.0, "density": d.n_points / (float(np.prod(d.size)) + 1e-3),
             "height": float(d.center[2] - ground_ref), "yaw": d.yaw,
             "n_points": d.n_points, "mean_intensity": -1.0},
            math.hypot(d.center[0], d.center[1]))
        c.update({"source": "det", "class_name": d.class_name,
                  "probs": None if d.probs is None else np.asarray(d.probs),
                  "det_score": float(d.score), "missed": False})
        cands.append(c)

    _local_bottom(pts, cands, cfg.gate.ground_radius_m if hasattr(cfg, "gate") else 3.0)

    # --- TTA passes → s_unc ---
    passes = tta_passes(cfg.tta)[1:]  # bỏ canonical
    matches = {i: [] for i in range(len(cands))}
    for rot, flip in passes:
        aug = augment_points(pts, rot, flip, cfg.tta.jitter_std, rng)
        for d in det.detect(aug):
            c0, y0 = untransform_box(d.center, d.yaw, rot, flip)
            for i, c in enumerate(cands):
                dd = math.hypot(c["center"][0] - c0[0], c["center"][1] - c0[1])
                if dd <= cfg.tta.match_radius:
                    matches[i].append((c0, d.size, float(y0), d.probs))
                    break
    for i, c in enumerate(cands):
        ms = matches[i]
        c["tta_passes"] = len(passes)
        if ms:
            centers = np.array([m[0] for m in ms])
            sizes = np.array([m[1] for m in ms])
            ents = [_entropy(m[3]) for m in ms]
            c["tta_std_xy"] = float(centers[:, :2].std(axis=0).mean())
            c["tta_std_size"] = float(sizes.std(axis=0).mean())
            c["tta_entropy"] = float(np.mean(ents))
            c["missed"] = False
        # không match pass nào: giữ missed=True → M2 gán uncertainty cao nhất

    mean_score = float(np.mean([c["det_score"] for c in cands if c["det_score"] is not None])) \
        if any(c["det_score"] is not None for c in cands) else 0.0
    return cands, aux, mean_score
