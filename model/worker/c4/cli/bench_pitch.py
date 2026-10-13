"""Pitch benchmark: mini is illustrative/in-sample; pool opens T once. Exit 0/2/3/1."""

import argparse
import hashlib
import json
import re
import sys
import time
from pathlib import Path

import numpy as np
import pandas as pd

from c4.contracts import ContractError, read_table, write_table
from c4.data.nusc import NuscTables
from c4.lidar import load_lidar_config
from c4.lidar.extract import load_filter
from c4.lidar.params import LidarParams, resolve
from c4.lidar.pipeline import run_selection_lidar
from c4.lidar.score import combine, rarity
from c4.lidar.select import select_mmr
from c4.rare.config import load_rare_def
from c4.rare.eval import (
    bootstrap_fixed,
    budget,
    context_coverage,
    evaluate,
    metrics,
    normalized_yield,
    paired_ci,
    random_selector,
    target_frames,
)
from c4.rare.gt_rhcio import (
    RareDefNotFrozen,
    base_rates,
    fit_reference,
    frame_context,
    label_gt,
    load_boxes,
)
from c4.rare.pipeline import PredRefTooSmall, run_rare_v24
from c4.rare.plots import plot_context_coverage, plot_examples, plot_iy_budget
from c4.rare.select import rare_selector
from c4.rare.semantic import ConceptRefEmpty, CropsStale

PACKAGE = "11_2026-10-13_clip-context-fleet"
BUILD_ROOT = Path(__file__).resolve().parents[6]
PLAN = BUILD_ROOT / "planning" / PACKAGE
SPEC = PLAN / "specs" / "SPEC-P04-BENCHMARK-PITCH.md"
PREREG_HASH = PLAN / "evidence" / "B1" / "prereg_sha256.txt"
FRACTIONS = (0.01, 0.02, 0.05, 0.10)


class GateError(ValueError):
    pass


def check_prereg():
    # awk normalises CRLF and emits a newline after each block line.
    text = SPEC.read_text(encoding="utf-8")
    match = re.search(r"^```prereg\n(.*?)^```(?:\n|$)", text, re.M | re.S)
    if match is None:
        raise GateError("PREREG_HASH_MISMATCH: missing prereg block")
    actual = hashlib.sha256(match[1].encode("utf-8")).hexdigest()
    expected = re.search(r"^([a-f0-9]{64})\s", PREREG_HASH.read_text(encoding="utf-8"), re.M)
    if expected is None or actual != expected[1]:
        raise GateError("PREREG_HASH_MISMATCH")
    return actual


def _data_root(job, index):
    # The CLI contract needs only J: recover its dataroot from the index manifest/path.
    for p in (
        job / "dataset.json",
        job / "job.json",
        job / "lidar" / "index.parquet.manifest.json",
    ):
        if p.is_file():
            d = json.loads(p.read_text(encoding="utf-8"))
            for key in ("data_root", "dataRoot", "dataroot"):
                if d.get(key):
                    return Path(d[key])
    first = Path(index.iloc[0]["lidar_path"])
    if first.is_absolute():
        return first.parents[2]
    # Published local jobs use these roots; validate the indexed blob before using one.
    for root in (
        job / "data",
        job.parent.parent / "datasets" / job.name,
        Path("H:/"),
        Path("E:/nuscenes_trainval"),
    ):
        if (root / first).is_file():
            return root
    raise FileNotFoundError(f"data root for {first}; use --data-root")


def _legacy(job, index, frac, mode):
    if mode == "mini":
        r = run_selection_lidar(job, LidarParams(tier=0, budget=frac))
        df = read_table(
            job / "out" / "selections" / r["selectionId"] / "selected.csv", "lidar_selected"
        )
        return df[df["method"] == "hybrid"].sort_values("rank")["sample_token"].tolist()
    # Same legacy functions/defaults, restricted to T BEFORE selection (never top-k of all splits).
    cfg = load_lidar_config()
    mask = (index["split"] == "T").to_numpy()
    ix = index[mask].reset_index(drop=True)
    z = np.load(job / "lidar" / "z0.npy")[mask]
    keep = load_filter(job / "lidar", index)[mask]
    p, _ = resolve(LidarParams(tier=0, budget=frac), cfg, [0])
    sc = combine(ix, keep, rarity(z, ix["scene_token"].to_numpy(), p.k, keep), None, None, 1, 0, 0)
    sel, _ = select_mmr(
        sc,
        z,
        budget(len(ix), frac),
        p.lam,
        p.m,
        method="t0_rar_mmr",
        score_norm=cfg.get("mmr_score", "rank"),
    )
    return sel.sort_values("rank")["sample_token"].tolist()


def _context(job, frame, mode):
    tags = {t: [] for t in frame["sample_token"]}
    axes = []
    if (job / "cache" / "context_frame.parquet").is_file():
        ctx = read_table(job / "cache" / "context_frame.parquet", "context_frame")
        for t, g in ctx.groupby("sample_token"):
            # fuse emits "glare_sun"; the pitch spec calls the same tag "sun".
            # Each sample counts once even if several cameras carry the tag.
            if t in tags and g["tag_glare"].isin(["sun", "glare_sun"]).any():
                tags[t].append("glare_sun")
        axes.append("glare_sun")
    if mode == "mini":
        for r in frame.itertuples():
            for a in ("night", "rain"):
                if getattr(r, "c_" + a):
                    tags[r.sample_token].append(a)
        axes += ["night", "rain"]
    return pd.DataFrame(
        {"sample_token": list(tags), "context_tags": ["|".join(v) for v in tags.values()]}
    ), axes


def _holm(boot, pairs, observed):
    tests = []
    for a, b in pairs:
        ci = paired_ci(boot, a, b)
        delta = observed[a] - observed[b]
        # Two-sided centred paired bootstrap test of delta=0; +1 correction.
        noise = (boot[a] - boot[b]).to_numpy() - delta
        p = float((1 + np.sum(np.abs(noise) >= abs(delta))) / (len(noise) + 1))
        tests.append(dict(a=a, b=b, **{**ci, "delta": delta}, p=p))
    running = 0.0
    for rank, test in enumerate(sorted(tests, key=lambda x: x["p"])):
        running = max(running, min(1.0, (len(tests) - rank) * test["p"]))
        test.update(p_holm=running, significant=running < 0.05)
    return tests


def run(job, mode, out, data_root=None):
    prereg = check_prereg()
    report_path = out / "report_pitch.json"
    if mode == "pool":
        if (
            report_path.is_file()
            and json.loads(report_path.read_text(encoding="utf-8")).get("mode") == "pool"
        ):
            raise GateError("T_ALREADY_OPENED")
        # Fail closed before accessing labels or calling any selector.
        for p in (job / "gt" / "freeze_manifest.json", job / "final_config.json"):
            if not p.is_file():
                raise RareDefNotFrozen(f"missing {p}")
    index = read_table(job / "lidar" / "index.parquet", "lidar_index")
    if index.empty:
        raise FileNotFoundError("empty lidar/index.parquet")
    root = Path(data_root) if data_root else _data_root(job, index)
    tables = NuscTables.load(root)
    pool_split, ref_split = ("all", "all") if mode == "mini" else ("T", "V")
    ref_tokens = (
        index["sample_token"]
        if mode == "mini"
        else index.loc[index["split"] == "V", "sample_token"]
    )
    pool = (
        index["sample_token"].tolist()
        if mode == "mini"
        else index.loc[index["split"] == "T", "sample_token"].tolist()
    )
    if not pool or len(ref_tokens) == 0:
        raise FileNotFoundError("empty pool/reference split")
    cfg, cfg_sha = load_rare_def()
    ref = fit_reference(load_boxes(tables, ref_tokens), frame_context(tables, ref_tokens), cfg)
    if mode == "pool":
        vf, _ = label_gt(tables, ref_tokens, ref, cfg)
        rate = base_rates(vf)["r2_combo"]
        if rate["rate"] > cfg.base_rate_cap or rate["scenes"] < cfg.min_support_scenes:
            raise GateError(f"BaseRateTooHigh: {rate}")
    frame, inst = label_gt(
        tables, pool, ref, cfg, split=dict(zip(index["sample_token"], index["split"]))
    )
    out.mkdir(parents=True, exist_ok=True)
    write_table(frame, out / "gt_rhcio_frame.parquet", "gt_rhcio_frame")
    write_table(inst, out / "gt_rhcio_instance.parquet", "gt_rhcio_instance")
    tf = target_frames(inst, capture="rare_form", gt_frame=frame)
    timings, selectors, configs = {}, {}, {}
    for method, profile in (("M2", "lidar_only"), ("M3", "multisensor")):
        start = time.perf_counter()
        try:
            r = run_rare_v24(job, root, profile=profile, pool_split=pool_split, ref_split=ref_split)
        except FileNotFoundError as e:
            if method != "M3":
                raise
            selectors[method] = None
            configs[method] = {"status": "chưa đo", "reason": str(e)}
        else:
            selectors[method] = rare_selector(r["ranking"])
            configs[method] = json.loads(
                (r["selection_dir"] / "config_used.json").read_text(encoding="utf-8")
            )
        timings[method] = time.perf_counter() - start
    ctx, axes = _context(job, frame, mode)
    curve, primary, selections, cov_rows = [], None, {}, []
    for frac in FRACTIONS:
        B = budget(len(pool), frac)
        start = time.perf_counter()
        legacy = _legacy(job, index, frac, mode)
        legacy_time = time.perf_counter() - start
        sels = {"M1": legacy, **{m: s(pool, B) for m, s in selectors.items() if s is not None}}
        # M0 is the mean over 100 selections, including each paired bootstrap replicate.
        start = time.perf_counter()
        random_sels = {f"random{s}": random_selector(s)(pool, B) for s in range(100)}
        random_time = time.perf_counter() - start
        boot = bootstrap_fixed(
            {**sels, **random_sels}, frame, target_frames(inst), capture="rare_form"
        )
        boot["M0"] = boot[list(random_sels)].mean(axis=1)
        rep = evaluate(
            {m: (lambda p, b, sel=sel: sel) for m, sel in sels.items()},
            frame,
            inst,
            frac=frac,
            capture="rare_form",
        )
        a_rep = evaluate(
            {m: (lambda p, b, sel=sel: sel) for m, sel in sels.items()},
            frame,
            inst,
            frac=frac,
            capture="any",
        )
        rand_metrics = [metrics(s, frame, tf) for s in random_sels.values()]
        random_m = {k: float(np.mean([r[k] for r in rand_metrics])) for k in rand_metrics[0]}
        random_m.update(
            ny=normalized_yield(random_m["iy"], rep["random"]["iy"], rep["oracle"]["iy"])
        )
        any_tf = target_frames(inst)
        random_a = float(np.mean([metrics(s, frame, any_tf)["iy"] for s in random_sels.values()]))
        methods = {"M0": random_m, **rep["methods"]}
        for m, metric in methods.items():
            lo, hi = np.percentile(boot[m], [2.5, 97.5])
            metric.update(
                ci95=[float(lo), float(hi)],
                iy_a=random_a if m == "M0" else a_rep["methods"][m]["iy"],
                time_s=random_time if m == "M0" else legacy_time if m == "M1" else timings[m],
            )
            curve.append(
                dict(method=m, frac=frac, B=B, iy=metric["iy"], lo=float(lo), hi=float(hi))
            )
        curve.append(
            dict(method="oracle", frac=frac, B=B, iy=rep["oracle"]["iy"], lo=None, hi=None)
        )
        if frac == 0.05:
            selections = sels
            ci = paired_ci(boot, "M2", "M1")
            ci["delta"] = methods["M2"]["iy"] - methods["M1"]["iy"]
            pairs = [("M2", "M0")] + ([("M3", "M2")] if "M3" in methods else [])
            primary = dict(
                B=B,
                methods=methods,
                oracle=rep["oracle"],
                primary_delta=ci,
                secondary=_holm(boot, pairs, {m: v["iy"] for m, v in methods.items()}),
                conclusion="shown"
                if mode == "pool" and ci["lo"] > 0
                else "not shown / underpowered",
                n_target_instances=rep["n_target_instances"],
            )
            for m in methods:
                if m == "M0":
                    cvs = [context_coverage(s, ctx, axes) for s in random_sels.values()]
                    cov = {
                        ax: {
                            key: (
                                None
                                if cvs[0][ax][key] is None
                                else float(np.mean([v[ax][key] for v in cvs]))
                            )
                            for key in ("cov", "base", "lift")
                        }
                        for ax in axes
                    }
                else:
                    cov = context_coverage(sels[m], ctx, axes)
                methods[m]["context"] = cov
                cov_rows += [dict(method=m, axis=ax, **v) for ax, v in cov.items()]
    for m in ("M0", "M1", "M2", "M3"):
        if m not in primary["methods"]:
            primary["methods"][m] = {"status": "chưa đo", **configs[m]}
    report = dict(
        mode=mode,
        label="mini · minh hoạ · in-sample" if mode == "mini" else "T pool",
        capture_primary="rare_form",
        capture_secondary="any",
        prereg_sha256=prereg,
        rare_def_sha256=cfg_sha,
        reference_sha256=ref.sha256,
        pool=len(pool),
        scenes=frame["scene_token"].nunique(),
        bootstrap=dict(n_boot=1000, seed=20261013, fixed_selections=True),
        **primary,
        selections=selections,
        curve=curve,
        config_used=configs,
        context_labels={"glare_sun": "predicted", "night/rain": "mini illustrative only"},
    )
    if mode == "pool":
        report["final_config_sha256"] = hashlib.sha256(
            (job / "final_config.json").read_bytes()
        ).hexdigest()
        report["freeze_manifest_sha256"] = hashlib.sha256(
            (job / "gt" / "freeze_manifest.json").read_bytes()
        ).hexdigest()
    report_path.write_text(
        json.dumps(report, ensure_ascii=False, indent=2, default=int, allow_nan=False),
        encoding="utf-8",
    )
    lines = [
        f"# {report['label']}",
        "",
        "Capture B = rare form (primary); A = any visible frame (secondary).",
        "Oracle is a NY reference only. Glare* is predicted.",
        "",
        "| Method | IY@B (B) | IY@B (A) | CI95 (B) | NY@B | cov glare* | Time (s) |",
        "|---|---:|---:|---|---:|---:|---:|",
    ]
    for m, v in primary["methods"].items():
        if "iy" not in v:
            lines.append(f"| {m} | chưa đo | — | — | — | — | — |")
            continue
        glare = v.get("context", {}).get("glare_sun", {}).get("cov")
        lines.append(
            f"| {m} | {v['iy']:.4f} | {v['iy_a']:.4f} | {v['ci95']} | "
            f"{v['ny']} | {glare} | {v['time_s']:.3f} |"
        )
    lines += [
        "",
        f"B={primary['B']}; primary M2−M1: {primary['primary_delta']}",
        f"Secondary (Holm): {primary['secondary']}",
        f"Conclusion: {primary['conclusion']}.",
    ]
    (out / "bench_table.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    cdf = pd.DataFrame(curve)
    cdf.attrs["mode"] = mode
    plot_iy_budget(cdf, out / "fig_iy_budget.png")
    cov_df = pd.DataFrame(cov_rows, columns=["method", "axis", "cov", "base", "lift"])
    bases = cov_df.groupby("axis")["base"].first().to_dict()
    plot_context_coverage(cov_df, bases, out / "fig_context.png")
    plot_examples(job, selections.get("M3", []), selections["M1"], 3, out / "fig_examples.png")
    print(f"{report['label']}: N={len(pool)} B={primary['B']} -> {out}")
    return 0


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--job-dir", required=True, type=Path)
    ap.add_argument("--mode", required=True, choices=("mini", "pool"))
    ap.add_argument("--out", required=True, type=Path)
    ap.add_argument("--data-root", type=Path, help="optional override of indexed dataset root")
    args = ap.parse_args(argv)
    try:
        return run(args.job_dir, args.mode, args.out, args.data_root)
    except (GateError, RareDefNotFrozen, PredRefTooSmall, ConceptRefEmpty) as e:
        print(f"{type(e).__name__}: {e}", file=sys.stderr)
        return 3
    except (FileNotFoundError, ContractError, CropsStale) as e:
        print(f"missing/invalid input: {e}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
