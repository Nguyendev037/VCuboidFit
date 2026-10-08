"""Hình học nuScenes bằng NumPy thuần (công thức PDF §06, không dùng nuscenes-devkit).

Điểm là mảng (3, n). Quaternion theo thứ tự (w, x, y, z).
"""
import numpy as np


def quat_to_mat(q) -> np.ndarray:
    """Quaternion (w, x, y, z) → ma trận xoay (3, 3); tự chuẩn hoá."""
    w, x, y, z = np.asarray(q, dtype=np.float64) / np.linalg.norm(q)
    return np.array([
        [1 - 2 * (y * y + z * z), 2 * (x * y - z * w), 2 * (x * z + y * w)],
        [2 * (x * y + z * w), 1 - 2 * (x * x + z * z), 2 * (y * z - x * w)],
        [2 * (x * z - y * w), 2 * (y * z + x * w), 1 - 2 * (x * x + y * y)]])


def box_corners(center, size_wlh, rotation) -> np.ndarray:
    """8 góc hộp (3, 8) theo thứ tự nuScenes; góc 0–3 là mặt trước (+x). size = (w, l, h)."""
    w, length, h = size_wlh
    corners = np.array([
        length / 2 * np.array([1, 1, 1, 1, -1, -1, -1, -1]),
        w / 2 * np.array([1, -1, -1, 1, 1, -1, -1, 1]),
        h / 2 * np.array([1, 1, -1, -1, 1, 1, -1, -1])])
    return quat_to_mat(rotation) @ corners + np.asarray(center, dtype=np.float64).reshape(3, 1)


def _inverse_pose(p: np.ndarray, pose: dict) -> np.ndarray:
    """Điểm trong hệ cha → hệ con, với pose = vị trí/hướng của hệ con trong hệ cha."""
    t = np.asarray(pose["translation"], dtype=np.float64).reshape(3, 1)
    return quat_to_mat(pose["rotation"]).T @ (np.asarray(p, dtype=np.float64) - t)


def global_to_ego(p, ego_pose: dict) -> np.ndarray:
    return _inverse_pose(p, ego_pose)


def ego_to_cam(p, calib: dict) -> np.ndarray:
    return _inverse_pose(p, calib)


def cam_to_pixel(p, K) -> tuple[np.ndarray, np.ndarray]:
    """Điểm trong hệ camera → (uv (2, n), độ sâu z (n,)). Điểm z ≤ 0 do người gọi loại."""
    p = np.asarray(p, dtype=np.float64)
    z = p[2]
    with np.errstate(divide="ignore", invalid="ignore"):
        uv = (np.asarray(K, dtype=np.float64) @ p)[:2] / z
    return uv, z
