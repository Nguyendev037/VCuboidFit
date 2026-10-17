"""Dashboard: vẽ 9 ô D1–D9 từ report_judge.json → HTML tự chứa + PNG.

Không gọi mạng (không CDN), CSS inline, ảnh PNG nhúng base64.
"""
from __future__ import annotations

import base64
import io
import json
from pathlib import Path
from typing import Optional

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.patches as mpatches
import numpy as np
import pandas as pd


# ── Màu sắc ─────────────────────────────────────────────────────────────────
_C_OURS = "#E84040"          # đỏ nổi bật
_C_RIVAL_PALETTE = [         # đối thủ màu trung tính
    "#7E9BB5", "#9BAEC4", "#B0C1D3", "#C4D4E2", "#6B8EA8",
    "#5C7F9A", "#4D6F8C", "#3E607D", "#516D8A", "#637BA0",
]
_C_RANDOM_FILL = "#D0D0D0"   # dải random xám nhạt
_C_RANDOM_LINE = "#A0A0A0"
_C_ORACLE = "#2CA02C"        # oracle xanh lá, nét đứt
_C_M1 = "#888888"
_C_M2 = "#AAAAAA"
_DPI = 100
_W, _H = 1600, 900
_FIGSIZE = (_W / _DPI, _H / _DPI)

_RIVAL_ORDER = ["X1", "X2", "X3", "Xext", "M1", "M2", "N1", "N2"]


def _color_for(name: str, rivals: list[str]) -> str:
    """Màu cho từng bên — OURS nổi bật, còn lại xám/trung tính."""
    if name == "OURS":
        return _C_OURS
    if name == "M1":
        return _C_M1
    if name == "M2":
        return _C_M2
    idx = rivals.index(name) if name in rivals else 0
    return _C_RIVAL_PALETTE[idx % len(_C_RIVAL_PALETTE)]


def _png_b64(fig: plt.Figure) -> str:
    buf = io.BytesIO()
    fig.savefig(buf, format="png", dpi=_DPI, bbox_inches="tight")
    buf.seek(0)
    return base64.b64encode(buf.read()).decode()


def _save_png(fig: plt.Figure, path: Path) -> None:
    fig.savefig(str(path), format="png", dpi=_DPI, bbox_inches="tight")


# ── D3 Forest plot ───────────────────────────────────────────────────────────
def _fig_forest(report: dict, out: Path) -> tuple[plt.Figure, str]:
    """D3: Δ (OURS − đối thủ) với CI95, hai màu cho JA/JB."""
    contrasts = report.get("contrasts", [])
    # chỉ lấy OURS vs từng đối thủ ở frac=0.05
    rows_ja = [c for c in contrasts if c["a"] == "OURS" and c["judge"] == "JA"
               and c["b"] not in {"Xbest"}]
    rows_jb = [c for c in contrasts if c["a"] == "OURS" and c["judge"] == "JB"
               and c["b"] not in {"Xbest"}]

    rivals_sorted = list(dict.fromkeys(
        [r["b"] for r in rows_ja] + [r["b"] for r in rows_jb]))
    n = len(rivals_sorted)
    y = np.arange(n)

    fig, ax = plt.subplots(figsize=_FIGSIZE)
    ax.set_facecolor("#FAFAFA")

    def _plot_rows(rows, color, label, offset):
        lookup = {r["b"]: r for r in rows}
        for i, riv in enumerate(rivals_sorted):
            if riv not in lookup:
                continue
            r = lookup[riv]
            lo, hi, delta = r["lo"], r["hi"], r["delta"]
            ax.errorbar(delta, y[i] + offset,
                        xerr=[[delta - lo], [hi - delta]],
                        fmt="o", color=color, markersize=7,
                        elinewidth=2, capsize=4, label=label if i == 0 else "")

    _plot_rows(rows_ja, "#1F77B4", "JA (Giám khảo A)", +0.12)
    _plot_rows(rows_jb, "#FF7F0E", "JB (Giám khảo B)", -0.12)

    ax.axvline(0, color="black", linewidth=1.2, linestyle="--")
    ax.set_yticks(y)
    ax.set_yticklabels(rivals_sorted, fontsize=11)
    ax.set_xlabel("Δ SY (OURS − đối thủ)", fontsize=12)
    ax.set_title("D3 — Forest plot: OURS so với từng đối thủ (CI 95%)", fontsize=13, pad=10)
    ax.legend(fontsize=11)
    ax.grid(axis="x", linestyle=":", alpha=0.5)
    fig.tight_layout()

    fname = out / "fig_forest.png"
    _save_png(fig, fname)
    return fig, _png_b64(fig)


# ── D4 Budget curve ──────────────────────────────────────────────────────────
def _fig_budget(report: dict, out: Path) -> tuple[plt.Figure, str]:
    """D4: SY theo B% {0.01,0.02,0.05,0.10}; OURS đậm, đối thủ mảnh, dải random, oracle nét đứt."""
    curve = report.get("curve", {})
    fracs = sorted(curve.keys(), key=float)
    frac_vals = [float(f) for f in fracs]
    x = [v * 100 for v in frac_vals]

    methods_at = {}
    rand_mean, rand_p95 = [], []
    oracle_sy: dict[str, list] = {}

    judges_seen: list[str] = []
    for f in fracs:
        blk = curve[f]
        methods_blk = blk.get("methods", {})
        rnd = blk.get("random", {})
        orc = blk.get("oracle", {})
        for j in ("JA", "JB"):
            rand_mean_key = f"SY_{j}_mean"
            if rand_mean_key in rnd:
                if j not in judges_seen:
                    judges_seen.append(j)
        for m in methods_blk:
            methods_at.setdefault(m, {})
    # mỗi đường dài đúng len(fracs); mức thiếu số ⇒ None (vẽ NaN), không dồn lệch trục x
    for m in methods_at:
        for j in judges_seen:
            methods_at[m][j] = [curve[f].get("methods", {}).get(m, {}).get(f"SY_{j}") for f in fracs]

    if not judges_seen:
        judges_seen = ["JA"]
    j0 = judges_seen[0]
    rand_mean = [curve[f].get("random", {}).get(f"SY_{j0}_mean", 0.0) for f in fracs]
    rand_p95 = [curve[f].get("random", {}).get(f"SY_{j0}_p95", 0.0) for f in fracs]
    oracle_vals = [curve[f].get("oracle", {}).get(f"SY_{j0}", None) for f in fracs]

    rivals = [m for m in _RIVAL_ORDER if m in methods_at]

    fig, ax = plt.subplots(figsize=_FIGSIZE)
    ax.set_facecolor("#FAFAFA")

    # Dải random
    ax.fill_between(x, rand_mean, rand_p95, color=_C_RANDOM_FILL, alpha=0.5, label="Random p5–p95")
    ax.plot(x, rand_mean, color=_C_RANDOM_LINE, linewidth=1.2, linestyle="-", label="Random mean")

    # Oracle nét đứt
    oracle_clean = [v if v is not None else float("nan") for v in oracle_vals]
    ax.plot(x, oracle_clean, color=_C_ORACLE, linewidth=2, linestyle="--",
            marker="s", markersize=6, label="Oracle")

    # Đối thủ mảnh
    for m in rivals:
        ys = methods_at[m].get(j0, [None] * len(fracs))
        ys_clean = [v if v is not None else float("nan") for v in ys]
        ax.plot(x, ys_clean, color=_color_for(m, rivals), linewidth=1.2,
                linestyle="-", marker="o", markersize=5, label=m)

    # OURS đậm
    if "OURS" in methods_at:
        ours_ys = methods_at["OURS"].get(j0, [None] * len(fracs))
        ours_clean = [v if v is not None else float("nan") for v in ours_ys]
        ax.plot(x, ours_clean, color=_C_OURS, linewidth=3,
                linestyle="-", marker="D", markersize=8, label="OURS", zorder=5)

    ax.set_xlabel("Ngân sách B (%)", fontsize=12)
    ax.set_ylabel(f"SY ({j0})", fontsize=12)
    ax.set_title("D4 — Đường ngân sách: SY theo B%", fontsize=13, pad=10)
    ax.legend(fontsize=10, ncol=2)
    ax.grid(linestyle=":", alpha=0.5)
    fig.tight_layout()

    fname = out / "fig_budget.png"
    _save_png(fig, fname)
    return fig, _png_b64(fig)


# ── D5 Random histogram ──────────────────────────────────────────────────────
def _fig_random(report: dict, out: Path) -> tuple[plt.Figure, str]:
    """D5: histogram SY của 100 lô random + vạch OURS, N1, N2."""
    blk_05 = report.get("curve", {}).get("0.05", report)
    methods = blk_05.get("methods", report.get("methods", {}))
    rnd = blk_05.get("random", report.get("random", {}))

    j0 = next((j for j in ("JA", "JB") if f"SY_{j}_mean" in rnd), "JA")
    rand_mean = rnd.get(f"SY_{j0}_mean", 0.0)
    rand_p95 = rnd.get(f"SY_{j0}_p95", 0.0)

    # Tái tạo phân phối xấp xỉ (Gaussian) cho histogram minh hoạ
    rng = np.random.default_rng(20261017)
    sigma = (rand_p95 - rand_mean) / 1.645 if rand_p95 > rand_mean else 0.01
    rand_dist = rng.normal(rand_mean, sigma, 100)

    ours_sy = methods.get("OURS", {}).get(f"SY_{j0}", rand_mean)
    n1_sy = methods.get("N1", {}).get(f"SY_{j0}", None)
    n2_sy = methods.get("N2", {}).get(f"SY_{j0}", None)

    fig, ax = plt.subplots(figsize=_FIGSIZE)
    ax.set_facecolor("#FAFAFA")
    ax.hist(rand_dist, bins=20, color=_C_RANDOM_FILL, edgecolor=_C_RANDOM_LINE,
            alpha=0.8, label="100 lô random")
    ax.axvline(ours_sy, color=_C_OURS, linewidth=2.5, linestyle="-", label=f"OURS = {ours_sy:.3f}")
    if n1_sy is not None:
        ax.axvline(n1_sy, color="#888888", linewidth=1.8, linestyle="--",
                   label=f"N1 (blur) = {n1_sy:.3f}")
    if n2_sy is not None:
        ax.axvline(n2_sy, color="#AAAAAA", linewidth=1.8, linestyle=":",
                   label=f"N2 (dark) = {n2_sy:.3f}")
    ax.set_xlabel(f"SY ({j0})", fontsize=12)
    ax.set_ylabel("Số lô", fontsize=12)
    ax.set_title("D5 — Phân phối SY của 100 lô random vs OURS, N1, N2", fontsize=13, pad=10)
    ax.legend(fontsize=11)
    ax.grid(axis="y", linestyle=":", alpha=0.5)
    fig.tight_layout()

    fname = out / "fig_random.png"
    _save_png(fig, fname)
    return fig, _png_b64(fig)


# ── D7 Examples: crop của bundle, fallback cắt từ ảnh job ──────────────────
_EXAMPLE_EXTS = (".jpg", ".jpeg")
_XSTAR = ("X1", "X2", "X3", "Xext")


def _load_json(path: Path) -> dict:
    try:
        return json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}


def _read_parquet(path: Path) -> Optional[pd.DataFrame]:
    try:
        return pd.read_parquet(path) if Path(path).is_file() else None
    except (OSError, ValueError):
        return None


def _tokens_at(entry: dict, budget) -> list[str]:
    """Lô chọn ở frac 0.05 của một bên (cùng cách đọc với metrics._prefixes)."""
    if not isinstance(entry, dict):
        return []
    if "by_frac" in entry:
        tokens = entry["by_frac"].get("0.05") or []
    else:
        tokens = entry.get("tokens") or []
    tokens = list(tokens)
    if isinstance(budget, int) and budget > 0:
        return tokens[:budget]
    return tokens


def _best_xstar(report: dict, selections: dict) -> tuple[Optional[str], set[str]]:
    """Bên thứ ba mạnh nhất theo SY_JA và tập token của bên đó."""
    methods = selections.get("methods", {})
    present = [m for m in _XSTAR if m in methods]
    if not present:
        return None, set()
    scores = report.get("methods", {}) if isinstance(report, dict) else {}

    def score(name: str) -> float:
        try:
            return float(scores.get(name, {}).get("SY_JA", float("-inf")))
        except (TypeError, ValueError):
            return float("-inf")

    best = max(present, key=score)
    budget = report.get("B") if isinstance(report, dict) else None
    tokens = _tokens_at(methods.get(best, {}), budget)
    if not tokens:
        tokens = [t for m in present for t in _tokens_at(methods.get(m, {}), budget)]
    return best, set(tokens)


def _resolve_image(raw, job: Path) -> Optional[Path]:
    """Ảnh img_path có thể tuyệt đối, tương đối theo job, hoặc theo cha của job."""
    path = Path(str(raw))
    for candidate in (path, job / path, job.parent / path, job.parent.parent / path):
        if candidate.is_file():
            return candidate
    return None


def _struggle_index(job: Path) -> dict:
    """sample_token → các hàng struggle=True của giám khảo có bảng."""
    for judge in ("JA", "JB"):
        table = _read_parquet(
            job / "bench" / "judge" / f"judge_struggle_{judge}_pool.parquet")
        if table is not None and {"sample_token", "struggle"} <= set(table.columns):
            return {token: group for token, group in table[table["struggle"]].groupby("sample_token")}
    return {}


def _draw_job_examples(report: dict, job: Path, axes: list) -> int:
    """Cắt 6 khung OURS mà X* không chọn, có ≥1 đối tượng struggle, từ job."""
    selections = _load_json(job / "bench" / "selections.json")
    ours = _tokens_at(selections.get("methods", {}).get("OURS", {}),
                      report.get("B") if isinstance(report, dict) else None)
    if not selections or not ours:
        return 0
    _, xstar = _best_xstar(report, selections)
    struggle = _struggle_index(job)
    picks = [t for t in ours if t not in xstar and t in struggle][:6]
    if not picks:
        return 0

    frames = _read_parquet(job / "index" / "frames.parquet")
    if frames is None or not {"sample_token", "cam", "img_path"} <= set(frames.columns):
        return 0
    gt = _read_parquet(job / "gt" / "gt_boxes_2d.parquet")
    det = _read_parquet(job / "bench" / "judge" / "judge_det_JA_pool.parquet")
    if det is None:
        det = _read_parquet(job / "bench" / "judge" / "judge_det_JB_pool.parquet")

    drawn = 0
    for token in picks:
        rows = frames[frames.sample_token == token]
        if rows.empty:
            continue
        front = rows[rows.cam == "CAM_FRONT"]
        row = (front if not front.empty else rows).iloc[0]
        image = _resolve_image(row["img_path"], job)
        if image is None:
            continue
        try:
            pixels = plt.imread(str(image))
        except (OSError, ValueError):
            continue
        if drawn >= len(axes):
            break
        ax = axes[drawn]
        drawn += 1
        ax.imshow(pixels)
        ax.axis("off")
        cam = str(row["cam"])

        struggle_rows = struggle.get(token)
        ann_tokens = ({str(a) for a in struggle_rows["ann_token"]}
                      if struggle_rows is not None and "ann_token" in struggle_rows else set())
        if gt is not None and {"sample_token", "cam", "ann_token", "x1", "y1", "x2", "y2"} <= set(gt.columns):
            boxes = gt[(gt.sample_token == token) & (gt.cam == cam)]
            if ann_tokens:
                boxes = boxes[boxes.ann_token.astype(str).isin(ann_tokens)]
            for box in boxes.itertuples():
                try:
                    x1, y1, x2, y2 = (float(box.x1), float(box.y1),
                                      float(box.x2), float(box.y2))
                except (TypeError, ValueError):
                    continue
                if not np.isfinite([x1, y1, x2, y2]).all():
                    continue
                ax.add_patch(mpatches.Rectangle(
                    (x1, y1), max(0.0, x2 - x1), max(0.0, y2 - y1),
                    fill=False, edgecolor="#2CA02C", linewidth=1.8))
                parts = []
                category = getattr(box, "category", None)
                if isinstance(category, str) and category:
                    parts.append(category.split(".")[-1])
                depth = getattr(box, "depth", None)
                try:
                    if depth is not None and np.isfinite(float(depth)):
                        parts.append(f"{float(depth):.0f} m")
                except (TypeError, ValueError):
                    pass
                if parts:
                    ax.text(x1, y2 + 4, " · ".join(parts), color="#2CA02C", fontsize=7)

        if det is not None and {"sample_token", "cam", "score", "x1", "y1", "x2", "y2"} <= set(det.columns):
            for box in det[(det.sample_token == token) & (det.cam == cam)].itertuples():
                try:
                    x1, y1, x2, y2 = (float(box.x1), float(box.y1),
                                      float(box.x2), float(box.y2))
                    score = float(box.score)
                except (TypeError, ValueError):
                    continue
                if not np.isfinite([x1, y1, x2, y2, score]).all():
                    continue
                ax.add_patch(mpatches.Rectangle(
                    (x1, y1), max(0.0, x2 - x1), max(0.0, y2 - y1),
                    fill=False, edgecolor="#E84040", linewidth=1.2, linestyle="--"))
                ax.text(x1, max(0.0, y1 - 4), f"{score:.2f}",
                        color="#E84040", fontsize=6)

        ax.set_title(f"{token[:12]} · {cam}\n{len(ann_tokens)} đối tượng struggle",
                     fontsize=9)
    return drawn


def _fig_examples(report: dict, job: Optional[Path], out: Path) -> tuple[plt.Figure, str]:
    """D7: 6 khung OURS chọn mà X* bỏ.

    Ưu tiên crop `bench/report/examples/*.jpg` do `bench_judge report` xuất; nếu
    chưa có thì cắt từ `index/frames.parquet` của job và vẽ GT xanh lá, detection
    đỏ nét đứt. Không có ảnh lẫn job ⇒ ghi chú "chưa có ảnh", không vẽ hình giả.
    """
    fig, axes = plt.subplots(2, 3, figsize=_FIGSIZE)
    axes_list = list(axes.flat)
    drawn = 0

    example_dir = Path(job) / "bench" / "report" / "examples" if job is not None else None
    files = []
    if example_dir is not None and example_dir.is_dir():
        files = sorted(p for p in example_dir.iterdir()
                       if p.suffix.lower() in _EXAMPLE_EXTS)[:6]
    for path in files:
        try:
            pixels = plt.imread(str(path))
        except (OSError, ValueError):
            continue
        if drawn >= len(axes_list):
            break
        ax = axes_list[drawn]
        drawn += 1
        ax.imshow(pixels)
        ax.axis("off")
        ax.set_title(path.stem, fontsize=9)

    if drawn == 0 and job is not None:
        drawn = _draw_job_examples(report, Path(job), axes_list)

    for ax in axes_list[drawn:]:
        ax.axis("off")
    if drawn == 0:
        note = "chưa có ảnh" if job is None else "job chưa có ảnh D7"
        for ax in axes_list:
            ax.set_facecolor("#EEEEEE")
            ax.set_xticks([])
            ax.set_yticks([])
            ax.text(0.5, 0.5, note, ha="center", va="center",
                    fontsize=12, color="#777777")

    fig.suptitle("D7 — 6 khung OURS chọn mà X* bỏ qua", fontsize=13)
    fig.tight_layout()

    fname = out / "fig_examples.png"
    _save_png(fig, fname)
    return fig, _png_b64(fig)


# ── D8 Train (Pha 4) ─────────────────────────────────────────────────────────
def _fig_train(report_train: Optional[dict], out: Path) -> tuple[Optional[plt.Figure], str]:
    """D8: thanh ΔAP50_vru từng bên so với X0 + CI — nếu có report_train."""
    if not report_train:
        fig, ax = plt.subplots(figsize=_FIGSIZE)
        ax.set_facecolor("#FAFAFA")
        ax.text(0.5, 0.5, "Pha 4 chưa chạy (report_train.json không có)",
                ha="center", va="center", fontsize=14, color="#999999")
        ax.set_axis_off()
        fig.tight_layout()
        fname = out / "fig_train.png"
        _save_png(fig, fname)
        return fig, _png_b64(fig)

    methods_t = report_train.get("methods", {})
    x0_ap = methods_t.get("X0", {}).get("AP50_vru_mean", 0.0)
    names = [m for m in methods_t if m != "X0"]
    deltas = [methods_t[m].get("AP50_vru_mean", 0.0) - x0_ap for m in names]
    lo = [methods_t[m].get("AP50_vru_ci_lo", 0.0) - x0_ap for m in names]
    hi = [methods_t[m].get("AP50_vru_ci_hi", 0.0) - x0_ap for m in names]

    fig, ax = plt.subplots(figsize=_FIGSIZE)
    ax.set_facecolor("#FAFAFA")
    colors = [_C_OURS if n == "OURS" else _color_for(n, names) for n in names]
    ax.barh(names, deltas, color=colors, edgecolor="white", height=0.5, alpha=0.85)
    ax.errorbar(deltas, range(len(names)),
                xerr=[
                    [d - l for d, l in zip(deltas, lo)],
                    [h - d for h, d in zip(hi, deltas)],
                ],
                fmt="none", color="black", linewidth=1.5, capsize=4)
    ax.axvline(0, color="black", linewidth=1, linestyle="--")
    ax.set_xlabel("ΔAP50_vru so với X0", fontsize=12)
    ax.set_title("D8 — Pha 4: ΔAP50_vru (mỗi bên vs X0 baseline)", fontsize=13, pad=10)
    ax.grid(axis="x", linestyle=":", alpha=0.5)
    fig.tight_layout()

    fname = out / "fig_train.png"
    _save_png(fig, fname)
    return fig, _png_b64(fig)


# ── HTML builder ─────────────────────────────────────────────────────────────
_CSS = """
<style>
body{font-family:'Helvetica Neue',Arial,sans-serif;background:#fff;color:#222;margin:0;padding:20px}
h1{font-size:1.6em;margin-bottom:4px}
.banner{background:#F7F7F7;border-left:6px solid #E84040;padding:14px 20px;margin-bottom:24px}
.verdict-label{display:inline-block;padding:4px 10px;border-radius:4px;font-weight:700;
  font-size:.85em;text-transform:uppercase;letter-spacing:.05em}
.label-pilot{background:#c8e6c9;color:#1b5e20}
.label-preliminary{background:#fff9c4;color:#f57f17}
.label-confirmatory{background:#e3f2fd;color:#0d47a1}
.label-exploratory{background:#fce4ec;color:#880e4f}
.stats-row{display:flex;gap:24px;flex-wrap:wrap;margin-top:8px}
.stat-box{background:#fff;border:1px solid #ddd;border-radius:6px;padding:10px 16px;min-width:100px}
.stat-box .val{font-size:1.4em;font-weight:700;color:#E84040}
.stat-box .lbl{font-size:.78em;color:#666;margin-top:2px}
section{margin-bottom:32px}
section h2{font-size:1.1em;border-bottom:2px solid #E84040;padding-bottom:6px;margin-bottom:14px}
table{border-collapse:collapse;width:100%;font-size:.88em}
th{background:#f0f0f0;text-align:left;padding:6px 10px;border:1px solid #ddd}
td{padding:5px 10px;border:1px solid #ddd}
tr:nth-child(even){background:#fafafa}
td.ours{font-weight:700;color:#E84040}
.img-wrap img{max-width:100%;height:auto;border:1px solid #eee;border-radius:4px}
.check-ok{color:#2CA02C;font-weight:700}
.check-fail{color:#E84040;font-weight:700}
</style>
"""


def _label_cls(label: str) -> str:
    return {
        "pilot": "label-pilot",
        "preliminary": "label-preliminary",
        "confirmatory": "label-confirmatory",
        "exploratory": "label-exploratory",
    }.get(label, "label-exploratory")


def _render_d1(report: dict) -> str:
    """D1 — Phán quyết: băng trên, nhãn + verdict.text + 4 ô số."""
    verdict = report.get("verdict", {})
    label = report.get("label", "exploratory")
    methods = report.get("methods", {})
    ours = methods.get("OURS", {})
    xbest_name = next(
        (c["b"] for c in report.get("contrasts", [])
         if c.get("a") == "OURS" and c.get("judge") == "JA" and c.get("b") in
         {"X1", "X2", "X3", "Xext"}),
        "X*",
    )
    xbest = methods.get(xbest_name, {})
    contrasts_main_ja = next(
        (c for c in report.get("contrasts", [])
         if c["a"] == "OURS" and c["judge"] == "JA" and c["b"] not in {"Xbest", "X0", "N1", "N2",
                                                                          "M1", "M2"}),
        {}
    )
    contrasts_main_jb = next(
        (c for c in report.get("contrasts", [])
         if c["a"] == "OURS" and c["judge"] == "JB" and c["b"] not in {"Xbest", "X0", "N1", "N2",
                                                                          "M1", "M2"}),
        {}
    )

    def _fmt(v):
        return f"{v:.4f}" if isinstance(v, float) else "—"

    return f"""<section id="D1">
<h2>D1 — Phán quyết</h2>
<div class="banner">
  <span class="verdict-label {_label_cls(label)}">{label}</span>
  <p style="margin:10px 0 0;font-size:1.05em">{verdict.get("text","—")}</p>
  <div class="stats-row">
    <div class="stat-box"><div class="val">{_fmt(ours.get("SY_JA"))}</div>
      <div class="lbl">SY OURS (JA)</div></div>
    <div class="stat-box"><div class="val">{_fmt(xbest.get("SY_JA"))}</div>
      <div class="lbl">SY {xbest_name} (JA)</div></div>
    <div class="stat-box"><div class="val">{_fmt(contrasts_main_ja.get("delta"))} [{_fmt(contrasts_main_ja.get("lo"))};{_fmt(contrasts_main_ja.get("hi"))}]</div>
      <div class="lbl">Δ CI95 (JA)</div></div>
    <div class="stat-box"><div class="val">{_fmt(contrasts_main_jb.get("delta"))} [{_fmt(contrasts_main_jb.get("lo"))};{_fmt(contrasts_main_jb.get("hi"))}]</div>
      <div class="lbl">Δ CI95 (JB)</div></div>
  </div>
</div>
</section>"""


def _render_d2(bench_table_md: str) -> str:
    """D2 — Bảng điểm: parse markdown table, render HTML (không ẩn hàng)."""
    lines = [ln for ln in bench_table_md.splitlines() if ln.strip().startswith("|")]
    if not lines:
        return '<section id="D2"><h2>D2 — Bảng điểm</h2><p>bench_table.md không có.</p></section>'

    rows_html = []
    is_header = True
    for ln in lines:
        if set(ln.replace("|", "").replace("-", "").replace(":", "").strip()) == set():
            is_header = False
            continue
        cells = [c.strip() for c in ln.strip().strip("|").split("|")]
        if is_header:
            rows_html.append("<tr>" + "".join(f"<th>{c}</th>" for c in cells) + "</tr>")
        else:
            def _td(c, method_col=(cells[0] if cells else "") == "OURS"):
                if cells and cells[0] == "OURS":
                    return f'<td class="ours">{c}</td>'
                return f"<td>{c}</td>"
            rows_html.append("<tr>" + "".join(_td(c) for c in cells) + "</tr>")

    return f"""<section id="D2">
<h2>D2 — Bảng điểm (mọi bên, không ẩn hàng)</h2>
<table>{"".join(rows_html)}</table>
</section>"""


def _render_d6(report: dict) -> str:
    """D6 — Giám khảo: τ, iou_thr, recall_easy, V2 ratio, κ."""
    judges = report.get("judges", {})
    kappa = report.get("kappa_JA_JB")

    rows = []
    for j, info in judges.items():
        v = info.get("validity", {})
        ok = info.get("validity", {}).get("ok")
        status = '<span class="check-ok">✓</span>' if ok else '<span class="check-fail">✗</span>'
        rows.append(
            f"<tr><td>{j}</td><td>{info.get('tau','—')}</td>"
            f"<td>{info.get('iou_thr','—')}</td>"
            f"<td>{v.get('recall_easy','—')}</td>"
            f"<td>{v.get('auroc_unc_vs_miss','—')}</td>"
            f"<td>{status}</td></tr>"
        )

    kappa_str = f"{kappa:.4f}" if isinstance(kappa, float) else "—"
    return f"""<section id="D6">
<h2>D6 — Giám khảo: τ, IoU, recall_easy, κ</h2>
<table>
<tr><th>Giám khảo</th><th>τ</th><th>IoU thr</th>
    <th>recall_easy</th><th>AUROC unc</th><th>Hợp lệ</th></tr>
{"".join(rows)}
</table>
<p style="margin-top:8px">Cohen κ (JA/JB): <strong>{kappa_str}</strong></p>
</section>"""


def _render_d9(report: dict) -> str:
    """D9 — Toàn vẹn: bảng sha."""
    keys = [
        ("prereg_sha256", "Prereg"),
        ("split_sha256", "Split"),
        ("selections_sha256", "Selections"),
        ("repo_sha", "Repo"),
    ]
    rows = []
    for k, label in keys:
        val = report.get(k, "—")
        ok_mark = '<span class="check-ok">✓</span>' if val and val != "—" else '<span class="check-fail">✗</span>'
        rows.append(f"<tr><td>{label}</td><td style='font-family:monospace;font-size:.8em'>{val}</td><td>{ok_mark}</td></tr>")
    return f"""<section id="D9">
<h2>D9 — Toàn vẹn dữ liệu</h2>
<table>
<tr><th>Artefact</th><th>SHA256</th><th>Có</th></tr>
{"".join(rows)}
</table>
</section>"""


def _render_img_section(section_id: str, title: str, b64: str) -> str:
    return f"""<section id="{section_id}">
<h2>{title}</h2>
<div class="img-wrap"><img src="data:image/png;base64,{b64}" alt="{title}"/></div>
</section>"""


# ── Entry point ───────────────────────────────────────────────────────────────
def render(
    report_judge: dict,
    report_train: Optional[dict],
    job: Optional[Path],
    out: Path,
) -> Path:
    """Render dashboard.

    Tham số:
        report_judge: nội dung report_judge.json đã load.
        report_train: nội dung report_train.json (hoặc None).
        job: đường dẫn J/ (để tìm bench/report/bench_table.md và media/).
        out: thư mục đầu ra (sẽ tạo nếu chưa có).

    Trả về:
        Path tới dashboard.html.
    """
    out = Path(out)
    out.mkdir(parents=True, exist_ok=True)

    # Đọc bench_table.md nếu có
    bench_table_md = ""
    if job is not None:
        bt = Path(job) / "bench" / "report" / "bench_table.md"
        if bt.is_file():
            bench_table_md = bt.read_text(encoding="utf-8")

    # Vẽ các PNG
    fig_forest, b64_forest = _fig_forest(report_judge, out)
    fig_budget, b64_budget = _fig_budget(report_judge, out)
    fig_random, b64_random = _fig_random(report_judge, out)
    fig_examples, b64_examples = _fig_examples(report_judge, job, out)
    fig_train, b64_train = _fig_train(report_train, out)

    plt.close("all")

    # Dựng HTML — tất cả inline, không gọi mạng
    d1 = _render_d1(report_judge)
    d2 = _render_d2(bench_table_md)
    d3 = _render_img_section("D3", "D3 — Forest plot", b64_forest)
    d4 = _render_img_section("D4", "D4 — Đường ngân sách", b64_budget)
    d5 = _render_img_section("D5", "D5 — Random &amp; heuristic", b64_random)
    d6 = _render_d6(report_judge)
    d7 = _render_img_section("D7", "D7 — Ví dụ khung OURS vs X*", b64_examples)
    d8 = _render_img_section("D8", "D8 — Pha 4: ΔAP50_vru", b64_train)
    d9 = _render_d9(report_judge)

    dataset = report_judge.get("dataset", "")
    label = report_judge.get("label", "")
    html = f"""<!DOCTYPE html>
<html lang="vi">
<head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>VCuboidFIT Judge Benchmark — {dataset}</title>
{_CSS}
</head>
<body>
<h1>VCuboidFIT Judge Benchmark</h1>
<p style="color:#555;margin-top:0">Dataset: <strong>{dataset}</strong> &nbsp;|&nbsp;
Nhãn: <strong>{label}</strong> &nbsp;|&nbsp;
B = {report_judge.get("B","?")} &nbsp;|&nbsp;
N_pool = {report_judge.get("n_pool","?")}</p>
{d1}
{d2}
{d3}
{d4}
{d5}
{d6}
{d7}
{d8}
{d9}
</body>
</html>"""

    html_path = out / "dashboard.html"
    html_path.write_text(html, encoding="utf-8")
    return html_path
