"""M6 — Đánh giá trên GT giấu: bộ lọc luật + P/R@B theo slice + baselines + ablation.

Sửa theo phản biện (tautology):
- Bổ sung ablation RULE-ONLY (chỉ cờ luật) vs FULL scorer → chứng minh
  shape/unc/ood đóng góp thật.
- Bổ sung metric YIELD (số GT VRU box mỗi frame gán nhãn) — đo giá trị downstream.
- Baseline: random (≥ n_seeds seeds, mean±std) + confidence-only.
- Thống kê: bootstrap theo SCENE cho recall@B; Wilson CI cho precision từng slice.
- Báo thêm recall@B TRƯỚC/SAU dedup để minh bạch chi phí của dedup.

"Nhãn thật giấu" = GT không bao giờ được scorer nhìn thấy (trừ chế độ tune="rule_v"
chỉ dùng GT của V và được khai báo). Định nghĩa rule đúng theo đề ngày 9/10.
"""
import math
import random
from typing import Dict, List, Optional

import numpy as np

from .utils import average_precision, bev_iou, save_json, wilson_ci

VRU_CLASSES = ("pedestrian", "bicycle", "motorcycle")


# ---------------------------------------------------------------------------
# GT rule filter ("đáp án giấu")
# ---------------------------------------------------------------------------

def gt_rare_object(gtb, obj_cfg) -> bool:
    if gtb.class_name in ("bicycle", "motorcycle"):
        return True
    if getattr(obj_cfg, "far_few_scope", "vru") == "vru" and gtb.class_name not in VRU_CLASSES:
        return False
    dist = math.hypot(gtb.center[0], gtb.center[1])
    if dist > obj_cfg.far_m:
        return True
    if gtb.num_lidar_pts >= 0 and gtb.num_lidar_pts < obj_cfg.few_points:
        return True
    return False


def gt_frame_flags(frame: dict, obj_cfg, frame_cfg) -> dict:
    gt = frame.get("gt") or []
    rare_objs = [g for g in gt if gt_rare_object(g, obj_cfg)]
    n_ped = sum(1 for g in gt if g.class_name == "pedestrian")
    from .weather import parse_desc
    w = parse_desc(frame.get("desc", ""))
    crowd = n_ped >= frame_cfg.crowd_n
    return {
        "rare_objs": rare_objs,
        "n_rare": len(rare_objs),
        "n_vru": sum(1 for g in gt if g.class_name in VRU_CLASSES),
        "crowd": crowd, "night": w["night"], "rain": w["rain"],
        "rare_frame": bool(rare_objs or crowd or w["night"] or w["rain"]),
        "slices": {
            "rare_class": any(g.class_name in ("bicycle", "motorcycle") for g in gt),
            "far_few": any((math.hypot(g.center[0], g.center[1]) > obj_cfg.far_m
                            or (0 <= g.num_lidar_pts < obj_cfg.few_points))
                           and (getattr(obj_cfg, "far_few_scope", "vru") != "vru"
                                or g.class_name in VRU_CLASSES) for g in gt),
            "crowd": crowd, "night": w["night"], "rain": w["rain"],
        },
    }


# ---------------------------------------------------------------------------
# Metrics
# ---------------------------------------------------------------------------

def _pr_at_b(ranked_fids: List[str], pos: set, B: int) -> tuple:
    sel = ranked_fids[:B]
    tp = sum(1 for f in sel if f in pos)
    prec = tp / max(len(sel), 1)
    rec = tp / max(len(pos), 1)
    return prec, rec, tp


def _object_metrics(sel_fids: List[str], cands_by_fid, gt_flags_by_fid, iou_thresh: float) -> dict:
    n_sel_obj, n_correct, gt_total = 0, 0, 0
    for fid in sel_fids:
        fl = gt_flags_by_fid.get(fid)
        if fl is None:
            continue
        gt_total += fl["n_rare"]
        cands = cands_by_fid.get(fid, [])
        n_sel_obj += len(cands)
        for c in cands:
            box = (c["center"][0], c["center"][1], c["size"][0], c["size"][1], c["yaw"])
            for g in fl["rare_objs"]:
                gb = (g.center[0], g.center[1], g.size[0], g.size[1], g.yaw)
                if bev_iou(box, gb) >= iou_thresh:
                    n_correct += 1
                    break
    return {
        "n_selected_objects": n_sel_obj,
        "object_precision": n_correct / max(n_sel_obj, 1),
        "object_recall": (n_correct / max(gt_total, 1)) if gt_total else float("nan"),
        "n_gt_rare_total": gt_total,
    }


def evaluate(frames: Dict[str, dict], cands: List[dict], cfg, gate: dict = None) -> dict:
    """Chạy toàn bộ M6 trên các frame split='T'."""
    ev = cfg.evalcfg
    obj_cfg, frame_cfg = cfg.obj, cfg.frame
    T = [f for f in frames.values() if f["split"] == "T"]
    n_pilot = sum(1 for f in frames.values() if f["split"] == "PILOT")
    missing_gt = [f["fid"] for f in T if f.get("gt") is None]
    if missing_gt:
        raise RuntimeError(f"M6 cần GT cho tập T nhưng thiếu ở {len(missing_gt)} frame "
                           f"(vd {missing_gt[0]}). Nguồn dữ liệu không cung cấp GT?")

    gt_flags_by_fid = {f["fid"]: gt_frame_flags(f, obj_cfg, frame_cfg) for f in T}
    pos = {fid for fid, fl in gt_flags_by_fid.items() if fl["rare_frame"]}
    slices_pos = {s: {fid for fid, fl in gt_flags_by_fid.items() if fl["slices"][s]}
                  for s in ("rare_class", "far_few", "crowd", "night", "rain")}
    cands_by_fid: Dict[str, List[dict]] = {}
    for c in cands:
        if frames[c["fid"]]["split"] == "T":
            cands_by_fid.setdefault(c["fid"], []).append(c)

    # ---- các bảng xếp hạng ----
    pipe_kept = sorted(T, key=lambda f: f.get("rank", 10 ** 9))
    pipe_fids = [f["fid"] for f in pipe_kept]                      # pipeline: sau dedup
    nodedup_fids = sorted([f["fid"] for f in T], key=lambda fid: frames[fid]["rank_nodedup"])
    ruleonly_fids = sorted([f["fid"] for f in T], key=lambda fid: -frames[fid]["rule_only"])
    conf_fids = sorted([f["fid"] for f in T], key=lambda fid: frames[fid]["mean_det_score"])
    rng = random.Random(ev.n_seeds)
    random_fids_seeds = []
    fids_T = [f["fid"] for f in T]
    for _ in range(max(1, ev.n_seeds)):
        r = fids_T[:]
        rng.shuffle(r)
        random_fids_seeds.append(r)

    def variant_metrics(fids: List[str]) -> dict:
        out = {"AP": average_precision([1 if f in pos else 0 for f in fids])}
        for B in ev.budgets:
            p, r, tp = _pr_at_b(fids, pos, B)
            out[f"P@{B}"], out[f"R@{B}"] = p, r
        return out

    random_runs = [variant_metrics(r) for r in random_fids_seeds]
    rand_B = {f"R@{B}": [run[f"R@{B}"] for run in random_runs] for B in ev.budgets}
    rand_P = {f"P@{B}": [run[f"P@{B}"] for run in random_runs] for B in ev.budgets}

    mid = ev.budgets[len(ev.budgets) // 2]
    report = {
        "n_frames_T": len(T), "n_rare_frames": len(pos),
        "n_pilot_excluded": n_pilot,
        "base_rate": len(pos) / max(len(T), 1),
        "budgets": list(ev.budgets),
        "pipeline": variant_metrics(pipe_fids),
        "pipeline_nodedup": variant_metrics(nodedup_fids),
        "rule_only_ablation": variant_metrics(ruleonly_fids),
        "confidence_only": variant_metrics(conf_fids),
        "random_mean": {k: float(np.mean(v)) for k, v in {**rand_P, **rand_B}.items()},
        "random_std": {k: float(np.std(v)) for k, v in {**rand_P, **rand_B}.items()},
        "dedup_effect": {f"R@{B}": variant_metrics(pipe_fids)[f"R@{B}"] - variant_metrics(nodedup_fids)[f"R@{B}"]
                         for B in ev.budgets},
    }

    # ---- yield: số GT VRU box mỗi frame được gán nhãn ----
    def yield_at(fids: List[str], B: int) -> float:
        return sum(gt_flags_by_fid[f]["n_vru"] for f in fids[:B]) / max(B, 1)
    report["yield_vru_per_frame"] = {
        "pipeline": yield_at(pipe_fids, mid),
        "random_mean": float(np.mean([yield_at(r, mid) for r in random_fids_seeds])),
        "rule_only": yield_at(ruleonly_fids, mid),
    }

    # ---- theo slice (pipeline vs random, kèm n và Wilson) ----
    slice_report = {}
    for s, sp in slices_pos.items():
        if not sp:
            slice_report[s] = {"n_pos": 0}
            continue
        # recall trong slice = recall trên các frame hiếm thuộc slice đó
        def slice_recall(fids: List[str], B: int) -> float:
            sel = [f for f in fids[:B] if f in sp]
            # frame được chọn thuộc slice và hiếm
            tp = sum(1 for f in fids[:B] if f in sp and f in pos)
            return tp / max(len(sp), 1)
        sel_mid = pipe_fids[:mid]
        n_sel_in_slice = sum(1 for f in sel_mid if f in sp and f in pos)
        k = sum(1 for f in sel_mid if f in sp)
        slice_report[s] = {
            "n_pos": len(sp),
            f"R@{mid}": slice_recall(pipe_fids, mid),
            f"random_R@{mid}": float(np.mean([slice_recall(r, mid) for r in random_fids_seeds])),
            f"P_in_slice@{mid}": n_sel_in_slice / max(k, 1),
            "wilson": wilson_ci(n_sel_in_slice, k),
        }
    report["slices"] = slice_report

    # ---- object-level ----
    report["object_level"] = {
        "pipeline": _object_metrics(pipe_fids[:mid], cands_by_fid, gt_flags_by_fid, ev.iou_thresh),
        "random": _object_metrics(random_fids_seeds[0][:mid], cands_by_fid, gt_flags_by_fid, ev.iou_thresh),
        "budget": mid,
    }

    # ---- bootstrap theo SCENE cho recall@mid ----
    scenes = sorted({frames[fid]["scene"] for fid in fids_T})
    by_scene = {s: [fid for fid in fids_T if frames[fid]["scene"] == s] for s in scenes}
    pos_scenes = {fid: (fid in pos) for fid in fids_T}

    def boot_recall(rank_map) -> List[float]:
        vals = []
        brng = random.Random(123)
        for _ in range(ev.bootstrap):
            samp = [by_scene[brng.choice(scenes)] for _ in range(len(scenes))]
            flat = [fid for sc in samp for fid in sc]
            npos = sum(1 for fid in flat if pos_scenes[fid])
            if npos == 0:
                continue
            tp = sum(1 for fid in flat[:mid] if pos_scenes[fid])
            vals.append(tp / npos)
        return vals

    pipe_map = {fid: i for i, fid in enumerate(pipe_fids)}
    vals = boot_recall(pipe_map)
    report["bootstrap_recall_by_scene"] = {
        "budget": mid,
        "pipeline_ci95": [float(np.percentile(vals, 2.5)), float(np.percentile(vals, 97.5))] if vals else None,
    }

    # ---- lift so với random ----
    report["lift_over_random"] = {
        f"R@{B}": report["pipeline"][f"R@{B}"] - report["random_mean"][f"R@{B}"]
        for B in ev.budgets
    }
    # Cổng ngoại lai: (1) bao nhiêu frame hiếm THẬT (theo GT) bị xếp nhầm là ngoại lai/nghi ngờ;
    # (2) bao nhiêu frame cố ý làm hỏng lọt vào nhóm hợp lệ (corruption_test, tính trong pipeline).
    pos_T = [f for f in T if gt_frame_flags(f, obj_cfg, frame_cfg)["rare_frame"]]
    report["outlier_gate"] = {
        "counts_T": {g: sum(1 for f in T if f.get("gate", "valid") == g)
                     for g in ("valid", "suspect", "outlier")},
        "rare_true_as_outlier": (round(sum(1 for f in pos_T if f.get("gate") == "outlier")
                                       / len(pos_T), 4) if pos_T else None),
        "rare_true_as_suspect": (round(sum(1 for f in pos_T if f.get("gate") == "suspect")
                                       / len(pos_T), 4) if pos_T else None),
        "corruption_test": (gate or {}).get("corruption_test", {}),
        "domain_shift_warning": (gate or {}).get("domain_shift_warning", False),
    }
    m = getattr(cfg, "model", None)
    if m is not None:
        report["model"] = {"mode": m.mode, "provenance": m.provenance,
                           "retrain": m.retrain, "explore_frac": m.explore_frac,
                           "note": ("AP downstream chỉ báo khi retrain=True"
                                    if not m.retrain else
                                    "retrain bật: báo thêm AP của model sau vòng (ngoài M6)")}
    return report


def print_report(report: dict) -> None:
    p = report["pipeline"]
    rm, rs = report["random_mean"], report["random_std"]
    print("\n=== M6 — KẾT QUẢ ĐÁNH GIÁ (tập T, GT giấu) ===")
    print(f"Frames T: {report['n_frames_T']} | frame hiếm (rule): {report['n_rare_frames']} "
          f"({report['base_rate']:.1%}) | budgets: {report['budgets']}")
    print(f"{'Chỉ số':<12}{'Pipeline':>10}{'Random':>18}{'Rule-only':>11}{'Conf-only':>11}{'NoDedup':>9}")
    for B in report["budgets"]:
        for m in (f"P@{B}", f"R@{B}"):
            print(f"{m:<12}{p[m]:>10.3f}{rm[m]:>11.3f}±{rs[m]:.3f}"
                  f"{report['rule_only_ablation'][m]:>11.3f}"
                  f"{report['confidence_only'][m]:>11.3f}"
                  f"{report['pipeline_nodedup'][m]:>9.3f}")
    print(f"AP (full ranking): pipeline {p['AP']:.3f} | rule-only {report['rule_only_ablation']['AP']:.3f}")
    y = report["yield_vru_per_frame"]
    print(f"Yield GT-VRU/frame @B: pipeline {y['pipeline']:.2f} vs random {y['random_mean']:.2f}")
    print("Theo slice (@budget giữa):")
    for s, d in report["slices"].items():
        if d.get("n_pos", 0) == 0:
            print(f"  {s:<11} — không có mẫu dương trong T")
            continue
        key = [k for k in d if k.startswith("R@")][0]
        print(f"  {s:<11} n={d['n_pos']:<4} R={d[key]:.3f} (random {d['random_' + key]:.3f}) "
              f"wilson={tuple(round(x, 2) for x in d['wilson'])}")
    ob = report["object_level"]["pipeline"]
    print(f"Object-level @B: precision {ob['object_precision']:.3f}, "
          f"recall {ob['object_recall']:.3f} (IoU ≥ 0.5)")
    ci = report["bootstrap_recall_by_scene"]["pipeline_ci95"]
    if ci:
        print(f"Bootstrap recall@{report['bootstrap_recall_by_scene']['budget']} (theo scene): "
              f"[{ci[0]:.3f}, {ci[1]:.3f}]")
    print_gate(report)


def print_gate(report: dict) -> None:
    g = report.get("outlier_gate")
    if not g:
        return
    print(f"Cổng ngoại lai (T): {g['counts_T']} | frame hiếm thật bị xếp Ngoại lai: "
          f"{g['rare_true_as_outlier']} · Nghi ngờ: {g['rare_true_as_suspect']}")
    for k, d in (g.get("corruption_test") or {}).items():
        print(f"  lỗi giả '{k}': n={d['n']} lọt vào Hợp lệ={d['valid']} "
              f"(leak {d['leak_rate']}), Nghi ngờ={d['suspect']}, Ngoại lai={d['outlier']}")
    if g.get("domain_shift_warning"):
        print("  CẢNH BÁO: nhiều frame T cô lập so với V → lệch domain, không phải hiếm")


def save_report(report: dict, path: str) -> None:
    save_json(report, path)
