"""Thí nghiệm PDF §6: ma trận run + tune lưới trên V + ablation khối, MỘT script chấm (eval).

Bố cục `<out>/` (một bộ dữ liệu):
  index.parquet · features/{desc_raw.npz, filter.parquet} · gt/{gt_rare_lidar.parquet,
  cell_freq.csv} · t1/{z1.npy, preds_*.pkl, signals.parquet} (nếu Tầng 1 đã chạy) ·
  <split>/<run>/{config.yaml, selected_5pct.csv} · <split>/metrics.json · report_selection.md
"""
import itertools
import json
import subprocess
from dataclasses import dataclass, field
from pathlib import Path

import numpy as np
import pandas as pd
import yaml

from c4.contracts import read_table, write_table
from c4.lidar import eval as ev
from c4.lidar.extract import embed_split, extract_all, load_filter, load_raw
from c4.lidar.score import combine, pct_rank, rarity
from c4.lidar.select import budget, select_coreset, select_mmr, select_random, select_topk
from c4.lidar.uncertainty import load_signals, unc_score


def git_sha() -> str:
    try:
        return subprocess.run(["git", "rev-parse", "HEAD"], capture_output=True, text=True,
                              timeout=5, check=False).stdout.strip()
    except OSError:
        return ""


@dataclass
class Pool:
    """Dữ liệu KHÔNG NHÃN của một split, đã sắp theo index."""
    index: pd.DataFrame
    raw: dict
    keep: np.ndarray
    sig: pd.DataFrame | None = None
    z1: np.ndarray | None = None
    cache: dict = field(default_factory=dict)

    @property
    def scene(self):
        return self.index["scene_token"].to_numpy()

    def z0(self, drop=()):
        key = ("z0", tuple(drop))
        if key not in self.cache:
            self.cache[key] = embed_split(self.raw, self.keep, self.cfg, drop)
        return self.cache[key]

    def rar(self, k, space="z0", drop=()):
        key = ("rar", k, space, tuple(drop))
        if key not in self.cache:
            z = self.z0(drop) if space == "z0" else self.z1
            self.cache[key] = rarity(z, self.scene, k, self.keep)
        return self.cache[key]

    def sub(self, mask) -> "Pool":
        """Pool con theo mặt nạ dòng (dùng cho bootstrap) — tính lại PCA/Rar trên tập con."""
        mask = np.asarray(mask, bool)
        p = Pool(self.index[mask].reset_index(drop=True), {k: v[mask] for k, v in self.raw.items()},
                 self.keep[mask],
                 None if self.sig is None else self.sig[mask].reset_index(drop=True),
                 None if self.z1 is None else self.z1[mask])
        p.cfg = self.cfg
        return p


def prepare(data_root, out: Path, cfg: dict, gcfg: dict, n_jobs: int = -1, log=print) -> None:
    """Chỉ mục + chia tập + descriptor + GT (idempotent: bỏ qua phần đã có)."""
    from c4.data.nusc import NuscTables
    from c4.lidar.gt import build_gt
    from c4.lidar.index import build_lidar_index
    from c4.lidar.splits import assign_splits

    out.mkdir(parents=True, exist_ok=True)
    t = NuscTables.load(data_root)
    ip = out / "index.parquet"
    if ip.is_file():
        index = read_table(str(ip), "lidar_index")
    else:
        index = assign_splits(build_lidar_index(t, data_root), cfg)
        write_table(index, str(ip), "lidar_index", data_root=str(data_root))
    log(f"index: {len(index)} keyframe · " + ", ".join(
        f"{k}={v}" for k, v in index.groupby("split").size().items()))
    if not (out / "features" / "desc_raw.npz").is_file():
        _, filt = extract_all(index, data_root, out / "features", cfg, n_jobs=n_jobs,
                              bev_dir=out / "media" / "bev")
        log(f"descriptor: {int(filt['keep'].sum())}/{len(filt)} frame hợp lệ")
    if t.has_annotations and not (out / "gt" / "gt_rare_lidar.parquet").is_file():
        (out / "gt").mkdir(exist_ok=True)
        gt, cf = build_gt(t, index, gcfg)
        write_table(gt, str(out / "gt" / "gt_rare_lidar.parquet"), "gt_rare_lidar", tau=gcfg["tau"])
        cf.to_csv(out / "gt" / "cell_freq.csv", index=False)
        log(f"gt: {int(gt['is_rare'].sum())} frame rare / {len(gt)}")


def load_pool(out: Path, split: str, cfg: dict) -> Pool:
    full = read_table(str(out / "index.parquet"), "lidar_index")
    mask = (full["split"] == split).to_numpy()
    index = full[mask].reset_index(drop=True)
    sig = load_signals(out / "t1", index) if (out / "t1").is_dir() else None
    z1 = None
    if sig is not None and (out / "t1" / "z1.npy").is_file():
        z1 = np.load(out / "t1" / "z1.npy")[mask]
    p = Pool(index, load_raw(out / "features", index), load_filter(out / "features", index),
             sig, z1)
    p.cfg = cfg
    return p


def scores_for(pool: Pool, k: int, weights, rar_space="z0", drop=()) -> pd.DataFrame:
    a, b, g = weights
    nov = unc = None
    if pool.sig is not None:
        nov = pool.sig["nov"].to_numpy(np.float32)
        unc = unc_score(pool.sig, pool.keep)
    return combine(pool.index, pool.keep, pool.rar(k, rar_space, drop), nov, unc, a, b, g)


def run_matrix(pool: Pool, params: dict, cfg: dict, truth: ev.Truth | None) -> dict:
    """Mọi run của PDF §6.2 có thể chạy với dữ liệu hiện có. Trả {tên: lidar_selected}."""
    B = budget(len(pool.index), cfg["defaults"]["budget"])
    k, lam, m = params["k"], params["lam"], params["m"]
    runs = {}
    for s in cfg["random_seeds"]:
        runs[f"random_{s}"] = select_random(scores_for(pool, k, (1, 0, 0)), B, s)
        runs[f"random_quota_{s}"] = select_random(scores_for(pool, k, (1, 0, 0)), B, s, m=m or B)
    t0 = scores_for(pool, k, (1, 0, 0))
    z = pool.z0()
    runs["coreset_z0"] = select_coreset(t0, z, B)
    runs["t0_rar_topk"] = select_topk(t0, B, method="t0_rar_topk")
    runs["t0_rar_mmr"], _ = select_mmr(t0, z, B, lam, m, method="t0_rar_mmr")
    if pool.sig is not None:
        if pool.z1 is not None:
            r1 = scores_for(pool, k, (1, 0, 0), rar_space="z1")
            runs["t1_rar_mmr"], _ = select_mmr(r1, z, B, lam, m, method="t1_rar_mmr")
        for name, w in (("t1_nov_mmr", (0, 1, 0)), ("t1_unc_mmr", (0, 0, 1))):
            runs[name], _ = select_mmr(scores_for(pool, k, w), z, B, lam, m, w, method=name)
        ent = t0.assign(s=pct_rank(pool.sig["ent"].to_numpy(), pool.keep))
        runs["entropy_only"] = select_topk(ent, B, method="entropy_only")
        w = tuple(params.get("weights", cfg["presets"]["balanced"]))
        runs["hybrid_mmr"], _ = select_mmr(scores_for(pool, k, w), z, B, lam, m, w,
                                           method="hybrid_mmr")
    if truth is not None:
        toks = ev.oracle(truth, B)
        pos = {t: i for i, t in enumerate(pool.index["sample_token"])}
        sc = t0.iloc[[pos[t] for t in toks]].reset_index(drop=True)
        runs["oracle_label"] = sc.assign(method="oracle_label", seed=0,
                                         rank=np.arange(1, len(sc) + 1),
                                         max_sim=0.0, mmr_util=0.0, reason="oracle",
                                         budget_B=B)[list(runs["random_0"].columns)]
    return runs


def criterion(m: dict, truth: ev.Truth, B: int) -> float:
    """Tiêu chí chọn cấu hình chốt trước (PDF §4.5): nRecall trung bình của nhóm B và C."""
    return float(np.mean([m["byGroup"][g] * len(truth.groups[g])
                          / max(min(B, len(truth.groups[g])), 1)
                          for g in ("B", "C")]))


def tune(pool: Pool, cfg: dict, truth: ev.Truth, log=print) -> tuple[dict, list[dict]]:
    """Lưới Tầng 0: k × λ × m (48 cấu hình); nếu có Tầng 1: lưới α,β,γ bước 0.25 (15)."""
    B = budget(len(pool.index), cfg["defaults"]["budget"])
    g, dt = cfg["grid"], ev.delta_t()
    rows = []
    for k, lam, m in itertools.product(g["k"], g["lam"], g["m"]):
        sel, _ = select_mmr(scores_for(pool, k, (1, 0, 0)), pool.z0(), B, lam, m)
        met = ev.metrics(ev.first_B(sel, B), truth, B, dt)
        rows.append(dict(tier=0, k=k, lam=lam, m=m, weights=[1, 0, 0],
                         crit=criterion(met, truth, B), recall=met["recall"]))
    d = cfg["defaults"]

    def near_default(r):  # hoà tiêu chí ⇒ ưu tiên cấu hình gần mặc định (tránh λ=1 tắt đa dạng)
        m = r["m"] if r["m"] is not None else 99
        return -(abs(r["k"] - d["k"]) / 10 + abs(r["lam"] - d["lam"]) + abs(m - d["m"]) / 10)

    best = max((r for r in rows if r["tier"] == 0),
               key=lambda r: (round(r["crit"], 9), round(r["recall"], 9), near_default(r)))
    params = dict(k=best["k"], lam=best["lam"], m=best["m"], weights=[1.0, 0.0, 0.0])
    if pool.sig is not None:
        step = g["weight_step"]
        vals = np.arange(0, 1 + 1e-9, step)
        for a, b in itertools.product(vals, vals):
            c = 1 - a - b
            if c < -1e-9:
                continue
            w = (float(a), float(b), float(max(c, 0)))
            sel, _ = select_mmr(scores_for(pool, params["k"], w), pool.z0(), B, params["lam"],
                                params["m"], w)
            met = ev.metrics(ev.first_B(sel, B), truth, B, dt)
            rows.append(dict(tier=1, k=params["k"], lam=params["lam"], m=params["m"],
                             weights=list(w), crit=criterion(met, truth, B), recall=met["recall"]))
        b1 = max((r for r in rows if r["tier"] == 1), key=lambda r: (r["crit"], r["recall"]))
        params["weights_t1"] = b1["weights"]
    log(f"tune: tốt nhất tầng 0 k={params['k']} λ={params['lam']} m={params['m']} "
        f"(crit {best['crit']:.3f})")
    return params, rows


def ablation_blocks(pool: Pool, params: dict, cfg: dict, truth: ev.Truth) -> dict:
    """Leave-one-block-out cho t0_rar_mmr (PDF §6.3) — chỉ để phân tích."""
    B = budget(len(pool.index), cfg["defaults"]["budget"])
    out = {}
    for blk in ["A", "B", "C", "D", "E"]:
        sc = scores_for(pool, params["k"], (1, 0, 0), drop=(blk,))
        sel, _ = select_mmr(sc, pool.z0((blk,)), B, params["lam"], params["m"])
        out[f"-{blk}"] = ev.metrics(ev.first_B(sel, B), truth, B, ev.delta_t())
    return out


def write_runs(out_dir: Path, runs: dict, params: dict, split: str, cfg: dict) -> None:
    for name, sel in runs.items():
        d = out_dir / name
        d.mkdir(parents=True, exist_ok=True)
        write_table(sel, str(d / "selected_5pct.csv"), "lidar_selected", run=name)
        (d / "config.yaml").write_text(yaml.safe_dump(dict(
            run=name, split=split, params=params, git_sha=git_sha(),
            seeds=cfg["random_seeds"], budget=cfg["defaults"]["budget"]), allow_unicode=True),
            encoding="utf-8")


def fmt_table(res: dict) -> str:
    lines = ["| Run | Recall@5% | nRecall | Uplift | Precision | Scene-Recall | Coverage | "
             "Redundancy | B | B′ | C |", "|---|---|---|---|---|---|---|---|---|---|---|"]

    def row(name, m, sd=None):
        def f(k, sub=None):
            v = m["byGroup"][sub] if sub else m[k]
            s = f"{v:.3f}"
            if sd is not None:
                s += f" ± {(sd['byGroup'][sub] if sub else sd[k]):.3f}"
            return s
        lines.append(f"| {name} | {f('recall')} | {f('nRecall')} | {f('uplift')} | "
                     f"{f('precision')} | {f('sceneRecall')} | {f('coverage')} | "
                     f"{f('redundancy')} | {f(None, 'B')} | {f(None, 'Bp')} | {f(None, 'C')} |")
    if res.get("random"):
        row("random (10 seed)", res["random"]["mean"], res["random"]["std"])
    if res.get("randomQuota"):
        row("random_quota (10 seed)", res["randomQuota"]["mean"], res["randomQuota"]["std"])
    for k, m in res["runs"].items():
        row(k, m)
    return "\n".join(lines)


def report(out: Path, split: str, res: dict, params: dict, tune_rows, abl, ci) -> str:
    p = res["pool"]
    txt = [f"# Báo cáo chọn mẫu — split {split}", "",
           f"Pool N={p['N']} · B={p['B']} · rare={p['rare']} · cell hiếm={p['rareCells']} · "
           f"nhóm {p['groups']} · Recall kỳ vọng của random = {res['expectedRandomRecall']:.3f}",
           f"Tham số: `{json.dumps(params)}` · git `{git_sha()[:10]}`", "", fmt_table(res), ""]
    if ci:
        txt += [f"CI 95% recall t0_rar_mmr (bootstrap scene {ci['frac']:.0%}, n={ci['n']}): "
                f"[{ci['low']:.3f}, {ci['high']:.3f}]", ""]
        if res.get("random"):
            thr = res["random"]["mean"]["recall"] + 2 * res["random"]["std"]["recall"]
            txt += [f"Tiêu chí 'hơn random' (PDF §5.3): cận dưới {ci['low']:.3f} "
                    f"{'>' if ci['low'] > thr else '≤'} mean+2std random {thr:.3f}", ""]
    if abl:
        txt += ["## Ablation khối descriptor (leave-one-block-out, chỉ phân tích)", "",
                "| Bỏ khối | Recall | B | C |", "|---|---|---|---|"]
        txt += [f"| {k} | {m['recall']:.3f} | {m['byGroup']['B']:.3f} | {m['byGroup']['C']:.3f} |"
                for k, m in abl.items()]
        txt.append("")
    if tune_rows:
        top = sorted(tune_rows, key=lambda r: -r["crit"])[:10]
        txt += ["## Tune (10 cấu hình tốt nhất theo tiêu chí nRecall B+C)", "",
                "| tầng | k | λ | m | α,β,γ | tiêu chí | recall |", "|---|---|---|---|---|---|---|"]
        txt += [f"| {r['tier']} | {r['k']} | {r['lam']} | {r['m']} | {r['weights']} | "
                f"{r['crit']:.3f} | {r['recall']:.3f} |" for r in top]
    return "\n".join(txt) + "\n"


def run_split(out: Path, split: str, cfg: dict, params: dict | None, do_tune: bool,
              boot_n: int, log=print) -> dict:
    pool = load_pool(out, split, cfg)
    gt_p = out / "gt" / "gt_rare_lidar.parquet"
    gt = read_table(str(gt_p), "gt_rare_lidar") if gt_p.is_file() else None
    truth = ev.Truth(gt, pool.index) if gt is not None else None
    tune_rows, abl, ci = [], {}, None
    if params is None:
        d = cfg["defaults"]
        params = dict(k=d["k"], lam=d["lam"], m=d["m"], weights=[1.0, 0.0, 0.0])
    if do_tune and truth is not None:
        params, tune_rows = tune(pool, cfg, truth, log)
    if "weights_t1" in params:
        params["weights"] = params.pop("weights_t1")
    runs = run_matrix(pool, params, cfg, truth)
    B = budget(len(pool.index), cfg["defaults"]["budget"])
    sdir = out / split
    write_runs(sdir, runs, params, split, cfg)
    res = ev.evaluate_runs(runs, truth, B, ev.delta_t()) if truth is not None else {}
    if truth is not None:
        abl = ablation_blocks(pool, params, cfg, truth)
        if boot_n:
            def run_fn(sub_index):
                m = pool.index["sample_token"].isin(set(sub_index["sample_token"])).to_numpy()
                sp = pool.sub(m)
                Bs = budget(len(sp.index), cfg["defaults"]["budget"])
                sel, _ = select_mmr(scores_for(sp, params["k"], (1, 0, 0)), sp.z0(), Bs,
                                    params["lam"], params["m"])
                return ev.first_B(sel, Bs)
            ci = ev.bootstrap_ci(run_fn, pool.index, lambda s: ev.Truth(gt, s),
                                 cfg["defaults"]["budget"], ev.delta_t(), boot_n,
                                 cfg["bootstrap"]["seed"])
        res.update(params=params, ci95_t0=ci, ablation_blocks=abl, tune=tune_rows)
        (sdir / "metrics.json").write_text(json.dumps(res, indent=1, ensure_ascii=False),
                                           encoding="utf-8")
        (sdir / "report_selection.md").write_text(report(out, split, res, params, tune_rows,
                                                         abl, ci), encoding="utf-8")
    return dict(params=params, metrics=res, B=B)
