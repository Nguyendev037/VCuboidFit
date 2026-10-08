"""M7 · chọn B frame: MMR + quota/scene (PDF §4.4) và các baseline không nhãn (PDF §6.1).

Mọi hàm nhận bảng `lidar_scores` (thứ tự = lidar_index) và trả bảng `lidar_selected`.
"""
import math

import numpy as np
import pandas as pd

from c4.contracts import validate
from c4.mining.mmr import mmr_select

COMPONENTS = [("r_rar", "rarity"), ("r_nov", "novelty"), ("r_unc", "uncertainty")]


def budget(n_pool: int, frac: float) -> int:
    return max(1, math.ceil(frac * n_pool))


def l2n(z: np.ndarray) -> np.ndarray:
    z = np.asarray(z, np.float32)
    return z / np.maximum(np.linalg.norm(z, axis=1, keepdims=True), 1e-12)


def reasons(sc: pd.DataFrame, weights=(1.0, 0.0, 0.0)) -> list[str]:
    """Thành phần có hạng phần trăm cao nhất (trong các thành phần có trọng số > 0)."""
    cols = [(c, name) for (c, name), w in zip(COMPONENTS, weights) if w > 0] or COMPONENTS[:1]
    out = []
    for row in sc[[c for c, _ in cols]].itertuples(index=False):
        j = int(np.argmax(row))
        out.append(f"{cols[j][1]} p{int(round(100 * row[j]))}")
    return out


def _table(sc: pd.DataFrame, idx, method: str, B: int, seed=0, s=None, max_sim=None,
           util=None, reason=None) -> pd.DataFrame:
    idx = list(idx)
    sub = sc.iloc[idx]
    n = len(idx)
    df = pd.DataFrame(dict(
        method=method, seed=seed, rank=np.arange(1, n + 1), sample_token=sub["sample_token"].values,
        scene_token=sub["scene_token"].values,
        s=sub["s"].values if s is None else s, max_sim=np.zeros(n) if max_sim is None else max_sim,
        mmr_util=np.zeros(n) if util is None else util,
        reason=[method] * n if reason is None else reason, budget_B=B))
    return validate(df, "lidar_selected")


def _scene_codes(sc):
    return sc["scene_token"].astype("category").cat.codes.to_numpy()


def minmax_score(sc: pd.DataFrame, weights=(1.0, 0.0, 0.0)) -> np.ndarray:
    """Q4 (chốt Đ14, planning/04 plan.md): điểm cho MMR từ giá trị thô chuẩn hoá min-max trên
    frame hợp lệ, cắt ngoại lai ở phân vị 1/99 (một frame lỗi không nén cả pool) — giữ biên độ
    Rar mà hạng phần trăm làm mất. Tín hiệu hằng ⇒ 0."""
    keep = sc["keep"].to_numpy(bool)
    out = np.zeros(len(sc))
    for col, w in zip(("rar", "nov", "unc"), weights):
        if w <= 0:
            continue
        x = sc[col].to_numpy(np.float64)
        v = x[keep]
        lo, hi = (np.percentile(v, [1, 99]) if v.size else (0.0, 0.0))
        if hi > lo:
            out += w * np.where(keep, np.clip((x - lo) / (hi - lo), 0.0, 1.0), 0.0)
    return np.round(np.clip(out, 0.0, 1.0), 6)


def select_mmr(sc: pd.DataFrame, z: np.ndarray, B: int, lam: float, m: int | None,
               weights=(1.0, 0.0, 0.0), method="mmr", col="s",
               score_norm: str = "rank") -> tuple[pd.DataFrame, list[str]]:
    """MMR tham lam: f* = argmax λ·s(f) − (1−λ)·max_g cos(z(f), z(g)), quota m frame/scene.
    Quota không đủ chỗ cho B frame ⇒ tự nâng m (cảnh báo)."""
    keep = sc["keep"].to_numpy(bool)
    scene = _scene_codes(sc)
    warnings: list[str] = []
    n_ok = int(keep.sum())
    if n_ok == 0:
        return _table(sc, [], method, B), ["Không có frame LiDAR hợp lệ nào để chọn"]
    m_eff = B if m is None else int(m)
    per_scene = np.bincount(scene[keep])
    while sum(min(m_eff, c) for c in per_scene) < min(B, n_ok):
        m_eff += 1
    if m is not None and m_eff != m:
        warnings.append(f"Quota/scene tự nâng từ {m} lên {m_eff} để đủ {B} frame "
                        f"({len(per_scene[per_scene > 0])} scene hợp lệ)")
    if score_norm == "minmax":
        sc = sc.assign(**{col: minmax_score(sc, weights)})
    elif score_norm != "rank":
        raise ValueError(f"score_norm không hợp lệ: {score_norm}")
    picks = mmr_select(sc[col].to_numpy(np.float32), l2n(z), scene,
                       sc["frame_idx"].to_numpy(), keep, B, B, lam=lam, m=m_eff, min_gap=1)
    if len(picks) < B:
        warnings.append(f"Chỉ chọn được {len(picks)} / {B} frame hợp lệ")
    idx = [p["i"] for p in picks]
    sub = sc.iloc[idx]
    return _table(sc, idx, method, B, s=[p["S"] for p in picks],
                  max_sim=[p["max_sim"] for p in picks], util=[p["mmr_util"] for p in picks],
                  reason=reasons(sub, weights)), warnings


def select_topk(sc: pd.DataFrame, B: int, col="s", method="topk", weights=(1.0, 0.0, 0.0)):
    ok = np.flatnonzero(sc["keep"].to_numpy(bool))
    order = ok[np.lexsort((sc["sample_token"].to_numpy()[ok], -sc[col].to_numpy()[ok]))][:B]
    return _table(sc, order, method, B, reason=reasons(sc.iloc[order], weights))


def select_random(sc: pd.DataFrame, B: int, seed: int, m: int | None = None) -> pd.DataFrame:
    ok = np.flatnonzero(sc["keep"].to_numpy(bool))
    order = ok[np.random.default_rng(seed).permutation(len(ok))]
    if m is None:
        return _table(sc, order[:B], "random", B, seed=seed)
    scene = _scene_codes(sc)
    count = np.zeros(scene.max() + 1, int)
    m_eff = m
    while True:
        chosen = []
        count[:] = 0
        for i in order:
            if count[scene[i]] < m_eff:
                chosen.append(i)
                count[scene[i]] += 1
                if len(chosen) == B:
                    break
        if len(chosen) >= min(B, len(ok)):
            break
        m_eff += 1
    return _table(sc, chosen, "random_quota", B, seed=seed)


def select_coreset(sc: pd.DataFrame, z: np.ndarray, B: int) -> pd.DataFrame:
    """k-center greedy (Sener & Savarese) trên z; khởi đầu = frame có Rar lớn nhất."""
    ok = np.flatnonzero(sc["keep"].to_numpy(bool))
    if len(ok) == 0:
        return _table(sc, [], "coreset", B)
    Z = np.asarray(z, np.float64)[ok]
    first = int(np.argmax(sc["rar"].to_numpy()[ok]))
    chosen = [first]
    dmin = np.linalg.norm(Z - Z[first], axis=1)
    while len(chosen) < min(B, len(ok)):
        j = int(np.argmax(dmin))
        chosen.append(j)
        dmin = np.minimum(dmin, np.linalg.norm(Z - Z[j], axis=1))
    return _table(sc, ok[chosen], "coreset", B)
