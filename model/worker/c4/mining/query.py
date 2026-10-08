# c4/mining/query.py · Qry(x): cosine CLIP cao nhất giữa ảnh và tập text query
import hashlib
import threading
from collections import OrderedDict
from typing import Protocol

import numpy as np
import pandas as pd


class TextEncoder(Protocol):
    def encode(self, texts: list[str]) -> np.ndarray:
        """Trả embedding text đã chuẩn hóa L2, shape (len(texts), d)."""


TEXT_CACHE_MAX = 32
_TEXT_CACHE: OrderedDict[str, np.ndarray] = OrderedDict()  # LRU: mới dùng nhất ở cuối
_TEXT_LOCK = threading.Lock()


def query_scores(C_img: np.ndarray, T: np.ndarray, query_ids: list[str]):
    sim = np.asarray(C_img, np.float32) @ np.asarray(T, np.float32).T
    best = np.argmax(sim, axis=1)
    return sim[np.arange(len(sim)), best].astype(np.float32), np.asarray(query_ids, object)[best]


def apply_queries(feat: pd.DataFrame, C_img: np.ndarray, queries: list[dict],
                  encoder: TextEncoder) -> pd.DataFrame:
    """Ghi đè qry_max, qry_best theo tập query mới. Embedding text cache theo nội dung query."""
    if not queries:
        raise ValueError("Cần ít nhất một query")
    texts = [q["text"] for q in queries]
    key = hashlib.sha1("\n".join(texts).encode("utf-8")).hexdigest()
    with _TEXT_LOCK:
        if key in _TEXT_CACHE:
            _TEXT_CACHE.move_to_end(key)
        else:
            _TEXT_CACHE[key] = np.asarray(encoder.encode(texts), np.float32)
            while len(_TEXT_CACHE) > TEXT_CACHE_MAX:
                _TEXT_CACHE.popitem(last=False)
        T = _TEXT_CACHE[key]
    mx, best = query_scores(C_img[feat["emb_row"].to_numpy()], T, [q["id"] for q in queries])
    return feat.assign(qry_max=mx, qry_best=pd.array(best, dtype="string"))
