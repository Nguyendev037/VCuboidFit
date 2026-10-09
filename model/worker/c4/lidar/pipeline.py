"""Chọn 5% cho web trên một job LiDAR (sau stage lidar_index + t0). Trả `result.json` cùng hình
dạng pipeline camera + trường LiDAR (01-CONTRACTS §4). Nhãn chỉ đọc qua `eval`.

Bố cục job: lidar/{index.parquet, filter.parquet, z0.npy, desc_raw.npz} · media/bev/*.png ·
gt/gt_rare_lidar.parquet (nếu dataset có nhãn) · t1/signals.parquet (nếu đã chạy Tầng 1) ·
out/selections/<sid>/{result.json, scores.parquet, selected.csv}.
"""
import hashlib
import json
import os
from dataclasses import asdict, replace
from pathlib import Path

import numpy as np
import pandas as pd

from c4.analysis.overview import duplicate_groups
from c4.contracts import read_table, write_table
from c4.lidar import eval as ev
from c4.lidar import load_lidar_config
from c4.lidar.extract import load_filter
from c4.lidar.params import LidarParams, params_schema, resolve
from c4.lidar.score import combine, rarity
from c4.lidar.select import budget, l2n, select_coreset, select_mmr, select_random, select_topk
from c4.lidar.uncertainty import load_signals, unc_score
from c4.pipeline import _atomic_json

PREVIEW_N = 12
DUP_THETA = 0.95


def tier1_machine_ready() -> bool:
    """Khả dụng Tầng 1 là thuộc tính của MÁY (plan 09 D1): thí nghiệm seed có đủ index, cấu hình
    và checkpoint. Không phụ thuộc job nên UI biết trước khi phân tích."""
    exp_s = os.environ.get("VCF_T1_EXP", "").strip()
    if not exp_s:
        return False
    exp = Path(exp_s)
    return all(exp.joinpath(*rel).is_file() for rel in (
        ("index.parquet",), ("t1", "cfg", "pp_seed.yaml"), ("t1", "ckpt", "seed_latest.pth")))


def tier_available(job: Path) -> list[int]:
    """Tầng dùng ĐƯỢC để chọn trên job này: cần t1/signals.parquet của job (kể cả từ máy ngoài)."""
    return [0, 1] if (Path(job) / "t1" / "signals.parquet").is_file() else [0]


def schema(job: Path, cfg=None) -> dict:
    """`tierAvailable` = [0,1] khi máy sẵn sàng (cho MỌI job) hoặc job đã có tín hiệu Tầng 1."""
    avail = [0, 1] if tier1_machine_ready() else tier_available(Path(job))
    return params_schema(cfg or load_lidar_config(), avail)


def _fingerprint(job: Path) -> str:
    parts = []
    for p in ("lidar/z0.npy", "lidar/filter.parquet", "t1/signals.parquet"):
        f = job / p
        parts.append(f"{p}:{f.stat().st_size}:{f.stat().st_mtime_ns}" if f.is_file() else p)
    return "|".join(parts)


def _cached(job: Path, name: str, fp: str, fn):
    key = hashlib.sha1(f"{name}|{fp}".encode()).hexdigest()[:10]
    path = job / "out" / f"{name}_{key}.npy"
    if path.is_file():
        return np.load(path)
    v = fn()
    path.parent.mkdir(parents=True, exist_ok=True)
    np.save(path, v)
    return v


def _cp(n, total):
    return {"count": int(n), "pct": round(float(n) / max(total, 1), 6)}


def _web_metrics(m: dict) -> dict:
    keys = ["recall", "nRecall", "uplift", "precision", "sceneRecall", "coverage",
            "coverageGain", "redundancy", "nBoxes"]
    return {**{k: float(m.get(k, 0.0)) for k in keys}, "byGroup": m["byGroup"]}


def run_selection_lidar(job_dir, params: LidarParams, cfg=None) -> dict:
    job = Path(job_dir)
    cfg = cfg or load_lidar_config()
    has_sig = tier_available(job) == [0, 1]
    avail = [0, 1] if tier1_machine_ready() or has_sig else [0]  # cùng luật với `schema`
    if params.tier is None and not has_sig:
        params = replace(params, tier=0)  # máy sẵn sàng nhưng job chưa chạy t1: mặc định Tầng 0
    elif params.tier == 1 and 1 in avail and not has_sig:
        raise ValueError("tier_unavailable: job chưa có tín hiệu Tầng 1, hãy chạy Tầng 1 trước")
    r, warnings = resolve(params, cfg, avail)
    if r.tier == 1 and has_sig:  # plan 09 D2: tín hiệu Tầng 1 không có nov thật ⇒ β = 0
        mf = job / "t1" / "signals.parquet.manifest.json"
        try:
            nov_src = json.loads(mf.read_text(encoding="utf-8")).get("nov_source")
        except (OSError, ValueError):
            nov_src = None
        if nov_src == "none":
            a, g = r.alpha, r.gamma
            tot = a + g
            a, g = (a / tot, g / tot) if tot > 0 else (1.0, 0.0)
            r = replace(r, alpha=a, beta=0.0, gamma=g)
            warnings = list(warnings) + [
                "Lạ với model không khả dụng (chưa có seed): β đặt về 0, α và γ chuẩn hoá lại"]
    fp = _fingerprint(job)
    sid = hashlib.sha1(f"lidar|{json.dumps(asdict(r), sort_keys=True)}|{fp}".encode()) \
        .hexdigest()[:12]
    out = job / "out" / "selections" / sid
    if (out / "result.json").is_file():
        return json.loads((out / "result.json").read_text(encoding="utf-8"))

    index = read_table(str(job / "lidar" / "index.parquet"), "lidar_index")
    keep = load_filter(job / "lidar", index)
    z = np.load(job / "lidar" / "z0.npy")
    scene = index["scene_token"].to_numpy()
    rar = _cached(job, f"rar_k{r.k}", fp, lambda: rarity(z, scene, r.k, keep))
    sig = load_signals(job / "t1", index) if r.tier == 1 else None
    nov = sig["nov"].to_numpy(np.float32) if sig is not None else None
    unc = unc_score(sig, keep) if sig is not None else None
    w = (r.alpha, r.beta, r.gamma)
    sc = combine(index, keep, rar, nov, unc, *w)
    N = len(index)
    B = budget(N, r.budget)
    hybrid, w2 = select_mmr(sc, z, B, r.lam, r.m, w, method="hybrid",
                            score_norm=cfg.get("mmr_score", "rank"))
    warnings += w2
    runs = {"hybrid": hybrid,
            "t0_rar_topk": select_topk(combine(index, keep, rar, None, None, 1, 0, 0), B,
                                       method="t0_rar_topk"),
            "coreset_z0": select_coreset(sc, z, B),
            "hybrid_nodiv": select_topk(sc, B, method="hybrid_nodiv", weights=w)}
    if sig is not None:
        for name, ww in (("t1_nov_mmr", (0, 1, 0)), ("t1_unc_mmr", (0, 0, 1))):
            runs[name], _ = select_mmr(combine(index, keep, rar, nov, unc, *ww), z, B, r.lam,
                                       r.m, ww, method=name)
    for s in cfg["random_seeds"]:
        runs[f"random_{s}"] = select_random(sc, B, s)
        runs[f"random_quota_{s}"] = select_random(sc, B, s, m=r.m or B)

    gt_path = job / "gt" / "gt_rare_lidar.parquet"
    metrics, truth = None, None
    if gt_path.is_file():
        truth = ev.Truth(read_table(str(gt_path), "gt_rare_lidar"), index)
        res = ev.evaluate_runs(runs, truth, B, ev.delta_t())
        metrics = dict(hybrid=_web_metrics(res["runs"]["hybrid"]),
                       random=({k: _web_metrics(v) for k, v in res["random"].items()}
                               if res["random"] else None),
                       ablation={k: _web_metrics(v) for k, v in res["runs"].items()
                                 if k != "hybrid"},
                       ci95=None)

    groups = _cached(job, "dup_groups", fp, lambda: duplicate_groups(l2n(z), DUP_THETA))
    analysis = _analysis(index, sc, keep, job, hybrid, B, groups, truth, r)
    info = sc.set_index("sample_token")
    names = dict(zip(index["sample_token"], index["scene_name"]))
    preview = []
    for row in hybrid.sort_values("rank").head(PREVIEW_N).itertuples():
        f = info.loc[row.sample_token]
        preview.append(dict(
            rank=int(row.rank), sampleToken=row.sample_token, sceneToken=row.scene_token,
            sceneName=names[row.sample_token], frameIdx=int(f["frame_idx"]), bestCam="LIDAR_TOP",
            S=round(float(row.s), 6), rRar=round(float(f["r_rar"]), 6),
            rNov=round(float(f["r_nov"]), 6), rUnc=round(float(f["r_unc"]), 6), rQry=0.0,
            qryBest="", reason=row.reason, tags=analysis["tags"].get(row.sample_token, []),
            camsAvailable=[]))
    result = dict(selectionId=sid, pipeline="lidar",
                  params={"pipeline": "lidar", **asdict(r), "quotaOff": r.m is None},
                  tierAvailable=avail, poolSize=N, budgetB=B, warnings=warnings,
                  metrics=metrics, preview=preview, analysis=analysis)
    out.mkdir(parents=True, exist_ok=True)
    sc.to_parquet(out / "scores.parquet", index=False)
    write_table(pd.concat(runs.values(), ignore_index=True), str(out / "selected.csv"),
                "lidar_selected", selection_id=sid)
    _atomic_json(result, out / "result.json")
    return result


def _analysis(index, sc, keep, job: Path, hybrid, B, groups, truth, r) -> dict:
    N = len(index)
    filt = read_table(str(job / "lidar" / "filter.parquet"), "lidar_filter")
    reasons = filt["reason"].value_counts()
    k = keep
    too_safe = k & (sc["r_rar"].to_numpy() <= 0.3) & (sc["r_nov"].to_numpy() <= 0.3)
    easy = k & (sc["r_unc"].to_numpy() <= 0.2) if r.tier == 1 else np.zeros(N, bool)
    S = sc["s"].to_numpy(np.float64)
    n_high = int((S[k] >= np.percentile(S[k], 90)).sum()) if k.any() else 0
    tok = index["sample_token"].to_numpy()
    grp_of = dict(zip(tok, groups))
    rare_gt, gt_tags = None, {}
    if truth is not None:
        rare_gt = {"total": _cp(len(truth.rare), N)}
        rare_gt.update({g: _cp(len(v), N) for g, v in truth.groups.items()})
        # tag máy đọc được, khớp chip lọc "Rare GT A/B/C" của web; "rare (cell)" = đúng định nghĩa
        # rare của PDF §5.1, các tag nhóm chỉ nói frame thuộc nhóm nào
        for t in tok:
            hit = [f"Rare GT {g}" for g, v in truth.groups.items() if t in v]
            if t in truth.rare:
                hit.insert(0, "rare (cell)")
            if hit:
                gt_tags[t] = hit
    info = sc.set_index("sample_token")
    tags, first, dup_in = {}, {}, 0
    for row in hybrid.sort_values("rank").itertuples():
        f = info.loc[row.sample_token]
        t = []
        if f["r_rar"] >= 0.8:
            t.append("Hiếm")
        if f["r_nov"] >= 0.8:
            t.append("Lạ với model")
        if f["r_unc"] >= 0.8:
            t.append("Khó")
        gid = grp_of[row.sample_token]
        if gid in first:
            t.append(f"Trùng với #{first[gid]}")
            dup_in += int(row.rank <= B)
        else:
            first[gid] = int(row.rank)
        t.extend(gt_tags.get(row.sample_token, []))
        tags[row.sample_token] = t
    top = hybrid[hybrid["rank"] <= B]
    kinds = {"rarity": 0, "novelty": 0, "uncertainty": 0}
    for text in top["reason"]:
        kinds[str(text).split(" ")[0]] = kinds.get(str(text).split(" ")[0], 0) + 1
    counts, bins = np.histogram(S, bins=np.linspace(0.0, 1.0, 21))
    thr = float(top["s"].min()) if len(top) else 0.0
    return {
        "pool": {"scenes": int(index["scene_token"].nunique()), "frames": N, "images": 0,
                 "imagesByCam": {}, "hasLidar": True,
                 "duplicates": {"frames": _cp(N - len(np.unique(groups)), N),
                                "groups": int(sum(c > 1 for c in
                                                  np.unique(groups, return_counts=True)[1]))},
                 "tooSafe": _cp(too_safe.sum(), N), "easy": _cp(easy.sum(), N),
                 "unlabelable": {"total": _cp((~k).sum(), N), "dark": 0, "blurry": 0,
                                 "noObjects": int(reasons.get("few_points", 0)),
                                 "readError": int(reasons.get("read_error", 0))},
                 "excludedByCamera": _cp(0, N), "highValue": _cp(n_high, N), "rareGt": rare_gt},
        "selected": {"scenesCovered": int(top["scene_token"].nunique()), "reasons": kinds,
                     "duplicatesInSelection": dup_in},
        "histogram": {"bins": [round(float(b), 6) for b in bins],
                      "counts": [int(c) for c in counts], "budgetThreshold": round(thr, 6)},
        "tags": tags,
    }
