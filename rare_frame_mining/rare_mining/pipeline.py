"""Orchestrator M0→M5 (m6 do run_eval/demo gọi riêng).

Luồng v2 sau phản biện:
 1. Nạp frames, chia V/T THEO SCENE (không leak).
 2. M1: build candidates cho mọi frame (cluster + detector + TTA) — KHÔNG nhìn GT.
 3. M2: raw scores; shape model fit CHỈ trên candidates của V.
 4. M3: frame features; OOD fit CHỈ trên V (subset comfort).
 5. Aggregate trong từng split → s_obj, s_frame, rule_only; rank + dedup + quota.
 6. (Tuỳ chọn) tune="rule_v": grid-search trọng số frame trên GT của V — khai báo rõ.
 7. Ghi outputs + trả artifacts (frame dict có gt đính kèm để M6 dùng).
"""
import math
import os
from typing import List, Optional

import numpy as np

from . import m1_candidates, m2_object_score, m3_frame_score, m4_aggregate, m5_select
from . import outlier_gate
from .detectors import make_detector
from .utils import get_logger, set_seed

log = get_logger("pipeline")


def _split_scenes(frames: List[dict], val_frac: float, seed: int) -> None:
    """Chia V/T THEO SCENE; frame pilot/đã-gán (f["pilot"]) bị loại Ở CẤP FRAME —
    scene của nó vẫn tham gia V/T bình thường (loại cấp scene làm T co rút vô lý;
    không có rủi ro leak vì M0–M5 không nhìn GT)."""
    non_pilot = [f for f in frames if not f.get("pilot")]
    scenes = sorted({f["scene"] for f in non_pilot})
    rng = np.random.default_rng(seed)
    order = rng.permutation(len(scenes))
    n_val = max(1, int(round(val_frac * len(scenes))))
    val_scenes = {scenes[i] for i in order[:n_val]}
    for f in frames:
        if f.get("pilot"):
            f["split"] = "PILOT"   # chống leak: frame có nhãn không bao giờ vào V/T
        else:
            f["split"] = "V" if f["scene"] in val_scenes else "T"
    n_pilot = sum(1 for f in frames if f["split"] == "PILOT")
    log.info("Split theo scene: V=%d scene / T=%d scene | PILOT: %d frame (loại cấp frame)",
             n_val, len(scenes) - n_val, n_pilot)


def _recompute_frame_scores(frames: List[dict], fc, weights) -> None:
    from .utils import weighted_rank_agg
    comps = {
        "obj": np.array([f["obj_agg"] for f in frames]),
        "crowd": np.array([min(1.0, f["crowd_count"] / 10.0) for f in frames]),
        "weather": np.array([max(f["night"], f["rain_score"]) for f in frames]),
        "ood": np.array([f["ood_raw"] for f in frames]),
    }
    agg = weighted_rank_agg(comps, weights)
    for f, s in zip(frames, agg):
        hard = int(f["crowd_count"] >= fc.crowd_n) + int(f["night"] > 0) + int(f["rain_score"] > 0.5)
        f["s_frame"] = float(min(1.0, s + fc.hard_boost * hard))


def _corruption_test(frames_raw, frame_dicts, cands_by_fid, st, det, cfg, rng) -> dict:
    """Kiểm chứng cổng: cố ý làm hỏng frame V hợp lệ (4 kiểu lỗi), chạy lại M1 + cổng,
    đo tỉ lệ frame lỗi LỌT vào nhóm 'valid' (càng thấp càng tốt). Không dùng nhãn."""
    gcfg = cfg.gate
    if not gcfg.enabled or gcfg.corruption_test_n <= 0:
        return {}
    from .features import vru_prior
    by_fid = {f["fid"]: f for f in frame_dicts}
    src = {fr.fid: fr for fr in frames_raw}
    pool = [f for f in frame_dicts if f["split"] == "V" and f["gate"] == "valid"]
    if not pool:
        return {}
    idx = rng.choice(len(pool), size=min(gcfg.corruption_test_n, len(pool)), replace=False)
    out = {k: {"n": 0, "valid": 0, "suspect": 0, "outlier": 0} for k in outlier_gate.CORRUPTIONS}
    for i in idx:
        base = pool[int(i)]
        pts0 = src[base["fid"]].load_points()
        nbs = [(by_fid[n], cands_by_fid.get(n, [])) for n in base.get("gate_neighbors", [])
               if by_fid[n]["gate"] != "outlier"]
        prev = [by_fid[n]["t"] for n in base.get("gate_neighbors", []) if by_fid[n]["t"] < base["t"]]
        for kind in outlier_gate.CORRUPTIONS:
            pts = outlier_gate.corrupt_points(pts0, kind, rng)
            cands, aux, ms = m1_candidates.build_frame(pts, base["fid"] + "#" + kind, det, cfg, rng,
                                                       pose=base.get("pose"))
            for c in cands:
                c["s_vru_raw"] = float(vru_prior(c, cfg.obj))
                c["s_obj"] = 0.0
            f = {"fid": base["fid"] + "#" + kind, "scene": base["scene"], "t": base["t"],
                 "ego": base["ego"], "pose": base.get("pose"), "desc": base["desc"], "aux": aux,
                 "mean_det_score": ms,
                 "camera_paths": (), "split": "V"}
            f.update(m3_frame_score.frame_raw_features(f, cands, cfg.frame))
            fail1 = outlier_gate.validity_for(f, st, max(prev) if prev else None)
            gate, _ = outlier_gate.classify_one(f, cands, nbs, st, fail1)
            out[kind]["n"] += 1
            out[kind][gate] += 1
    for k, d in out.items():
        d["leak_rate"] = round(d["valid"] / d["n"], 3) if d["n"] else None
    return out


def run_pipeline(source, cfg, budget: int = 100, max_frames: Optional[int] = None,
                 tune: str = "none", verbose: bool = True,
                 subset_fids: Optional[List[str]] = None,
                 exclude_fids: Optional[List[str]] = None):
    """Chạy M0→M5. tune: 'none' (label-free, trọng số đều) | 'rule_v' (dùng GT của V).
    subset_fids: chạy chỉ trên tập frame con (M0.5b pilot batch).
    exclude_fids: frame pilot đã có nhãn → ép split='PILOT', loại khỏi V/T (chống leak)."""
    set_seed(cfg.split.seed)
    frames_raw = source.frames()
    if subset_fids:
        want = set(subset_fids)
        frames_raw = [f for f in frames_raw if f.fid in want]
    exclude = set(exclude_fids or [])
    if max_frames:
        # cắt đều theo scene để không phá split
        per_scene = {}
        kept = []
        for f in frames_raw:
            per_scene.setdefault(f.scene, [])
            if len(per_scene[f.scene]) < max_frames:
                kept.append(f)
                per_scene[f.scene].append(1)
        frames_raw = kept
    log.info("Số frame: %d", len(frames_raw))

    det = make_detector(cfg) if cfg.detector.backend != "none" else None
    rng = np.random.default_rng(cfg.split.seed)

    # --- M1: build candidates (không GT) ---
    frame_dicts: List[dict] = []
    all_cands: List[dict] = []
    for i, fr in enumerate(frames_raw):
        cands, aux, mean_score = m1_candidates.build_frame(fr.load_points(), fr.fid, det, cfg, rng,
                                                           pose=fr.sensor_pose)
        fd = {"fid": fr.fid, "scene": fr.scene, "t": fr.t, "ego": fr.ego_xy, "pose": fr.sensor_pose,
              "desc": fr.desc, "aux": aux, "mean_det_score": mean_score,
              "camera_paths": fr.camera_paths, "gt": None, "gt_fn": fr.gt_fn,
              "pilot": fr.fid in exclude}
        frame_dicts.append(fd)
        all_cands.extend(cands)
        if verbose and (i + 1) % 50 == 0:
            log.info("M1 %d/%d frame, %d candidates", i + 1, len(frames_raw), len(all_cands))

    _split_scenes(frame_dicts, cfg.split.val_frac, cfg.split.seed)
    frames = {f["fid"]: f for f in frame_dicts}
    for c in all_cands:
        c["split"] = frames[c["fid"]]["split"]

    # --- GT gắn tạm (chỉ M6/tune dùng) ---
    for fd in frame_dicts:
        if fd["gt_fn"] is not None:
            fd["gt"] = fd["gt_fn"]()

    # --- M2: raw + fit shape trên V ---
    v_cands = [c for c in all_cands if c["split"] == "V"]
    m2_object_score.score_candidates(all_cands, cfg.obj, v_cands)

    # --- aggregate điểm vật thể TRƯỚC (frame features cần s_obj) ---
    for split in ("V", "T", "PILOT"):
        csplit = [c for c in all_cands if c["split"] == split]
        m2_object_score.aggregate_object_scores(csplit, cfg.obj)

    # --- M3: frame features + OOD fit trên V ---
    for fd in frame_dicts:
        fd.update(m3_frame_score.frame_raw_features(
            fd, [c for c in all_cands if c["fid"] == fd["fid"]], cfg.frame))
    ood_model = m3_frame_score.fit_ood_reference(frame_dicts, cfg.frame)

    # --- Cổng NGOẠI LAI (trước khi chọn): Hợp lệ / Nghi ngờ / Ngoại lai — không dùng nhãn ---
    cands_by_fid = {}
    for c in all_cands:
        cands_by_fid.setdefault(c["fid"], []).append(c)
    gate_summary, gate_state = outlier_gate.apply_gate(frame_dicts, cands_by_fid, cfg.gate)
    if gate_summary.get("enabled"):
        log.info("Cổng ngoại lai: %s%s", gate_summary["counts"],
                 " | CẢNH BÁO lệch domain" if gate_summary["domain_shift_warning"] else "")

    # --- rank + dedup từng split ---
    artifacts_ranked = {}
    for split in ("V", "T"):
        fsplit = [f for f in frame_dicts if f["split"] == split]
        m3_frame_score.aggregate_frame_scores(fsplit, cfg.frame, ood_model)
        # OOD = CỜ (không cộng điểm khi w_ood = 0): ngưỡng = phân vị của V
        if split == "V":
            v_ood = [f["ood_raw"] for f in fsplit]
            ood_thr = float(np.quantile(v_ood, cfg.gate.ood_flag_q)) if v_ood else float("inf")
        for f in fsplit:
            f["ood_flag"] = int(f["ood_raw"] > ood_thr)
        if tune == "rule_v" and split == "V" and all(f["gt"] is not None for f in fsplit):
            best_w, best_score = {"obj": cfg.frame.w_obj, "crowd": cfg.frame.w_crowd,
                                  "weather": cfg.frame.w_weather, "ood": cfg.frame.w_ood}, -1.0
            from .m6_evaluate import gt_frame_flags
            pos_v = set()
            for f in fsplit:
                if gt_frame_flags(f, cfg.obj, cfg.frame)["rare_frame"]:
                    pos_v.add(f["fid"])
            for wo in (0.5, 1.0, 2.0):
                for wc in (0.5, 1.0, 2.0):
                    for ww in (0.5, 1.0, 2.0):
                        for wdd in ((0.0,) if cfg.frame.w_ood == 0 else (0.5, 1.0, 2.0)):
                            w = {"obj": wo, "crowd": wc, "weather": ww, "ood": wdd}
                            _recompute_frame_scores(fsplit, cfg.frame, w)
                            ranked_all, ranked_kept = m4_aggregate.rank_and_dedup(fsplit, cfg.dedup)
                            top = [f["fid"] for f in ranked_kept[:budget]]
                            rec = sum(1 for f in top if f in pos_v) / max(len(pos_v), 1)
                            if rec > best_score:
                                best_score, best_w = rec, dict(w)
            log.info("tune=rule_v trên V: weights tốt nhất %s (recall@%d=%.3f)",
                     best_w, budget, best_score)
            cfg.frame.w_obj, cfg.frame.w_crowd = best_w["obj"], best_w["crowd"]
            cfg.frame.w_weather, cfg.frame.w_ood = best_w["weather"], best_w["ood"]
            # re-apply lên cả hai split cho nhất quán
            for sp in ("V", "T"):
                fs = [f for f in frame_dicts if f["split"] == sp]
                _recompute_frame_scores(fs, cfg.frame, best_w)
        ranked_all, ranked_kept = m4_aggregate.rank_and_dedup(fsplit, cfg.dedup)
        # M5: chọn top-B theo ngân sách + quota slice — ĐÁNH DẤU (không cắt danh sách:
        # thứ tự đầy đủ vẫn giữ trong CSV để đội gán thấy bối cảnh), cột selected=1
        # là lô khuyến nghị giao gán nhãn.
        # chỉ frame qua cổng (gate_tier 0) mới được chọn; Nghi ngờ → người duyệt; Ngoại lai → loại
        eligible = [f for f in ranked_kept if f.get("gate_tier", 0) == 0]
        selected = m4_aggregate.diversify_select(eligible, budget, cfg.diversity)
        sel_fids = {f["fid"] for f in selected}
        for f in ranked_kept:
            f["selected"] = 1 if f["fid"] in sel_fids else 0
        # Phương án B (chỉ khi công tắc retrain bật): thêm một mẫu NGẪU NHIÊN ngoài lô chọn,
        # cũng gán nhãn và thêm vào train để giữ phân phối chung. Không ảnh hưởng M6.
        mcfg = getattr(cfg, "model", None)
        n_exp = int(round(mcfg.explore_frac * budget)) if (mcfg and mcfg.retrain) else 0
        rest = [f for f in eligible if not f["selected"]]
        exp_fids = set()
        if n_exp > 0 and rest:
            rng_e = np.random.default_rng(cfg.split.seed + 7)
            idx = rng_e.choice(len(rest), size=min(n_exp, len(rest)), replace=False)
            exp_fids = {rest[i]["fid"] for i in idx}
        for f in ranked_kept:
            f["explore"] = 1 if f["fid"] in exp_fids else 0
        artifacts_ranked[split] = (ranked_all, ranked_kept)

    ranked_T_all, ranked_T_kept = artifacts_ranked["T"]
    ranked_V_all, ranked_V_kept = artifacts_ranked["V"]

    gate_corruption = _corruption_test(frames_raw, frame_dicts, cands_by_fid, gate_state, det, cfg, rng)

    artifacts = {
        "gate": {**gate_summary, "corruption_test": gate_corruption},
        "frames": frames,
        "cands": all_cands,
        "ranked_T": ranked_T_kept,
        "ranked_T_all": ranked_T_all,
        "ranked_V": ranked_V_kept,
        "ranked_V_all": ranked_V_all,
        "cfg": cfg,
    }
    m5_select.write_outputs(artifacts, cfg.out_dir, cfg.frame)
    cfg.save_json(os.path.join(cfg.out_dir, "config_used.json"))
    # artifacts cho M6 (run_eval.py) — bỏ gt_fn (closure không pickle được); GT đã materialize
    import pickle
    clean_frames = {fid: {k: v for k, v in fd.items() if k != "gt_fn"}
                    for fid, fd in frames.items()}
    with open(os.path.join(cfg.out_dir, "artifacts.pkl"), "wb") as fh:
        pickle.dump({
            "frames": clean_frames, "cands": artifacts["cands"], "cfg": cfg,
            "gate": artifacts["gate"],
            "ranked_T": [f["fid"] for f in artifacts["ranked_T"]],
            "ranked_T_all": [f["fid"] for f in artifacts["ranked_T_all"]],
        }, fh)
    log.info("Đã ghi outputs vào %s", cfg.out_dir)
    return artifacts
