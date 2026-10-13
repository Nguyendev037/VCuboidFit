"""M3a · chiếu box ứng viên LiDAR (hệ ego) sang 6 camera, giữ camera nhìn rõ nhất (planning/11 SPEC-P06 §3).
Chỉ hình học; không đọc nhãn. Lệch thời gian LiDAR-camera bỏ qua (SPEC-P06 §8)."""
import numpy as np
import pandas as pd

from c4.contracts import CAMS, SPEC
from c4.data.geometry import box_corners, cam_to_pixel, ego_to_cam
from c4.data.project import IMG_H, IMG_W, MIN_DEPTH

_COLS = list(SPEC["rare_obj_cam"][0])


def _corners_ego(objs: pd.DataFrame) -> np.ndarray:
    """(n, 3, 8) góc box trong hệ ego. size theo thứ tự (w, l, h); quaternion yaw (cos(yaw/2), 0, 0, sin(yaw/2))."""
    out = np.empty((len(objs), 3, 8))
    for k, r in enumerate(objs[["cx", "cy", "cz", "w", "l", "h", "yaw"]].to_numpy(np.float64)):
        q = (np.cos(r[6] / 2), 0.0, 0.0, np.sin(r[6] / 2))
        out[k] = box_corners(r[:3], r[3:6], q)
    return out


def project_objects(objs: pd.DataFrame, cam_poses: pd.DataFrame, min_visible: float = 0.3) -> pd.DataFrame:
    """-> bảng `rare_obj_cam` (khoá sample_token, object_id): cam, x1, y1, x2, y2 (đã cắt về 1600×900), visible_frac.

    Mỗi vật × 6 camera: 8 góc; bỏ camera nếu có góc z <= MIN_DEPTH; visible_frac = diện tích bbox đã cắt / chưa cắt.
    Giữ ĐÚNG MỘT camera có visible_frac lớn nhất (hoà: theo thứ tự CAMS); < min_visible => không có hàng."""
    rows = []
    poses = {(t, c): r for t, c, r in zip(cam_poses["sample_token"], cam_poses["cam"],
                                           cam_poses.to_dict("records"))}
    for tok, g in objs.groupby("sample_token", sort=False):
        ego = _corners_ego(g)                                   # (n, 3, 8)
        flat = ego.transpose(1, 0, 2).reshape(3, -1)            # (3, n*8)
        n = len(g)
        best = np.full(n, -1.0)
        box = np.zeros((n, 4))
        cam_of = [""] * n
        for cam in CAMS:
            pose = poses.get((tok, cam))
            if pose is None:
                continue
            pc = ego_to_cam(flat, pose)
            uv, z = cam_to_pixel(pc, np.asarray(pose["intrinsic"], np.float64).reshape(3, 3))
            u, v = uv[0].reshape(n, 8), uv[1].reshape(n, 8)
            front = (z.reshape(n, 8) > MIN_DEPTH).all(1)
            x1, x2, y1, y2 = u.min(1), u.max(1), v.min(1), v.max(1)
            area = (x2 - x1) * (y2 - y1)
            cx1, cx2 = np.clip(x1, 0, IMG_W), np.clip(x2, 0, IMG_W)
            cy1, cy2 = np.clip(y1, 0, IMG_H), np.clip(y2, 0, IMG_H)
            carea = np.clip(cx2 - cx1, 0, None) * np.clip(cy2 - cy1, 0, None)
            with np.errstate(divide="ignore", invalid="ignore"):
                vis = np.where(front & (area > 0), carea / area, -1.0)
            better = vis > best + 1e-12
            for k in np.flatnonzero(better):
                best[k], box[k], cam_of[k] = vis[k], (cx1[k], cy1[k], cx2[k], cy2[k]), cam
        for k, oid in enumerate(g["object_id"]):
            if best[k] >= min_visible and best[k] > 0:
                rows.append((tok, oid, cam_of[k], *box[k], best[k]))
    df = pd.DataFrame(rows, columns=_COLS)
    return df.astype({"sample_token": "string", "object_id": "string", "cam": "string",
                      **{c: "float32" for c in ("x1", "y1", "x2", "y2", "visible_frac")}})
