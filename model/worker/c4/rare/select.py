"""M2c · dedup theo track + MMR chọn B frame (planning/11 SPEC-P05 §6.2 + §14.1). Frame suspect/outlier và
frame ngoài pool KHÔNG BAO GIỜ vào lô chọn (A5). Không đọc nhãn."""
import math
from collections.abc import Sequence

import numpy as np
import pandas as pd

from c4.lidar.select import l2n
from c4.mining.mmr import mmr_select

TRACK_PENALTY = 0.5


def rare_selector(ranking: list[str]):
    """Selector (pool, B) -> token theo thứ tự `ranking` (đã xếp bằng MMR), lọc theo pool (SPEC-P05 §14.1)."""
    def sel(pool: Sequence[str], B: int) -> list[str]:
        ok = set(pool)
        return [t for t in ranking if t in ok][:B]
    return sel


def track_penalized(rare_objects: pd.DataFrame, eligible_tokens: set[str]) -> set[str]:
    """Frame bị phạt = có vật thuộc track nhưng KHÔNG phải frame tốt nhất (s_obj cao nhất) của bất kỳ track nào nó chứa.
    Frame không có vật tracked (hoặc là đại diện của ≥ 1 track) không bị phạt."""
    obj = rare_objects[rare_objects["sample_token"].isin(eligible_tokens) & (rare_objects["track_id"] != "")]
    if obj.empty:
        return set()
    best = obj.sort_values(["s_obj", "sample_token"], ascending=[False, True], kind="mergesort") \
        .drop_duplicates("track_id")
    representative = set(best["sample_token"])
    return {t for t in obj["sample_token"].unique() if t not in representative}


def select_rare(rare_frames: pd.DataFrame, rare_objects: pd.DataFrame, z0: np.ndarray, index: pd.DataFrame,
                B: int, cfg: dict, eligible: np.ndarray | None = None) -> pd.DataFrame:
    """Điền rank/selected/explore. `eligible` (bool theo thứ tự `index`) = gate valid ∧ pool; mặc định gate valid.

    ranking = MỌI frame eligible theo thứ tự MMR (pha A: không bị phạt track, quota `quota_m`/scene, B=B_max=n_eligible
    theo §14.1; pha B: phần còn lại, quota nâng không giới hạn). selected = ranking[:B]. Trả bản sao đã điền;
    `df.attrs["ranking"]` = token theo thứ tự, `df.attrs["warningCodes"]` = cảnh báo."""
    df = rare_frames.copy()
    tokens = df["sample_token"].tolist()
    assert tokens == index["sample_token"].tolist(), "rare_frames phải cùng thứ tự lidar_index"
    elig = (df["gate"] == "valid").to_numpy() if eligible is None else np.asarray(eligible, bool)
    elig = elig & (df["gate"] == "valid").to_numpy()
    warnings: list[str] = []
    n_elig = int(elig.sum())
    if n_elig == 0:
        warnings.append("ELIGIBLE_ZERO")
    elif B > n_elig:
        warnings.append("ELIGIBLE_LT_B")
        B = n_elig
    pen_tokens = track_penalized(rare_objects, {t for t, e in zip(tokens, elig) if e})
    pen = np.array([t in pen_tokens for t in tokens])
    S = df["s_frame"].to_numpy(np.float32) * np.where(pen, TRACK_PENALTY, 1.0).astype(np.float32)
    Z = l2n(z0)
    scene = index["scene_token"].astype("category").cat.codes.to_numpy()
    fidx = index["frame_idx"].to_numpy()
    lam, m_cfg = float(cfg.get("mmr_lambda", 0.7)), cfg.get("quota_m", 3)
    # "even" (H14 P2): trần mỗi scene = ceil(B / số scene eligible) => phủ scene đều; không dùng nhãn
    m = max(1, math.ceil(B / max(len(np.unique(scene[elig])), 1))) if m_cfg == "even" else int(m_cfg)
    order: list[tuple[int, float]] = []  # (vị trí trong index, max_sim)
    if n_elig:
        picks = mmr_select(S, Z, scene, fidx, elig & ~pen, n_elig, n_elig, lam=lam, m=m, min_gap=1)
        order = [(p["i"], p["max_sim"]) for p in picks]
        left = elig.copy()
        left[[i for i, _ in order]] = False
        if left.any():  # SPEC-P05 §6.2 bước 6: phần còn lại (kể cả frame bị phạt track), quota nâng không giới hạn
            nl = int(left.sum())
            rest = mmr_select(S, Z, scene, fidx, left, nl, nl, lam=lam, m=nl, min_gap=1)
            order += [(p["i"], p["max_sim"]) for p in rest]
    rank = np.full(len(df), -1, np.int64)
    explore = np.zeros(len(df), bool)
    # explore (Đ25): frame được chọn nhưng hạng s_frame THUẦN (không phạt track, không MMR) nằm ngoài top-B eligible
    pure = df["s_frame"].to_numpy(np.float64)
    pure_top = set(np.flatnonzero(elig)[np.argsort(-pure[elig], kind="mergesort")[:B]])
    for r, (i, _) in enumerate(order, start=1):
        rank[i] = r
        explore[i] = (r <= B) and i not in pure_top
    df["rank"] = pd.array([None if r < 0 else int(r) for r in rank], dtype="Int32")
    df["selected"] = (rank > 0) & (rank <= B)
    df["explore"] = explore
    df.attrs["ranking"] = [tokens[i] for i, _ in order]
    df.attrs["warningCodes"] = warnings
    df.attrs["B"] = B
    df.attrs["quota_m"] = m
    return df
