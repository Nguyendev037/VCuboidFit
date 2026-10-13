"""Pitch figures, always PNG 1600 x 900; no model inference or annotation reads."""

import json
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

from c4.contracts import read_table


def _save(fig, out):
    out = Path(out)
    out.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(out, dpi=100)
    plt.close(fig)
    return out


def plot_iy_budget(curve: pd.DataFrame, out: Path) -> Path:
    fig, ax = plt.subplots(figsize=(16, 9), layout="constrained")
    for method, g in curve.groupby("method", sort=False):
        g = g.sort_values("frac")
        x = g["frac"].to_numpy(float) * 100
        ax.plot(x, g["iy"], "--" if method == "oracle" else "-o", label=method)
        if method != "oracle":
            ax.fill_between(x, g["lo"].to_numpy(float), g["hi"].to_numpy(float), alpha=0.12)
    mode = curve.attrs.get("mode", "pool")
    ax.set(
        title=f"IY@B · capture B (rare form) · {mode}"
        + (" · illustrative · in-sample" if mode == "mini" else ""),
        xlabel="Budget (%)",
        ylabel="Unique rare instances / selected frames",
        xticks=[1, 2, 5, 10],
    )
    ax.grid(alpha=0.2)
    ax.legend()
    return _save(fig, out)


def plot_context_coverage(cov: pd.DataFrame, base: dict[str, float], out: Path) -> Path:
    fig, axes = plt.subplots(1, 2, figsize=(16, 9), layout="constrained")
    for ax, tags, title in zip(
        axes,
        [("glare_sun",), ("night", "rain")],
        ["Glare* · predicted", "Mini · night/rain · illustrative · in-sample"],
    ):
        sub = cov[cov["axis"].isin(tags)]
        methods = list(sub["method"].unique())
        if sub.empty:
            ax.text(0.5, 0.5, "Not measured", ha="center", transform=ax.transAxes)
        for i, tag in enumerate(tags):
            vals = sub[sub["axis"] == tag].set_index("method")["cov"].reindex(methods)
            ax.bar(
                np.arange(len(methods)) + (i - (len(tags) - 1) / 2) * 0.32,
                vals,
                width=0.3,
                label=tag,
            )
            if tag in base:
                ax.axhline(base[tag], linestyle="--", label=f"{tag} base {base[tag]:.1%}")
        ax.set(title=title, ylabel="Selected fraction", ylim=(0, 1))
        ax.set_xticks(np.arange(len(methods)), methods, rotation=15)
        if not sub.empty:
            ax.legend()
    return _save(fig, out)


def plot_examples(job_dir: Path, sel_new: list[str], sel_old: list[str], k: int, out: Path) -> Path:
    job = Path(job_dir)
    tokens = [t for t in sel_new if t not in set(sel_old)][:k]
    fig, axes = plt.subplots(max(k, 1), 2, figsize=(16, 9), squeeze=False, layout="constrained")
    tags = {}
    for p in sorted(
        (job / "engines" / "rare_v24").glob("*/config_used.json"),
        key=lambda p: p.stat().st_mtime,
        reverse=True,
    ):
        if json.loads(p.read_text(encoding="utf-8"))["profile"] == "multisensor":
            f = read_table(p.parent / "rare_frames.parquet", "rare_frames")
            tags = f.set_index("sample_token")["pred_tags"].to_dict()
            break
    context = {}
    if (job / "cache" / "context_frame.parquet").is_file():
        c = read_table(job / "cache" / "context_frame.parquet", "context_frame")
        for t, g in c.groupby("sample_token"):
            context[t] = ", ".join(sorted(set(g["tag_glare"].dropna()) - {""})) or "none"
    for row in range(max(k, 1)):
        for col, (folder, suffix) in enumerate([("bev", ".png"), ("thumbs", "_CAM_FRONT.webp")]):
            ax = axes[row, col]
            ax.axis("off")
            if row >= len(tokens):
                ax.text(0.5, 0.5, "No additional M3 frame", ha="center", transform=ax.transAxes)
                continue
            t = tokens[row]
            path = job / "media" / folder / (t + suffix)
            if path.is_file():
                ax.imshow(plt.imread(path))
            else:
                ax.text(0.5, 0.5, f"{folder} unavailable", ha="center", transform=ax.transAxes)
            ax.set_title(
                f"{t[:12]} · {'BEV' if col == 0 else 'CAM_FRONT'}\n"
                f"RHCIO predicted: {tags.get(t, '') or 'none'} · "
                f"glare predicted: {context.get(t, 'unavailable')}"
            )
    fig.suptitle("M3 selected, M1 omitted · illustrative examples")
    return _save(fig, out)
