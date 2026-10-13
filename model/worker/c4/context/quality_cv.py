"""C1: đặc trưng chất lượng ảnh bằng OpenCV (CPU, không mô hình) → bảng `quality_cv`.

Định nghĩa: planning/11 · 01-CONTRACTS §2, SPEC-P01. Không có ngưỡng ở đây (B3): chỉ sinh đặc trưng,
cờ CV do C3 suy từ context_thresholds_v1.json. Ảnh hỏng ⇒ img_ok=False, mọi cột số = 0 (không NaN: validate() cấm NaN).
"""
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import cv2
import numpy as np
import pandas as pd

from c4.contracts import QUALITY_CV, read_table, write_table

QUALITY_WH = (448, 252)
SAT_LEVEL = 250          # V >= 250 là bão hoà (định nghĩa, không phải ngưỡng fit)
MIN_BLOB_PX = 20
GRID = 4
BLUR_KSIZE = (5, 5)
BLUR_SIGMA = 1.0

FEATURE_KEYS = [c for c in QUALITY_CV if c not in ("sample_token", "cam", "img_ok")]
_IMMERKAER = np.array([[1, -2, 1], [-2, 4, -2], [1, -2, 1]], dtype=np.float32)
_DILATE = np.ones((3, 3), np.uint8)


def load_frames(job_dir, limit=None) -> pd.DataFrame:
    """Như c4.extract.dino.load_frames, nhưng không kéo torch (tầng bối cảnh chạy được trên bản CPU)."""
    path = Path(job_dir) / "index" / "frames.parquet"
    if not path.is_file():
        raise FileNotFoundError(f"thiếu {path} (chạy c4.cli.build_index trước)")
    frames = read_table(path, "frames")
    return frames if limit is None else frames.head(limit).reset_index(drop=True)


def _hist_percentile(hist: np.ndarray, n: int, q: float) -> float:
    """Giá trị nhỏ nhất v mà tỷ lệ pixel ≤ v đạt q (phân vị rời rạc trên histogram 256 bin)."""
    return float(np.searchsorted(np.cumsum(hist), q * n, side="left"))


def _noise_sigma(g: np.ndarray) -> float:
    """Immerkær (1996): sqrt(pi/2) / (6 (W-2)(H-2)) · Σ|g * M| trên phần lõi."""
    h, w = g.shape
    r = cv2.filter2D(g.astype(np.float32), cv2.CV_32F, _IMMERKAER, borderType=cv2.BORDER_REFLECT)
    s = float(np.abs(r[1:-1, 1:-1]).sum())
    return float(np.sqrt(np.pi / 2.0) * s / (6.0 * (w - 2) * (h - 2)))


def quality_features(img_bgr: np.ndarray) -> dict[str, float]:
    """13 đặc trưng (01 §2) từ ảnh BGR uint8 bất kỳ cỡ; luôn co về QUALITY_WH bằng INTER_AREA."""
    if (img_bgr.shape[1], img_bgr.shape[0]) != QUALITY_WH:
        img_bgr = cv2.resize(img_bgr, QUALITY_WH, interpolation=cv2.INTER_AREA)
    g = cv2.cvtColor(img_bgr, cv2.COLOR_BGR2GRAY)
    v = img_bgr.max(axis=2)  # kênh V của HSV = max(B, G, R)
    n = v.size
    hist = np.bincount(v.ravel(), minlength=256)
    v_p5, v_p95 = _hist_percentile(hist, n, 0.05), _hist_percentile(hist, n, 0.95)

    sat = (v >= SAT_LEVEL)
    sat_frac = float(sat.mean())
    blob_max, blob_count = 0.0, 0
    if sat.any():
        mask = cv2.dilate(sat.astype(np.uint8), _DILATE)
        _, _, stats, _ = cv2.connectedComponentsWithStats(mask, connectivity=8)
        areas = stats[1:, cv2.CC_STAT_AREA]
        blob_max = float(areas.max()) / n
        blob_count = int((areas >= MIN_BLOB_PX).sum())

    gh, gw = g.shape[0] // GRID, g.shape[1] // GRID
    tiles = g[:gh * GRID, :gw * GRID].reshape(GRID, gh, GRID, gw).mean(axis=(1, 3))
    sigma = _noise_sigma(g)
    lap_raw = float(cv2.Laplacian(g, cv2.CV_64F).var())
    lap_dn = float(cv2.Laplacian(cv2.GaussianBlur(g, BLUR_KSIZE, BLUR_SIGMA), cv2.CV_64F).var())
    black = v_p95 == 0
    return dict(
        luma_mean=float(g.mean()), v_mean=float(v.mean()), v_p5=v_p5, v_p95=v_p95,
        sat_frac=sat_frac, blob_max_frac=blob_max, blob_count=blob_count,
        tile_range=float(tiles.max() - tiles.min()),
        veil=0.0 if black else v_p5 / max(v_p95, 1.0),
        noise_sigma=sigma, lap_var_raw=lap_raw, lap_var_dn=lap_dn,
        sharp_ratio=0.0 if black else lap_dn / max(sigma * sigma, 1e-6))


def read_reduced(path: Path):
    """BGR đọc ở 1/2 độ phân giải (IMREAD_REDUCED_COLOR_2); None nếu hỏng. imdecode để chịu đường dẫn Unicode."""
    try:
        buf = np.fromfile(str(path), dtype=np.uint8)
        if buf.size == 0:
            return None
        return cv2.imdecode(buf, cv2.IMREAD_REDUCED_COLOR_2)
    except OSError:
        return None


def _one(path: Path) -> dict:
    img = read_reduced(path)
    if img is None:
        return {"img_ok": False, **{k: 0.0 for k in FEATURE_KEYS}}
    return {"img_ok": True, **quality_features(img)}


def extract_quality_cv(job_dir: Path, data_root: Path, *, limit: int | None = None,
                       workers: int = 0) -> pd.DataFrame:
    frames = load_frames(job_dir, limit)
    root = Path(data_root)
    paths = [root / p for p in frames["img_path"]]
    if workers and workers > 0:
        with ThreadPoolExecutor(max_workers=workers) as ex:  # cv2 nhả GIL
            rows = list(ex.map(_one, paths))
    else:
        rows = [_one(p) for p in paths]
    df = pd.DataFrame(rows, columns=["img_ok", *FEATURE_KEYS])
    df.insert(0, "cam", frames["cam"].to_numpy())
    df.insert(0, "sample_token", frames["sample_token"].to_numpy())
    out = Path(job_dir) / "cache" / "quality_cv.parquet"
    out.parent.mkdir(parents=True, exist_ok=True)
    write_table(df, out, "quality_cv")
    return df
