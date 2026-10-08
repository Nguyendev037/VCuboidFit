"""M3 · đọc và tiền xử lý point cloud keyframe LIDAR_TOP (.pcd.bin = float32 × 5: x, y, z,
intensity, ring). Không đọc nhãn."""
from pathlib import Path

import numpy as np


def load_pcd(path) -> np.ndarray:
    raw = np.fromfile(Path(path), dtype=np.float32)
    if raw.size == 0 or raw.size % 5:
        raise ValueError(f"{path}: kích thước {raw.size} không chia hết cho 5")
    return raw.reshape(-1, 5)


def remove_close(p: np.ndarray, radius: float) -> np.ndarray:
    """Bỏ điểm trên thân xe: |x| < r và |y| < r (đúng như nuscenes-devkit remove_close)."""
    near = (np.abs(p[:, 0]) < radius) & (np.abs(p[:, 1]) < radius)
    return p[~near]


def crop(p: np.ndarray, half: float) -> np.ndarray:
    keep = (np.abs(p[:, 0]) <= half) & (np.abs(p[:, 1]) <= half)
    return p[keep]


def voxel_downsample(p: np.ndarray, voxel: float) -> np.ndarray:
    """Giữ một điểm mỗi voxel (điểm có chỉ số nhỏ nhất) — tất định, không phụ thuộc thứ tự hash."""
    if len(p) == 0:
        return p
    key = np.floor(p[:, :3] / voxel).astype(np.int64)
    key -= key.min(axis=0)
    dims = key.max(axis=0) + 1
    flat = (key[:, 0] * dims[1] + key[:, 1]) * dims[2] + key[:, 2]
    _, first = np.unique(flat, return_index=True)
    return p[np.sort(first)]


def preprocess(p: np.ndarray, cfg: dict) -> tuple[np.ndarray, np.ndarray]:
    """Trả (điểm đã bỏ thân xe + cắt ±crop, bản voxel của nó)."""
    c = cfg["pcd"]
    q = crop(remove_close(p, c["remove_close_m"]), c["crop_m"])
    return q, voxel_downsample(q, c["voxel_m"])
