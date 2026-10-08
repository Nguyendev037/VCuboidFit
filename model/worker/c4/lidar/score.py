"""M6 · Rarity k-NN khác scene + gộp điểm bằng hạng phần trăm (PDF §4.3). Không đọc nhãn."""
import numpy as np
import pandas as pd

from c4.contracts import validate

CHUNK = 2048


def rarity(z: np.ndarray, scene: np.ndarray, k: int, valid: np.ndarray | None = None) -> np.ndarray:
    """Rar(f) = trung bình ‖z(f) − z(j)‖ trên k láng giềng j thuộc scene KHÁC và hợp lệ.

    Frame không hợp lệ vẫn được tính (để hiển thị) nhưng không làm láng giềng. Không đủ k ứng
    viên ⇒ dùng tất cả ứng viên có; không có ứng viên ⇒ 0.
    """
    z = np.asarray(z, np.float64)
    scene = np.asarray(scene)
    valid = np.ones(len(z), bool) if valid is None else np.asarray(valid, bool)
    sq = (z * z).sum(1)
    out = np.zeros(len(z), np.float64)
    for s0 in range(0, len(z), CHUNK):
        sl = slice(s0, s0 + CHUNK)
        d2 = sq[sl, None] + sq[None, :] - 2.0 * (z[sl] @ z.T)
        bad = (scene[sl, None] == scene[None, :]) | ~valid[None, :]
        d2 = np.where(bad, np.inf, np.maximum(d2, 0.0))
        kk = int(max(1, min(k, len(z))))
        part = np.partition(d2, kk - 1, axis=1)[:, :kk]
        d = np.sqrt(part)
        fin = np.isfinite(d)
        out[sl] = np.where(fin.any(1), np.where(fin, d, 0).sum(1) / np.maximum(fin.sum(1), 1), 0)
    return out.astype(np.float32)


def novelty(z1: np.ndarray, z1_seed: np.ndarray) -> np.ndarray:
    """Nov(f) = min_s ‖z1(f) − z1(s)‖ trên tập seed S."""
    a = np.asarray(z1, np.float64)
    b = np.asarray(z1_seed, np.float64)
    out = np.empty(len(a))
    bb = (b * b).sum(1)
    for s0 in range(0, len(a), CHUNK):
        x = a[s0:s0 + CHUNK]
        d2 = (x * x).sum(1)[:, None] + bb[None, :] - 2 * x @ b.T
        out[s0:s0 + CHUNK] = np.sqrt(np.maximum(d2.min(1), 0))
    return out.astype(np.float32)


def pct_rank(x: np.ndarray, mask: np.ndarray) -> np.ndarray:
    """Hạng phần trăm (0..1, ties lấy trung bình) trên phần tử mask; ngoài mask = 0."""
    vals = np.asarray(x)[np.asarray(mask, bool)]
    if vals.size == 0 or np.ptp(vals) == 0:  # tín hiệu hằng (vd model seed không ra box) ⇒ 0
        return np.zeros(len(x), np.float32)
    s = pd.Series(np.where(mask, x, np.nan))
    return s.rank(pct=True, method="average").fillna(0.0).to_numpy(np.float32)


def combine(index: pd.DataFrame, keep, rar, nov, unc, alpha, beta, gamma) -> pd.DataFrame:
    keep = np.asarray(keep, bool)
    n = len(index)
    zero = np.zeros(n, np.float32)
    r_rar = pct_rank(rar, keep)
    r_nov = zero if nov is None else pct_rank(nov, keep)  # không có Tầng 1 ⇒ hạng 0, không 0.5
    r_unc = zero if unc is None else pct_rank(unc, keep)
    nov = zero if nov is None else np.asarray(nov, np.float32)
    unc = zero if unc is None else np.asarray(unc, np.float32)
    s = np.where(keep, alpha * r_rar + beta * r_nov + gamma * r_unc, 0.0)
    df = pd.DataFrame(dict(
        sample_token=index["sample_token"].to_numpy(), scene_token=index["scene_token"].to_numpy(),
        split=index["split"].to_numpy(), frame_idx=index["frame_idx"].to_numpy(), keep=keep,
        rar=rar, nov=nov, unc=unc, r_rar=r_rar, r_nov=r_nov, r_unc=r_unc,
        s=np.round(s, 6)))
    return validate(df, "lidar_scores")
