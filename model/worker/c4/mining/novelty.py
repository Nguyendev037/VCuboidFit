# c4/mining/novelty.py · Nov(x): khoảng cách trung bình tới k láng giềng khác scene
import numpy as np


def novelty_knn(Z: np.ndarray, scene_code: np.ndarray, frame_idx: np.ndarray, k: int = 10,
                min_gap: int = 4, chunk: int = 2048) -> np.ndarray:
    """Z (N, d) đã chuẩn hóa L2. Láng giềng chỉ lấy từ scene khác; nếu cả pool chỉ có một scene
    thì lấy trong scene đó nhưng bỏ các frame cách nhau dưới min_gap. Kết quả trong [0, 2]."""
    Z = np.ascontiguousarray(Z, dtype=np.float32)
    scene_code = np.asarray(scene_code)
    frame_idx = np.asarray(frame_idx)
    single = len(np.unique(scene_code)) == 1
    out = np.zeros(len(Z), dtype=np.float32)
    for s in range(0, len(Z), chunk):
        e = min(s + chunk, len(Z))
        sim = Z[s:e] @ Z.T
        if single:
            mask = np.abs(frame_idx[s:e, None] - frame_idx[None, :]) < min_gap
        else:
            mask = scene_code[s:e, None] == scene_code[None, :]
        sim[mask] = -np.inf
        n_valid = (~mask).sum(1)
        k_eff = int(min(k, n_valid.max())) if len(n_valid) else 0
        if k_eff == 0:
            continue
        top = -np.partition(-sim, k_eff - 1, axis=1)[:, :k_eff]
        dist = np.where(np.isfinite(top), 1.0 - top, 0.0)
        cnt = np.minimum(n_valid, k_eff)
        out[s:e] = np.where(cnt > 0, dist.sum(1) / np.maximum(cnt, 1), 0.0)
    return out
