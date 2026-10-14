"""M2c · `run_rare_v24`: ứng viên -> cổng -> chấm điểm -> chọn B frame (planning/11 SPEC-P05 §8 + §14.1).
Phía CHỌN: KHÔNG đọc nhãn/GT. Nhãn chỉ qua `c4.rare.eval` ở phía đo."""
import hashlib
import json
import os
import time
from pathlib import Path

import numpy as np
import pandas as pd

from c4.contracts import _git_sha, read_table, write_table
from c4.lidar import load_lidar_config
from c4.lidar.extract import load_filter
from c4.lidar.uncertainty import load_signals
from c4.rare.calib import calib_sha256, lidar_to_ego
from c4.rare.candidates import build_candidates, load_class_map
from c4.rare.config import load_candidate_cfg, load_rare_def
from c4.rare.eval import budget
from c4.rare.frame_score import frame_scores
from c4.rare.gate import gate_all
from c4.rare.object_score import fit_pred_reference, fuse_semantic, score_objects
from c4.rare.select import select_rare
from c4.rare.semantic import CROP_FILES, check_crops, semantic_scores

DEFAULT_SCORING = {
    "w_shape": 0.15, "w_slice": 0.35, "w_vru": 0.30, "w_unc": 0.20,   # SPEC-P05 §5.2
    "w_obj": 0.70, "w_crowd": 0.15, "w_ctx": 0.15,                     # SPEC-P05 §6.1
    "gate_ood_sigma": 3.0, "iou_thr": 0.3, "d_max": 1.5, "v_max": 3.0,
    "mmr_lambda": 0.7, "quota_m": "even", "min_ref_vru": 50, "w_sem": 0.20,
}
PROFILES = ("lidar_only", "multisensor")
SPLITS_POOL = ("T", "V", "all")
SPLITS_REF = ("V", "all")


class PredRefTooSmall(ValueError):
    """Tập ref_split có < min_ref_vru object VRU (CLI exit 3 PRED_REF_TOO_SMALL)."""


def _fingerprint(job: Path) -> str:
    parts = []
    for rel in ("lidar/index.parquet", "lidar/z0.npy", "lidar/filter.parquet", "t1/preds_orig.pkl"):
        f = job / rel
        parts.append(f"{rel}:{f.stat().st_size}:{f.stat().st_mtime_ns}" if f.is_file() else rel)
    return "|".join(parts)


def run_rare_v24(job_dir, data_root, *, profile: str = "lidar_only", budget_frac: float = 0.05,
                 pool_split: str = "T", ref_split: str = "V", scoring: dict | None = None) -> dict:
    """-> {selection_dir, selected, ranking, B, modelMode, warnings, ...}. Thiếu đầu vào -> FileNotFoundError."""
    t_start = time.time()
    if profile not in PROFILES or pool_split not in SPLITS_POOL or ref_split not in SPLITS_REF:
        raise ValueError(f"tham số lạ: profile={profile} pool_split={pool_split} ref_split={ref_split}")
    job, root = Path(job_dir), Path(data_root)
    sc = {**DEFAULT_SCORING, **(scoring or {})}
    need = [job / "lidar" / n for n in ("index.parquet", "z0.npy", "filter.parquet")]
    if profile == "multisensor":  # SPEC-P06 §5: thiếu => lỗi, KHÔNG suy biến âm thầm về lidar_only
        need += [job / "cache" / n for n in ("context_frame.parquet",) + CROP_FILES]
    miss = [p.relative_to(job).as_posix() for p in need if not p.is_file()]
    if miss:
        raise FileNotFoundError(', '.join(miss))
    cfg = load_lidar_config()
    rare_cfg, rare_sha = load_rare_def()
    cand_cfg, cand_sha = load_candidate_cfg()
    class_map = load_class_map()
    index = read_table(job / "lidar" / "index.parquet", "lidar_index")
    keep = load_filter(job / "lidar", index)
    z0 = np.load(job / "lidar" / "z0.npy")
    has_pp = (job / "t1" / "preds_orig.pkl").is_file()
    mode = "cluster+pp_frozen" if has_pp else "cluster_only"

    calib = lidar_to_ego(root, index["sample_token"], job / "cache" / "lidar_calib.parquet")
    pre_warn = [] if len(calib) == len(index) else ["LIDAR_CALIB_MISSING"]  # thiếu => giữ hành vi cũ (hệ cảm biến)
    cand = build_candidates(job, root, cfg, rare_cfg, class_map, sc, lidar_calib=calib,
                            cand_cfg=cand_cfg)
    gate_df = gate_all(cand, index, z0, keep, {"gate_ood_sigma": sc["gate_ood_sigma"], "min_pts": rare_cfg.min_pts})

    split = index["split"].to_numpy()
    ref_mask = keep & ((split == ref_split) if ref_split != "all" else np.ones(len(index), bool))
    ref_tokens = set(index["sample_token"][ref_mask])
    ref_obj = cand[cand["sample_token"].isin(ref_tokens)]
    n_vru = int((ref_obj["cls_pred"] != "other").sum())
    if n_vru < sc["min_ref_vru"]:
        raise PredRefTooSmall(f"PRED_REF_TOO_SMALL: ref_split={ref_split} có {n_vru} object VRU < {sc['min_ref_vru']}")
    ref = fit_pred_reference(ref_obj, rare_cfg, n_frames=int(ref_mask.sum()))

    unc = load_signals(job / "t1", index) if has_pp else None
    keep_s = pd.Series(keep, index=index["sample_token"].to_numpy())
    scored = score_objects(cand, ref, unc, keep_s, sc)
    ctx, groups, sem_info = None, None, None
    if profile == "multisensor":
        check_crops(job, cand)  # CropsStale nếu ứng viên đổi sau khi crops
        sem = semantic_scores(job, index, ref_split)
        scored = fuse_semantic(scored, sem, float(sc["w_sem"]))
        ctx = read_table(job / "cache" / "context_frame.parquet", "context_frame")
        cmeta = json.loads((job / "cache" / "concepts_text.json").read_text(encoding="utf-8"))
        groups = dict(zip(cmeta["ids"], cmeta["groups"]))
        sem_info = {"concepts_sha256": cmeta["concepts_sha256"], "n_crops": len(sem),
                    "n_concept_hit": int((sem["concept_top"] != "").sum())}
    frames = frame_scores(scored, gate_df, ctx, index, sc, ref=ref, rare_cfg=rare_cfg, concept_groups=groups)

    pool_mask = np.ones(len(index), bool) if pool_split == "all" else (split == pool_split)
    elig = (frames["gate"] == "valid").to_numpy() & pool_mask
    n_elig = int(elig.sum())
    B = budget(n_elig, budget_frac) if n_elig else 0
    frames = select_rare(frames, scored, z0, index, B, sc, eligible=elig)
    B = int(frames.attrs["B"])
    warnings = pre_warn + list(frames.attrs["warningCodes"])
    ranking = list(frames.attrs["ranking"])

    manifest = {
        "engineVersion": "rare_v24", "profile": profile, "modelMode": mode, "checkpoint_sha256": None,
        "split_manifest_sha256": hashlib.sha256("\n".join(
            f"{t},{s}" for t, s in zip(index["sample_token"], index["split"])).encode()).hexdigest(),
        "rare_def_hash": rare_sha,
        "candidates_cfg_version": cand_cfg.version, "candidates_cfg_sha256": cand_sha,
        "pred_ref_hash": ref.sha256, "freeze_manifest_sha256": None, "seed": 0,
        "budget_frac": budget_frac, "B_resolved": B, "eligible_n": n_elig, "git_sha": _git_sha(),
        "vlm_model_id": None, "pool_split": pool_split, "ref_split": ref_split,
        "scoring_weights": {k: sc[k] for k in ("w_shape", "w_slice", "w_vru", "w_unc", "w_sem")},
        "semantic": sem_info,
        "frame_weights": {k: sc[k] for k in ("w_obj", "w_crowd", "w_ctx")},
        "gate_config": {"ood_sigma": sc["gate_ood_sigma"]},
        "tracker_config": {"d_max": sc["d_max"], "v_max": sc["v_max"]},
        "mmr_config": {"lambda": sc["mmr_lambda"], "quota_m": sc["quota_m"],
                       "quota_m_resolved": frames.attrs.get("quota_m")},
        "candidate_frame": "partial" if pre_warn else "ego",
        "lidar_calib_sha256": calib_sha256(calib),
        "scoring_extra": {"iou_thr": sc["iou_thr"], "min_ref_vru": sc["min_ref_vru"], "ref_vru_only": True},
        "warnings": warnings}
    sid = hashlib.sha1(f"rare_v24|{json.dumps(manifest, sort_keys=True, default=str)}|{_fingerprint(job)}"
                       .encode()).hexdigest()[:12]
    out = job / "engines" / "rare_v24" / sid
    out.mkdir(parents=True, exist_ok=True)
    write_table(scored, out / "rare_objects.parquet", "rare_objects", selection_id=sid)
    write_table(frames, out / "rare_frames.parquet", "rare_frames", selection_id=sid)
    tmp = out / "config_used.json.tmp"
    tmp.write_text(json.dumps(manifest, indent=2, ensure_ascii=False), encoding="utf-8")
    os.replace(tmp, out / "config_used.json")
    sel_tokens = ranking[:B]  # §14.1: selected = ranking[:B], theo thứ tự MMR
    return {"selection_dir": out, "selectionId": sid, "selected": sel_tokens, "ranking": ranking, "B": B,
            "modelMode": mode, "warnings": warnings, "n_objects": len(scored), "n_frames": len(frames),
            "eligible_n": n_elig, "gate_counts": frames["gate"].value_counts().to_dict(),
            "elapsed_s": round(time.time() - t_start, 1)}
