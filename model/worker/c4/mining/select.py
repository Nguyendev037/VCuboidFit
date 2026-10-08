# c4/mining/select.py · một hàm cho hybrid và mọi biến thể ablation
import math

import numpy as np
import pandas as pd

from c4.contracts import SELECTED, validate
from c4.mining.mmr import mmr_select

ABLATION = {"novelty": "S_nov", "uncertainty": "S_unc", "query": "S_qry"}


def reason(r) -> str:
    parts = [(r.r_nov, "novelty"), (r.r_unc, "uncertainty"), (r.r_qry, f"query {r.qry_best}")]
    top = [f"{name} p{int(v * 100)}" for v, name in sorted(parts, key=lambda t: -t[0])[:2]
           if v >= 0.8]
    return " · ".join(top) or "điểm tổng hợp cao"


def _prepare(fs: pd.DataFrame) -> pd.DataFrame:
    """Tất định: làm tròn điểm 6 chữ số và sắp theo sample_token trước khi chọn."""
    fs = fs.sort_values("sample_token").reset_index(drop=True)
    cols = ["S_hybrid", "S_nov", "S_unc", "S_qry"]
    fs[cols] = fs[cols].astype(np.float64).round(6)
    return fs


def _budgets(N: int, r):
    return math.ceil(r.budget * N), math.ceil(r.budget_max * N)


def _scene_caps(scene_ok: np.ndarray, fidx_ok: np.ndarray, gap: int) -> list[int]:
    """Số frame tối đa chọn được trong mỗi scene khi hai frame phải cách nhau ít nhất gap."""
    caps = []
    for s in np.unique(scene_ok):
        last, n = None, 0
        for f in np.sort(fidx_ok[scene_ok == s]):
            if last is None or f - last >= gap:
                last, n = f, n + 1
        caps.append(n)
    return caps


def _feasible_cap(scene_ok, fidx_ok, B: int, m0: int, g0: int) -> tuple[int, int]:
    """m nhỏ nhất (không dưới m0) đủ chọn B frame; nếu ngay cả không trần scene cũng không đủ
    thì giảm min_gap (chia đôi) như phương án cuối."""
    gap = g0
    while True:
        caps = _scene_caps(scene_ok, fidx_ok, gap)
        if sum(caps) >= B or gap == 1:
            break
        gap = max(1, gap // 2)
    m = m0
    while sum(min(m, c) for c in caps) < B and m < max(caps):
        m += 1
    return m, gap


def _empty(B: int) -> pd.DataFrame:
    return validate(pd.DataFrame({c: [] for c in SELECTED}).assign(budget_B=B), "selected")


def run_select(fs, Z_frame, r, col="S_hybrid", method="hybrid", diverse=True):
    fs = _prepare(fs)
    N = len(fs)
    B, B_max = _budgets(N, r)
    warnings: list[str] = []
    ok = fs["q_ok"].to_numpy(bool)
    if not ok.any():
        return _empty(B), ["Không có frame hợp lệ nào để chọn: mọi ảnh bị loại vì quá tối, "
                           "mờ hoặc không có vật thể"]
    scene = fs["scene_token"].astype("category").cat.codes.to_numpy()
    fidx = fs["frame_idx"].to_numpy()
    Z = np.asarray(Z_frame, np.float32)[fs["frame_emb_row"].to_numpy()]

    def select(m, gap, lam):
        return mmr_select(fs[col].to_numpy(np.float32), Z, scene, fidx, ok, B, B_max,
                          lam=lam, m=m, min_gap=gap)

    def n_top(picks):
        return sum(p["rank"] <= B for p in picks)

    if not diverse:
        picks = select(N, 1, 1.0)  # hybrid_nodiv: chỉ xếp theo điểm
    else:
        m0, g0 = r.m, r.min_gap
        m, gap = _feasible_cap(scene[ok], fidx[ok], B, m0, g0)
        picks = select(m, gap, r.lam)
        # MMR tham lam chọn theo điểm, không theo khoảng cách tối ưu, nên có thể vẫn thiếu:
        # nâng m đến trần của scene giàu nhất trước, sau đó mới giảm min_gap.
        caps_max = max(_scene_caps(scene[ok], fidx[ok], gap))
        while n_top(picks) < B:
            if m < caps_max:
                m += 1
            elif gap > 1:
                gap = max(1, gap // 2)
                caps_max = max(_scene_caps(scene[ok], fidx[ok], gap))
            else:
                break
            picks = select(m, gap, r.lam)
        if gap != g0:
            warnings.append(f"min_gap tự giảm từ {g0} xuống {gap} vì các scene không đủ frame "
                            f"cách xa nhau để chọn {B} frame")
        if m != m0:
            n_sc = len(np.unique(scene[ok]))
            warnings.append(f"max_per_scene tự nâng từ {m0} lên {m} để đủ {B} frame "
                            f"(dataset có {n_sc} scene hợp lệ)")
    if diverse and n_top(picks) < B:
        warnings.append(f"Chỉ chọn được {min(len(picks), B)} / {B} frame hợp lệ")
    if not picks:
        return _empty(B), warnings
    sel = fs.iloc[[p["i"] for p in picks]].reset_index(drop=True)
    out = sel.assign(
        method=method, seed=0, budget_B=B, rank=[p["rank"] for p in picks],
        S=[p["S"] for p in picks], max_sim=[p["max_sim"] for p in picks],
        mmr_util=[p["mmr_util"] for p in picks],
        reason=[reason(x) for x in sel.itertuples()])
    return validate(out, "selected"), warnings


def run_random(fs, r, seed: int) -> pd.DataFrame:
    fs = _prepare(fs)
    B, B_max = _budgets(len(fs), r)
    order = np.random.default_rng(seed).permutation(len(fs))[:B_max]
    out = fs.iloc[order].assign(method="random", seed=seed, rank=np.arange(1, len(order) + 1),
                                S=0.0, max_sim=0.0, mmr_util=0.0, reason="random", budget_B=B)
    return validate(out, "selected")


def run_all(fs, Z_frame, r, seeds):
    """Hybrid + 4 biến thể ablation + random theo từng seed. Cảnh báo lấy từ hybrid."""
    sels, warnings = {}, []
    sels["hybrid"], warnings = run_select(fs, Z_frame, r)
    for method, col in ABLATION.items():
        sels[method], _ = run_select(fs, Z_frame, r, col=col, method=method)
    sels["hybrid_nodiv"], _ = run_select(fs, Z_frame, r, method="hybrid_nodiv", diverse=False)
    for s in seeds:
        sels[f"random_{s}"] = run_random(fs, r, s)
    return sels, warnings
