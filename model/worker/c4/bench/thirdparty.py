"""Deterministic third-party and cheap baseline selectors."""

from pathlib import Path
from typing import Sequence

import numpy as np
import pandas as pd

from c4.rare.eval import Selector, topk_selector


def kcenter_selector(emb: np.ndarray, tokens: list[str], seed: int = 0) -> Selector:
    """Return a deterministic k-center-greedy selector over frame embeddings."""
    del seed
    vectors = np.asarray(emb, dtype=np.float32)
    if vectors.ndim != 2 or len(vectors) != len(tokens):
        raise ValueError("emb must be a 2-D array with one row per token")
    norms = np.linalg.norm(vectors, axis=1, keepdims=True)
    normalized = np.divide(vectors, norms, out=np.zeros_like(vectors), where=norms > 0)
    by_token = dict(zip(tokens, range(len(tokens))))
    if len(by_token) != len(tokens):
        raise ValueError("tokens must be unique")

    def select(pool: Sequence[str], budget: int) -> list[str]:
        available = sorted(set(pool) & by_token.keys())
        target = min(budget, len(available))
        if target == 0:
            return []
        rows = np.asarray([by_token[token] for token in available], dtype=np.intp)
        mean = normalized[rows].mean(axis=0)
        mean_norm = np.linalg.norm(mean)
        if mean_norm:
            mean = mean / mean_norm
        distances = 1.0 - normalized[rows] @ mean
        first = min(
            range(len(available)),
            key=lambda i: (-float(distances[i]), available[i]),
        )
        chosen = [first]
        remaining = set(range(len(available)))
        remaining.remove(first)
        min_dist = 1.0 - normalized[rows] @ normalized[rows[first]]
        while len(chosen) < target:
            next_idx = min(
                remaining,
                key=lambda i: (-float(min_dist[i]), available[i]),
            )
            chosen.append(next_idx)
            remaining.remove(next_idx)
            candidate_dist = 1.0 - normalized[rows] @ normalized[rows[next_idx]]
            min_dist = np.minimum(min_dist, candidate_dist)
        return [available[i] for i in chosen]

    return select


def entropy_selector(frame_unc: pd.Series) -> Selector:
    """Select frames with the highest detector uncertainty."""
    return topk_selector(frame_unc)


def crowd_selector(vru_count: pd.Series) -> Selector:
    """Select frames with the largest number of VRU detections."""
    return topk_selector(vru_count)


def blur_selector(q_blur: pd.Series) -> Selector:
    """Select the least sharp frames first."""
    return topk_selector(-q_blur)


def dark_selector(q_bright: pd.Series) -> Selector:
    """Select the darkest frames first."""
    return topk_selector(-q_bright)


def external_selector(path: Path) -> Selector:
    """Load a ranked token list from one token per line."""
    source = Path(path)
    if not source.is_file():
        raise FileNotFoundError(source)
    ranked = [line.strip() for line in source.read_text(encoding="utf-8").splitlines()]
    ranked = [token for token in ranked if token]

    def select(pool: Sequence[str], budget: int) -> list[str]:
        pool_set = set(pool)
        missing = [token for token in ranked if token not in pool_set]
        if missing:
            raise ValueError(f"ORDER_VIOLATION: token not in pool: {missing[0]}")
        # SPEC-P02 §6: danh sách ngắn hơn B ⇒ trả đúng phần có thật, KHÔNG bù token khác
        return list(dict.fromkeys(ranked))[:min(budget, len(pool_set))]

    return select


def frame_features(job: Path) -> pd.DataFrame:
    """Aggregate cached camera features into one deterministic row per frame."""
    root = Path(job) / "cache"
    dino_path = root / "feat_dino.parquet"
    emb_path = root / "dino_cls.npy"
    det_path = root / "feat_det.parquet"
    detections_path = root / "detections.parquet"
    for path in (dino_path, emb_path, det_path, detections_path):
        if not path.is_file():
            raise FileNotFoundError(path)

    dino = pd.read_parquet(dino_path)
    embeddings = np.load(emb_path)
    if "emb_row" in dino:  # emb_row có thể trỏ trùng (ảnh trùng nội dung) ⇒ chỉ kiểm biên
        rows = dino["emb_row"].to_numpy(dtype=np.intp)
    else:
        rows = np.arange(len(dino), dtype=np.intp)
    if len(rows) and (rows.min() < 0 or rows.max() >= len(embeddings)):
        raise ValueError("emb_row ngoài phạm vi dino_cls.npy")
    dino = dino.copy()
    dino["_row"] = rows

    def aggregate_embedding(group: pd.DataFrame) -> np.ndarray:
        values = np.asarray(embeddings[group["_row"].to_numpy()], dtype=np.float32)
        norms = np.linalg.norm(values, axis=1, keepdims=True)
        values = np.divide(values, norms, out=np.zeros_like(values), where=norms > 0)
        mean = values.mean(axis=0)
        norm = np.linalg.norm(mean)
        return mean / norm if norm else mean

    rows_out = []
    for token, group in dino.groupby("sample_token", sort=True):
        rows_out.append({
            "sample_token": token,
            "emb": aggregate_embedding(group),
            "unc_max": 0.0,
            "vru_count": 0,
            "q_blur_min": float(group["q_blur"].min()),
            "q_bright_mean": float(group["q_bright"].mean()),
        })
    result = pd.DataFrame(rows_out)

    det_features = pd.read_parquet(det_path)
    if not det_features.empty:
        uncertainty = det_features.groupby("sample_token", sort=False)["unc"].max()
        result["unc_max"] = result["sample_token"].map(uncertainty).fillna(0.0)
    detections = pd.read_parquet(detections_path)
    if not detections.empty:
        vru = detections[(detections["conf"] >= 0.5) &
                         detections["cls"].isin([0, 1, 3])]
        counts = vru.groupby("sample_token", sort=False).size()
        result["vru_count"] = result["sample_token"].map(counts).fillna(0).astype(int)
    return result
