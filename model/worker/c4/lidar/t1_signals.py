"""M6 (Tầng 1) · Ent, Inc, Nov từ output của model seed (PDF §4.2–4.3). Thuần numpy — chạy CPU.

preds_*.pkl: list[dict] theo thứ tự index, {sample_token, boxes (n,7), labels (n,), scores (n,)};
box lật đã được lật về hệ gốc bởi infer_t1.py.
"""
import pickle
from pathlib import Path

import numpy as np
import pandas as pd

from c4.contracts import ContractError, validate
from c4.lidar.scoring import novelty, pct_rank

EPS = 1e-6


def load_preds(path, tokens) -> list[dict]:
    with open(path, "rb") as f:
        preds = pickle.load(f)
    if [p["sample_token"] for p in preds] != list(tokens):
        raise ContractError(f"{path}: thứ tự/độ dài sample_token lệch lidar_index")
    return preds


def entropy(scores: np.ndarray) -> float:
    """Ent(f) = trung bình H(p_i), H nhị phân; D(f) rỗng ⇒ 0."""
    p = np.clip(np.asarray(scores, np.float64), EPS, 1 - EPS)
    if p.size == 0:
        return 0.0
    return float(np.mean(-p * np.log(p) - (1 - p) * np.log(1 - p)))


def match_count(a: dict, b: dict, delta: float) -> int:
    """Ghép tham lam theo score giảm dần: cùng class, tâm BEV cách < delta. Trả số cặp."""
    if len(a["scores"]) == 0 or len(b["scores"]) == 0:
        return 0
    used = np.zeros(len(b["scores"]), bool)
    cb = np.asarray(b["boxes"])[:, :2]
    lb = np.asarray(b["labels"])
    n = 0
    for i in np.argsort(-np.asarray(a["scores"]), kind="stable"):
        d = np.hypot(*(cb - np.asarray(a["boxes"])[i, :2]).T)
        ok = (~used) & (lb == a["labels"][i]) & (d < delta)
        if ok.any():
            used[np.flatnonzero(ok)[np.argmin(d[ok])]] = True
            n += 1
    return n


def inconsistency(orig: dict, flip: dict, delta: float) -> float:
    m = match_count(orig, flip, delta)
    return 1.0 - m / max(len(orig["scores"]), len(flip["scores"]), 1)


def _thr(p: dict, thr: float) -> dict:
    k = np.asarray(p["scores"]) >= thr
    return dict(boxes=np.asarray(p["boxes"])[k], labels=np.asarray(p["labels"])[k],
                scores=np.asarray(p["scores"])[k])


def compute_t1_signals(index: pd.DataFrame, preds_orig, preds_flip, z1: np.ndarray, seed_mask: np.ndarray,
            cfg: dict) -> pd.DataFrame:
    """t1_signals cho mọi dòng index. Nov đo tới các frame seed (seed_mask)."""
    t = cfg["t1"]
    ent, inc, ndet = [], [], []
    for po, pf in zip(preds_orig, preds_flip):
        a, b = _thr(po, t["score_thr"]), _thr(pf, t["score_thr"])
        ent.append(entropy(a["scores"]))
        inc.append(inconsistency(a, b, t["match_delta_m"]))
        ndet.append(len(a["scores"]))
    seed_mask = np.asarray(seed_mask, bool)
    nov = novelty(z1, z1[seed_mask]) if seed_mask.any() else np.zeros(len(index), np.float32)
    df = pd.DataFrame(dict(sample_token=index["sample_token"].to_numpy(), ent=ent, inc=inc,
                           n_det=ndet, nov=nov))
    return validate(df, "t1_signals")


def unc_score(sig: pd.DataFrame, keep: np.ndarray) -> np.ndarray:
    """Unc(f) = ½ r(Ent) + ½ r(Inc), hạng trên frame hợp lệ của tập đang chọn."""
    return (0.5 * pct_rank(sig["ent"].to_numpy(), keep)
            + 0.5 * pct_rank(sig["inc"].to_numpy(), keep)).astype(np.float32)


def load_signals(t1_dir, index: pd.DataFrame) -> pd.DataFrame | None:
    from c4.contracts import read_table

    p = Path(t1_dir) / "signals.parquet"
    if not p.is_file():
        return None
    s = read_table(str(p), "t1_signals").set_index("sample_token")
    missing = set(index["sample_token"]) - set(s.index)
    if missing:
        raise ContractError(f"t1/signals.parquet thiếu {len(missing)} sample_token")
    return s.loc[index["sample_token"]].reset_index()
