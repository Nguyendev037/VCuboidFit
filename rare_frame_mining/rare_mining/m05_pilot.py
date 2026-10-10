"""M0.5 — Pilot (bổ sung sau vòng phản biện thứ hai, cập nhật 10/10).

M0.5a run_sanity  : chạy detector trên tập nhỏ CÓ nhãn (random + phân tầng) →
    per-class recall/precision (kèm Wilson CI), recall slice gần/xa/ít-điểm cho VRU,
    kiểm schema (kênh intensity, mật độ điểm), kiểm IoU box-vs-GT (bắt lỗi thứ tự
    cột w/l/h của mmdet3d TRƯỚC khi đốt toàn bộ pool) → checklist go/no-go.
M0.5b (xem scripts/run_pilot.py subcommand `batch`): chạy pipeline trên vài trăm
    frame, xuất 2 lô gán tay (top-B' pipeline + random-B') → so yield thực tế.

Ràng buộc chống leak: frame pilot được pipeline ép split='PILOT' và M6 tự loại —
nhãn pilot KHÔNG BAO GIỜ dính vào tập báo cáo T.
Chú ý (phản biện): mẫu PHÂN TẦNG bị chệch → chỉ dùng để đo recall lớp hiếm;
base rate chỉ ước từ mẫu RANDOM.
"""
import math
import random
from typing import Dict, List, Optional

import numpy as np

from . import features as F
from .detectors import BaseDetector
from .utils import bev_iou, get_logger, wilson_ci

log = get_logger("m05_pilot")

VRU = ("pedestrian", "bicycle", "motorcycle")
CLASSES = ["pedestrian", "bicycle", "motorcycle", "car"]
FAR_M = 30.0
FEW_PTS = 10


# ---------------------------------------------------------------------------
# Chọn frame pilot (hai mẫu: random → base rate; phân tầng → recall lớp hiếm)
# ---------------------------------------------------------------------------

def _two_wheeler_signal(points: np.ndarray, cfg) -> bool:
    """Tín hiệu RẺ (chỉ cluster, không model): có cluster hình '2 bánh' không?"""
    pts = F.crop_roi(points, cfg.roi)
    if pts.shape[0] < 20:
        return False
    fg = F.remove_ground(pts, cfg.cluster.ground_cell, cfg.cluster.ground_h_thresh)
    if fg.shape[0] < 20:
        return False
    labels = F.cluster_points(fg, cfg.cluster)
    ground_ref = float(np.percentile(fg[:, 2], 5))
    for lab in np.unique(labels):
        if lab < 0:
            continue
        cpts = fg[labels == lab]
        if cpts.shape[0] < cfg.cluster.min_cluster_points:
            continue
        f = F.cluster_features(cpts, ground_ref)
        if 1.2 <= f["L"] <= 2.6 and 0.4 <= f["W"] <= 1.1 and 0.7 <= f["H"] <= 1.8:
            return True
    return False


def pick_pilot(frames, cfg, n_random: int, n_strat: int, seed: int = 0,
               max_scan: int = 1200) -> Dict[str, List[str]]:
    """Chọn frame cho pilot. Trả về {'random': [...], 'stratified': [...]}."""
    rng = random.Random(seed)
    all_fids = [fr.fid for fr in frames]
    random_fids = rng.sample(all_fids, min(n_random, len(all_fids)))
    chosen = set(random_fids)
    strat_fids: List[str] = []
    if n_strat > 0:
        pool = frames[:max_scan]
        for fr in pool:
            if len(strat_fids) >= n_strat:
                break
            if fr.fid in chosen:
                continue
            try:
                if _two_wheeler_signal(fr.load_points(), cfg):
                    strat_fids.append(fr.fid)
                    chosen.add(fr.fid)
            except Exception:
                continue
        log.info("Phân tầng: quét %d frame, chọn %d frame có tín hiệu 2-bánh",
                 len(pool), len(strat_fids))
    return {"random": random_fids, "stratified": strat_fids}


# ---------------------------------------------------------------------------
# M0.5a — Sanity check model
# ---------------------------------------------------------------------------

def _greedy_match(dets, gt_boxes, iou_thresh: float):
    """Match detection↔GT cùng lớp theo BEV-IoU, greedy theo score giảm dần.
    Trả về (pairs, matched_gt_idx): pairs = [(det_idx, gt_idx, iou)]."""
    order = sorted(range(len(dets)), key=lambda i: -dets[i].score)
    used_gt, pairs = set(), []
    for i in order:
        d = dets[i]
        best, biou = -1, iou_thresh
        for j, g in enumerate(gt_boxes):
            if j in used_gt or g.class_name != d.class_name:
                continue
            iou = bev_iou(
                (d.center[0], d.center[1], d.size[0], d.size[1], d.yaw),
                (g.center[0], g.center[1], g.size[0], g.size[1], g.yaw))
            if iou > biou:
                best, biou = j, iou
        if best >= 0:
            used_gt.add(best)
            pairs.append((i, best, biou))
    return pairs, used_gt


def run_sanity(frames, fids: List[str], det: BaseDetector, cfg,
               iou_thresh: float = 0.5) -> dict:
    """Chạy detector trên các frame (phải có GT) → báo cáo sanity + decisions."""
    by_fid = {fr.fid: fr for fr in frames}
    stats = {c: {"gt": 0, "tp": 0, "fp": 0} for c in CLASSES}
    vru_slices = {"near_lt30": [0, 0], "far_ge30": [0, 0], "sparse_lt10pts": [0, 0]}
    ious: List[float] = []
    n_ch = set()
    frames_with_int = 0
    pts_counts: List[int] = []
    used = with_gt = 0

    for fid in fids:
        fr = by_fid.get(fid)
        if fr is None:
            continue
        points = fr.load_points()
        used += 1
        n_ch.add(int(points.shape[1]))
        if points.shape[1] >= 4:
            frames_with_int += 1
        pts_counts.append(int(points.shape[0]))
        gt = []
        try:
            gt = fr.load_gt()
        except Exception:
            gt = []
        if not gt:
            continue
        with_gt += 1
        dets = det.detect(points)
        pairs, matched_gt = _greedy_match(dets, gt, iou_thresh)
        matched_det = {i for i, _, _ in pairs}
        for g in gt:
            if g.class_name in stats:
                stats[g.class_name]["gt"] += 1
        for k, d in enumerate(dets):
            if d.class_name in stats and k not in matched_det:
                stats[d.class_name]["fp"] += 1
        for _, j, iou in pairs:
            stats[gt[j].class_name]["tp"] += 1
            ious.append(iou)
        for j, g in enumerate(gt):
            if g.class_name not in VRU:
                continue
            hit = 1 if j in matched_gt else 0
            dist = math.hypot(g.center[0], g.center[1])
            key = "near_lt30" if dist < FAR_M else "far_ge30"
            vru_slices[key][0] += 1
            vru_slices[key][1] += hit
            if g.num_lidar_pts >= 0 and g.num_lidar_pts < FEW_PTS:
                vru_slices["sparse_lt10pts"][0] += 1
                vru_slices["sparse_lt10pts"][1] += hit

    per_class = {}
    for c, s in stats.items():
        rec = (s["tp"] / s["gt"]) if s["gt"] else None
        prec = (s["tp"] / (s["tp"] + s["fp"])) if (s["tp"] + s["fp"]) else None
        per_class[c] = {**s, "recall": rec, "precision": prec,
                        "recall_wilson95": wilson_ci(s["tp"], s["gt"]) if s["gt"] else None}

    rare = {c: stats[c] for c in ("bicycle", "motorcycle")}
    rare_gt = sum(s["gt"] for s in rare.values())
    rare_tp = sum(s["tp"] for s in rare.values())

    mean_iou = float(np.mean(ious)) if ious else None
    far_gt, far_tp = vru_slices["far_ge30"]
    decisions = [
        {"check": "box_schema (IoU TP trung bình — nếu thấp: kiểm tra thứ tự cột w/l/h)",
         "value": mean_iou, "n": len(ious),
         "verdict": ("PASS" if mean_iou is not None and mean_iou >= 0.55 else
                     ("WARN — kiểm tra thứ tự cột kích thước của detector" if mean_iou is not None else
                      "n/a — chưa có TP nào để đánh giá"))},
        {"check": "intensity_channel (cần cho rain_proxy)",
         "value": f"{frames_with_int}/{used}", "n": used,
         "verdict": ("PASS" if used and frames_with_int >= used / 2 else
                     "WARN — thiếu intensity → tắt rain_proxy ở M3")},
        {"check": "vru_recall_ngoai_30m (nếu <0.3: xem lại ngưỡng 'xa' của đề)",
         "value": (far_tp / far_gt) if far_gt else None, "n": far_gt,
         "verdict": ("PASS" if far_gt and far_tp / far_gt >= 0.3 else
                     ("WARN — model yếu ở xa" if far_gt else "n/a — không có GT xa"))},
        {"check": "rare_class_recall (bicycle+motorcycle)",
         "value": (rare_tp / rare_gt) if rare_gt else None, "n": rare_gt,
         "wilson95": wilson_ci(rare_tp, rare_gt) if rare_gt else None,
         "verdict": ("PASS" if rare_gt and rare_tp / rare_gt >= 0.25 else
                     ("WARN — lớp hiếm yếu: nguồn (b) ít giá trị với lớp hiếm" if rare_gt else
                      "n/a — mẫu chưa bắt được lớp hiếm, tăng n_strat"))},
    ]
    return {
        "n_frames_selected": len(fids), "n_frames_used": used,
        "n_frames_with_gt": with_gt,
        "schema": {"n_channels_seen": sorted(n_ch),
                   "frames_with_intensity": frames_with_int,
                   "mean_points_per_frame": float(np.mean(pts_counts)) if pts_counts else 0.0},
        "per_class": per_class,
        "vru_slices": vru_slices,
        "rare_class": {"gt": rare_gt, "tp": rare_tp,
                       "recall": (rare_tp / rare_gt) if rare_gt else None,
                       "wilson95": wilson_ci(rare_tp, rare_gt) if rare_gt else None},
        "decisions": decisions,
    }


def print_sanity(report: dict) -> None:
    print("\n=== M0.5a — SANITY CHECK MODEL (tập nhỏ có nhãn) ===")
    sc = report["schema"]
    print(f"Frames dùng: {report['n_frames_used']} (có GT: {report['n_frames_with_gt']}) | "
          f"channels: {sc['n_channels_seen']} | intensity: {sc['frames_with_intensity']} | "
          f"điểm/frame TB: {sc['mean_points_per_frame']:.0f}")
    print(f"{'Lớp':<12}{'GT':>6}{'TP':>5}{'FP':>5}{'Recall':>9}{'Wilson95':>17}{'Prec':>7}")
    for c, s in report["per_class"].items():
        if s["gt"] == 0 and not s["tp"] and not s["fp"]:
            continue
        rec = f"{s['recall']:.3f}" if s["recall"] is not None else "—"
        wil = (f"[{s['recall_wilson95'][0]:.2f},{s['recall_wilson95'][1]:.2f}]"
               if s["recall_wilson95"] else "—")
        prec = f"{s['precision']:.3f}" if s["precision"] is not None else "—"
        print(f"{c:<12}{s['gt']:>6}{s['tp']:>5}{s['fp']:>5}{rec:>9}{wil:>17}{prec:>7}")
    print("Slice VRU:", {k: {"gt": v[0], "tp": v[1]} for k, v in report["vru_slices"].items()})
    print("CHECKLIST QUYẾT ĐỊNH:")
    for d in report["decisions"]:
        print(f"  [{d['verdict']}] {d['check']} → {d['value']}")
