"""Chọn 5% cho web trên một job LiDAR (sau stage lidar_index + t0). KHÔNG đọc nhãn: phần chấm bằng
nhãn nằm ở `web_scoring`, ghép hai phần ở `web_run.run_lidar_selection` (test_no_leakage_lidar).

Bố cục job: lidar/{index.parquet, filter.parquet, z0.npy, desc_raw.npz} · media/bev/*.png ·
t1/signals.parquet (nếu đã chạy Tầng 1) · out/selections/<sid>/{result.json, scores.parquet,
selected.csv}.
"""
import hashlib
import json
from dataclasses import asdict, dataclass, field
from pathlib import Path

import numpy as np
import pandas as pd

from c4.analysis.overview import duplicate_groups
from c4.contracts import read_table
from c4.lidar import load_lidar_config
from c4.lidar.extract import load_filter
from c4.lidar.params import LidarParams, params_schema, resolve
from c4.lidar.scoring import combine_scores, rarity
from c4.lidar.selectors import (
    budget,
    l2_normalize,
    select_coreset,
    select_mmr,
    select_random,
    select_topk,
)
from c4.lidar.t1_signals import load_signals, unc_score

PREVIEW_N = 12
DUP_THETA = 0.95


def available_tiers(job: Path) -> list[int]:
    return [0, 1] if (job / "t1" / "signals.parquet").is_file() else [0]


def params_schema_for_job(job: Path, cfg=None) -> dict:
    return params_schema(cfg or load_lidar_config(), available_tiers(Path(job)))


def pool_mask(index: pd.DataFrame, tier: int) -> np.ndarray:
    """Dòng thuộc pool để chọn: Tầng 1 bỏ tập seed S (đã có nhãn); Tầng 0 lấy toàn bộ."""
    if tier == 1:
        return (index["split"] != "S").to_numpy(bool)
    return np.ones(len(index), bool)


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


def _count_pct(n, total):
    return {"count": int(n), "pct": round(float(n) / max(total, 1), 6)}


@dataclass
class WebSelection:
    """Kết quả chọn chưa có phần chấm nhãn. `cached` ≠ None ⇒ đã có result.json cho sid này."""
    sid: str
    out: Path
    result: dict
    runs: dict
    index: pd.DataFrame
    in_pool: np.ndarray
    B: int
    sc: pd.DataFrame
    cached: dict | None = field(default=None)

    def save(self, result: dict) -> None:
        from c4.contracts import write_table
        from c4.pipeline import _atomic_json

        self.out.mkdir(parents=True, exist_ok=True)
        self.sc.to_parquet(self.out / "scores.parquet", index=False)
        write_table(pd.concat(self.runs.values(), ignore_index=True),
                    str(self.out / "selected.csv"), "lidar_selected", selection_id=self.sid)
        _atomic_json(result, self.out / "result.json")


def select_for_web(job_dir, params: LidarParams, cfg=None) -> WebSelection:
    job = Path(job_dir)
    cfg = cfg or load_lidar_config()
    avail = available_tiers(job)
    r, warnings = resolve(params, cfg, avail)
    fp = _fingerprint(job)
    sid = hashlib.sha1(f"lidar|{json.dumps(asdict(r), sort_keys=True)}|{fp}".encode()) \
        .hexdigest()[:12]
    out = job / "out" / "selections" / sid
    if (out / "result.json").is_file():
        cached = json.loads((out / "result.json").read_text(encoding="utf-8"))
        return WebSelection(sid, out, cached, {}, None, None, 0, None, cached=cached)

    index = read_table(str(job / "lidar" / "index.parquet"), "lidar_index")
    keep = load_filter(job / "lidar", index)
    z = np.load(job / "lidar" / "z0.npy")
    scene = index["scene_token"].to_numpy()
    # Tầng 1: frame seed S đã có nhãn (model train trên chúng, Nov = 0) ⇒ không phải ứng viên và
    # không tính vào ngân sách B (Q1a: cả hai tầng chọn B frame từ pool, không gồm S). Tầng 0 chọn
    # trên toàn bộ dữ liệu người dùng nạp.
    in_pool = pool_mask(index, r.tier)
    if not in_pool.all():
        warnings.append(f"Tầng 1: bỏ {int((~in_pool).sum())} frame seed (đã có nhãn) khỏi danh "
                        "sách ứng viên")
    cand = keep & in_pool
    rar = _cached(job, f"rar_k{r.k}", fp, lambda: rarity(z, scene, r.k, keep))
    sig = load_signals(job / "t1", index) if r.tier == 1 else None
    nov = sig["nov"].to_numpy(np.float32) if sig is not None else None
    unc = unc_score(sig, cand) if sig is not None else None
    w = (r.alpha, r.beta, r.gamma)
    sc = combine_scores(index, cand, rar, nov, unc, *w)
    N = int(in_pool.sum())
    B = budget(N, r.budget)
    hybrid, w2 = select_mmr(sc, z, B, r.lam, r.m, w, method="hybrid",
                            score_norm=cfg["mmr_score"])
    warnings += w2
    runs = {"hybrid": hybrid,
            "t0_rar_topk": select_topk(combine_scores(index, cand, rar, None, None, 1, 0, 0), B,
                                       method="t0_rar_topk"),
            "coreset_z0": select_coreset(sc, z, B),
            "hybrid_nodiv": select_topk(sc, B, method="hybrid_nodiv", weights=w)}
    if sig is not None:
        for name, ww in (("t1_nov_mmr", (0, 1, 0)), ("t1_unc_mmr", (0, 0, 1))):
            runs[name], _ = select_mmr(combine_scores(index, cand, rar, nov, unc, *ww), z, B, r.lam,
                                       r.m, ww, method=name, score_norm=cfg["mmr_score"])
    for s in cfg["random_seeds"]:
        runs[f"random_{s}"] = select_random(sc, B, s)
        runs[f"random_quota_{s}"] = select_random(sc, B, s, m=r.m or B)

    groups = _cached(job, "dup_groups", fp, lambda: duplicate_groups(l2_normalize(z), DUP_THETA))
    analysis = _analysis(index, sc, keep, in_pool, job, hybrid, B, groups, r)
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
                  metrics=None, preview=preview, analysis=analysis)
    return WebSelection(sid, out, result, runs, index, in_pool, B, sc)


def _analysis(index, sc, keep, in_pool, job: Path, hybrid, B, groups, r) -> dict:
    N = int(in_pool.sum())
    filt = read_table(str(job / "lidar" / "filter.parquet"), "lidar_filter")
    pool_tokens = set(index.loc[in_pool, "sample_token"])
    reasons = filt[filt["sample_token"].isin(pool_tokens)]["reason"].value_counts()
    k = keep & in_pool
    groups_pool = groups[in_pool]
    too_safe = k & (sc["r_rar"].to_numpy() <= 0.3) & (sc["r_nov"].to_numpy() <= 0.3)
    easy = k & (sc["r_unc"].to_numpy() <= 0.2) if r.tier == 1 else np.zeros(len(index), bool)
    S = sc["s"].to_numpy(np.float64)
    n_high = int((S[k] >= np.percentile(S[k], 90)).sum()) if k.any() else 0
    tok = index["sample_token"].to_numpy()
    grp_of = dict(zip(tok, groups))
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
                 "duplicates": {"frames": _count_pct(N - len(np.unique(groups_pool)), N),
                                "groups": int(sum(c > 1 for c in
                                                  np.unique(groups_pool, return_counts=True)[1]))},
                 "tooSafe": _count_pct(too_safe.sum(), N), "easy": _count_pct(easy.sum(), N),
                 "unlabelable": {"total": _count_pct((~keep & in_pool).sum(), N), "dark": 0,
                                 "blurry": 0,
                                 "noObjects": int(reasons.get("few_points", 0)),
                                 "readError": int(reasons.get("read_error", 0))},
                 "excludedByCamera": _count_pct(0, N), "highValue": _count_pct(n_high, N),
                 "rareGt": None},
        "selected": {"scenesCovered": int(top["scene_token"].nunique()), "reasons": kinds,
                     "duplicatesInSelection": dup_in},
        "histogram": {"bins": [round(float(b), 6) for b in bins],
                      "counts": [int(c) for c in counts], "budgetThreshold": round(thr, 6)},
        "tags": tags,
    }
