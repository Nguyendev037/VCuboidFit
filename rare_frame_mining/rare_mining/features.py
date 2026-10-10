"""M1 (phần hình học): loại mặt đất, clustering class-agnostic, trích đặc trưng.

Không phụ thuộc nhãn, không phụ thuộc model. Đường nguồn (a) trong M1 —
bắt được cả vật model BỎ SÓT (phản biện kỹ thuật + REM ECCV'22).
"""
from typing import Tuple

import numpy as np


def crop_roi(points: np.ndarray, roi) -> np.ndarray:
    if points is None or points.shape[0] == 0:
        return points
    x, y, z = points[:, 0], points[:, 1], points[:, 2]
    r2 = x * x + y * y
    m = (r2 >= roi.min_range ** 2) & (r2 <= roi.max_range ** 2) \
        & (z >= roi.z_min) & (z <= roi.z_max)
    return points[m]


def remove_ground(points: np.ndarray, cell: float = 1.0, h_thresh: float = 0.25) -> np.ndarray:
    """Loại mặt đất bằng lưới xy: ground của mỗi ô = z thấp nhất trong ô;
    foreground = điểm cao hơn ground ô của nó quá h_thresh. Vector hoá đầy đủ."""
    if points.shape[0] == 0:
        return points
    xi = np.floor(points[:, 0] / cell).astype(np.int64)
    yi = np.floor(points[:, 1] / cell).astype(np.int64)
    xy = np.stack([xi, yi], axis=1)
    uniq, inv = np.unique(xy, axis=0, return_inverse=True)
    gmin = np.full(uniq.shape[0], np.inf)
    np.minimum.at(gmin, inv, points[:, 2])
    fg = (points[:, 2] - gmin[inv]) > h_thresh
    return points[fg]


def cluster_points(pts: np.ndarray, cfg) -> np.ndarray:
    """DBSCAN trên điểm foreground. Fallback: connected-components trên voxel grid
    (scipy.ndimage) nếu thiếu sklearn."""
    if pts.shape[0] < max(3, cfg.min_samples):
        return np.zeros(pts.shape[0], dtype=int)
    try:
        from sklearn.cluster import DBSCAN
        return DBSCAN(eps=cfg.eps, min_samples=cfg.min_samples).fit_predict(pts[:, :3])
    except Exception:
        return _grid_cluster(pts[:, :3], cfg.eps)


def _grid_cluster(pts: np.ndarray, eps: float) -> np.ndarray:
    from scipy import ndimage
    vox = np.floor(pts / max(eps, 1e-6)).astype(np.int64)
    vox -= vox.min(axis=0)
    dims = vox.max(axis=0) + 1
    grid = np.zeros(tuple(dims), dtype=bool)
    grid[tuple(vox.T)] = True
    lab, _ = ndimage.label(grid, structure=np.ones((3, 3, 3)))
    return lab[tuple(vox.T)] - 1


def cluster_features(cpts: np.ndarray, ground_ref: float) -> dict:
    """Đặc trưng hình học của 1 cluster.

    Trả về: n_points, L/W/H (PCA-aligned), 3 eigenvalues chuẩn hoá, density,
    height (độ cao tâm trên mặt đất), yaw, centroid, mean_intensity.
    """
    n = int(cpts.shape[0])
    c = cpts[:, :3].mean(axis=0)
    L = W = H = 0.0
    eigs = (0.0, 0.0, 0.0)
    yaw = 0.0
    if n >= 4:
        ctr = cpts[:, :3] - c
        cov = np.cov(ctr.T)
        cov = np.atleast_2d(cov)
        evals, evecs = np.linalg.eigh(cov)  # tăng dần
        proj = ctr @ evecs
        ext = np.ptp(proj, axis=0)
        # Sửa bug (do smoke test pilot phát hiện): gán L/W/H theo HƯỚNG trục riêng,
        # không theo độ lớn extent — người đứng cao 1.7 m trước đây bị ghi H≈0.5,
        # L≈1.45 → vru_prior / person_like / template fit chết với vật cao-ngang.
        zi = int(np.argmax(np.abs(evecs[2, :])))       # trục riêng gần trục z nhất → H
        xy = sorted([i for i in range(3) if i != zi], key=lambda i: -ext[i])
        L_i, W_i = xy[0], xy[1]
        L, W, H = float(ext[L_i]), float(ext[W_i]), float(ext[zi])
        evec = evecs[:, L_i]
        yaw = float(np.arctan2(evec[1], evec[0]))
        edesc = np.array([evals[L_i], evals[W_i], evals[zi]], dtype=float)
        tot = float(edesc.sum()) + 1e-9
        eigs = (float(edesc[0] / tot), float(edesc[1] / tot), float(edesc[2] / tot))
    density = n / (L * W * H + 1e-3)
    mean_int = float(cpts[:, 3].mean()) if cpts.shape[1] >= 4 else -1.0
    return {
        "n_points": n,
        "L": L, "W": W, "H": H,
        "eig1": eigs[0], "eig2": eigs[1], "eig3": eigs[2],
        "density": density,
        "height": float(c[2] - ground_ref),
        "centroid": (float(c[0]), float(c[1]), float(c[2])),
        "yaw": yaw,
        "mean_intensity": mean_int,
    }


def vru_prior(f: dict, obj_cfg) -> float:
    """Prior hình dạng VRU (người / 2 bánh): cao 0.6–2 m, rộng ≤1.2 m.

    Phản biện domain đã ghi nhận: prior cứng 0.8–2 m bỏ sót trẻ em → nới còn 0.6.
    Cluster quá ít điểm (< min_pts_shape) → hình học không tin được → hạ điểm.
    """
    h, w = f["H"], f["W"]
    n = f["n_points"]
    if n < obj_cfg.min_pts_shape:
        return 0.3 if (obj_cfg.vru_h[0] - 0.2 <= h <= obj_cfg.vru_h[1] + 0.2 and w <= obj_cfg.vru_w + 0.2) else 0.0
    if obj_cfg.vru_h[0] <= h <= obj_cfg.vru_h[1] and w <= obj_cfg.vru_w:
        return 1.0
    if obj_cfg.vru_h[0] - 0.2 <= h <= obj_cfg.vru_h[1] + 0.2 and w <= obj_cfg.vru_w + 0.2:
        return 0.5
    return 0.0


def person_like(f: dict, frame_cfg) -> bool:
    """Ứng viên 'giống người' dùng để đếm crowd (đề bài: đông người ≥5)."""
    return (frame_cfg.crowd_h[0] <= f["H"] <= frame_cfg.crowd_h[1]
            and f["W"] <= 1.2 and f["n_points"] >= 4)
