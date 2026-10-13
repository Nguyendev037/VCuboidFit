"""M6 · Đánh giá engine `rare_v24` theo instance (planning/10 SPEC-P03 §2). MODULE DUY NHẤT đọc bảng gt_rhcio_*.

IY@B = số instance target khác nhau có ≥1 frame trong lô chọn / B. NY@B = (IY − E[IY_random]) / (IY_oracle − E[IY_random]).
Oracle = tham lam max-coverage trên GT (cận dưới (1−1/e) của tối ưu thật).
"""
import math
from collections.abc import Callable, Sequence

import numpy as np
import pandas as pd

Selector = Callable[[Sequence[str], int], list[str]]  # (pool_tokens, B) → B token đã chọn


def budget(n_eligible: int, frac: float) -> int:
    """B = ceil(frac × eligible) (quyết định D04 hồ sơ 10)."""
    return max(1, math.ceil(frac * n_eligible))


def target_frames(gt_inst: pd.DataFrame, axis: str = "r2_combo", capture: str = "any",
                  gt_frame: pd.DataFrame | None = None) -> dict[str, set[str]]:
    """instance target của trục → tập frame (có ≥1 điểm) chứa nó."""
    rows = gt_inst[gt_inst["axes"].str.split("|").apply(lambda a: axis in a)]
    tf = {r.instance_token: set(r.frames.split("|")) for r in rows.itertuples() if r.frames}
    return _capture_frames(tf, gt_frame, capture, axis)


def _capture_frames(tf, gt_frame, capture, axis="r2_combo"):
    if capture == "any":
        return tf
    if capture != "rare_form":
        raise ValueError(f"unknown capture: {capture}")
    if gt_frame is None:
        raise ValueError("rare_form requires gt_frame")
    if axis != "r2_combo":
        raise ValueError("target_instances records rare form only for r2_combo")
    out = {i: set() for i in tf}
    for row in gt_frame.itertuples():
        for i in str(row.target_instances or "").split("|"):
            if i in out:
                out[i].add(row.sample_token)
    return out


def captured(sel: Sequence[str], tf: dict[str, set[str]]) -> set[str]:
    s = set(sel)
    return {i for i, fr in tf.items() if fr & s}


def metrics(sel: Sequence[str], gt_frame: pd.DataFrame, tf: dict[str, set[str]]) -> dict:
    B = max(len(sel), 1)
    cap = captured(sel, tf)
    g = gt_frame.set_index("sample_token")
    sub = g.loc[[t for t in sel if t in g.index]]
    return dict(B=len(sel), iy=len(cap) / B, n_instances=len(cap), irecall=len(cap) / max(len(tf), 1),
                precision=float(sub["is_target"].mean()) if len(sub) else 0.0,
                night=float(sub["c_night"].mean()) if len(sub) else 0.0,
                rain=float(sub["c_rain"].mean()) if len(sub) else 0.0)


def oracle_instance(pool: Sequence[str], B: int, tf: dict[str, set[str]]) -> list[str]:
    """Tham lam: mỗi bước lấy frame phủ thêm nhiều instance chưa phủ nhất; hoà ⇒ theo thứ tự token (tất định)."""
    by_frame: dict[str, set[str]] = {t: set() for t in pool}
    for i, fr in tf.items():
        for f in fr & by_frame.keys():
            by_frame[f].add(i)
    chosen, covered = [], set()
    remaining = sorted(by_frame)
    for _ in range(min(B, len(remaining))):
        best = max(remaining, key=lambda t: len(by_frame[t] - covered))
        chosen.append(best)
        covered |= by_frame[best]
        remaining.remove(best)
    return chosen


def random_selector(seed: int) -> Selector:
    def sel(pool, B):
        rng = np.random.default_rng(seed)
        return list(rng.choice(sorted(pool), size=min(B, len(pool)), replace=False))
    return sel


def topk_selector(scores: pd.Series) -> Selector:
    """Chọn B frame điểm cao nhất trong pool (hoà ⇒ theo token)."""
    def sel(pool, B):
        s = scores.reindex(sorted(pool)).fillna(-np.inf)
        return list(s.sort_values(ascending=False, kind="mergesort").index[:B])
    return sel


def expected_random_iy(pool, B, tf, n_seeds: int = 100) -> float:
    return float(np.mean([metrics(random_selector(s)(pool, B), pd.DataFrame(
        columns=["sample_token", "is_target", "c_night", "c_rain"]), tf)["iy"] for s in range(n_seeds)]))


def normalized_yield(iy: float, iy_random: float, iy_oracle: float) -> float | None:
    gap = iy_oracle - iy_random
    return None if gap <= 0 else (iy - iy_random) / gap


def bootstrap_delta(sel_a: Selector, sel_b: Selector, gt_frame: pd.DataFrame, tf: dict[str, set[str]],
                    frac: float, n_boot: int = 1000, seed: int = 2026) -> tuple[float, float, float]:
    """Paired cluster bootstrap theo scene, CHỌN LẠI mỗi lượt. → (Δ IY quan sát, CI95 thấp, CI95 cao)."""
    scenes = gt_frame.groupby("scene_token")["sample_token"].apply(list).to_dict()
    names = sorted(scenes)

    def delta(pool):
        B = budget(len(pool), frac)
        return metrics(sel_a(pool, B), gt_frame, tf)["iy"] - metrics(sel_b(pool, B), gt_frame, tf)["iy"]

    obs = delta([t for n in names for t in scenes[n]])
    rng = np.random.default_rng(seed)
    ds = []
    for _ in range(n_boot):
        pick = rng.choice(names, size=len(names), replace=True)
        # scene lặp ⇒ bỏ token trùng (bản pitching: đơn giản hoá trọng số cụm, ghi trong report)
        ds.append(delta(list(dict.fromkeys(t for n in pick for t in scenes[n]))))
    lo, hi = np.percentile(ds, [2.5, 97.5])
    return float(obs), float(lo), float(hi)


def evaluate(selectors: dict[str, Selector], gt_frame: pd.DataFrame, gt_inst: pd.DataFrame,
             frac: float = 0.05, axis: str = "r2_combo", n_random: int = 100,
             capture: str = "any") -> dict:
    """Bảng chính cho slide: IY, NY, IRecall, Precision, phủ đêm/mưa mỗi phương pháp + random + oracle."""
    pool = list(gt_frame["sample_token"])
    tf = target_frames(gt_inst, axis, capture, gt_frame)
    B = budget(len(pool), frac)
    iy_rand = expected_random_iy(pool, B, tf, n_random)
    orc = metrics(oracle_instance(pool, B, tf), gt_frame, tf)
    out = {"B": B, "pool": len(pool), "axis": axis, "n_target_instances": len(tf),
           "random": {"iy": iy_rand}, "oracle": orc, "methods": {}}
    for name, sel in selectors.items():
        m = metrics(sel(pool, B), gt_frame, tf)
        m["ny"] = normalized_yield(m["iy"], iy_rand, orc["iy"])
        m["lift"] = m["iy"] / iy_rand if iy_rand > 0 else None
        out["methods"][name] = m
    return out


def bootstrap_fixed(sels: dict[str, list[str]], gt_frame: pd.DataFrame, tf: dict[str, set[str]],
                    n_boot: int = 1000, seed: int = 20261013, capture: str = "any") -> pd.DataFrame:
    """CI chính (planning/11 SPEC-P04 §3): lô chọn CỐ ĐỊNH, rút scene có hoàn lại (scene lặp đếm lặp),
    IY_b = Σ cap_s / Σ |Sel ∩ s|. Hợp lệ vì mỗi instance chỉ thuộc một scene. Dòng = lượt, cột = phương pháp."""
    tf = _capture_frames(tf, gt_frame, capture)
    scene_of = dict(zip(gt_frame["sample_token"], gt_frame["scene_token"]))
    names = sorted(set(scene_of.values()))
    pos = {n: k for k, n in enumerate(names)}
    cap = {m: np.zeros(len(names)) for m in sels}
    nsel = {m: np.zeros(len(names)) for m in sels}
    for m, sel in sels.items():
        for t in sel:
            nsel[m][pos[scene_of[t]]] += 1
        for i in captured(sel, tf):
            cap[m][pos[scene_of[next(iter(tf[i]))]]] += 1
    rng = np.random.default_rng(seed)
    rows = []
    for _ in range(n_boot):
        idx = rng.integers(0, len(names), size=len(names))
        rows.append({m: cap[m][idx].sum() / max(nsel[m][idx].sum(), 1.0) for m in sels})
    return pd.DataFrame(rows)


def paired_ci(boot: pd.DataFrame, a: str, b: str, level: float = 0.95) -> dict:
    d = boot[a] - boot[b]
    lo, hi = np.percentile(d, [(1 - level) / 2 * 100, (1 + level) / 2 * 100])
    return dict(delta=float(d.mean()), lo=float(lo), hi=float(hi), n_boot=int(len(d)))


def context_coverage(sel: list[str], ctx: pd.DataFrame, axes=("glare_sun",)) -> dict[str, dict]:
    """Phủ bối cảnh: cov = |Sel ∩ F_a| / B, base = |F_a| / N, lift = cov / base. `ctx`: sample_token, context_tags ('a|b')."""
    tags = ctx.set_index("sample_token")["context_tags"].fillna("").str.split("|")
    out, B, N = {}, max(len(sel), 1), max(len(tags), 1)
    s = set(sel)
    for a in axes:
        fa = {t for t, tg in tags.items() if a in tg}
        cov, base = len(fa & s) / B, len(fa) / N
        out[a] = dict(cov=cov, base=base, lift=(cov / base) if base > 0 else None)
    return out
