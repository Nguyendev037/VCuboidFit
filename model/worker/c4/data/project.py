"""S0b: chiếu hộp 3D annotation sang 6 camera (gt_boxes_2d) và sang hệ ego LiDAR (boxes_3d)."""
import numpy as np
import pandas as pd

from c4.contracts import BOXES_3D, CAMS, GT_BOXES_2D, validate
from c4.data.geometry import box_corners, cam_to_pixel, ego_to_cam, global_to_ego
from c4.data.nusc import NuscTables
from c4.data.rare_gt import annotations_by_sample

IMG_W, IMG_H = 1600, 900
MIN_DEPTH = 0.1


def _lidar_ego_pose(t: NuscTables, lidar_sd: dict, cam_sds: dict[str, dict]) -> dict | None:
    """Ego pose của keyframe LIDAR_TOP; không có LiDAR thì lấy camera đầu tiên theo CAMS."""
    sd = lidar_sd or next((cam_sds[c] for c in CAMS if c in cam_sds), None)
    return t.ego_pose[sd["ego_pose_token"]] if sd else None


def project_boxes(t: NuscTables, frames: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame]:
    """(gt_boxes_2d, boxes_3d) cho các sample/camera có trong `frames`.

    Mỗi camera giữ hộp có cả 8 góc z > 0.1 và ≥ 1 góc nằm trong ảnh; x1..y2 cắt về 1600×900,
    `corners` = 8 cặp (u, v) chưa cắt. boxes_3d: 8 góc × (x, y, z) trong hệ ego của LIDAR_TOP.
    """
    anns = annotations_by_sample(t)
    lidar_by_sample = {}
    for sd in t.sample_data.values():
        cal = t.calibrated_sensor[sd["calibrated_sensor_token"]]
        if sd["is_key_frame"] and t.sensor[cal["sensor_token"]]["channel"] == "LIDAR_TOP":
            lidar_by_sample[sd["sample_token"]] = sd
    cam_sd = {(s, c): t.sample_data[d]
              for s, c, d in zip(frames["sample_token"], frames["cam"], frames["sd_token"])}
    cams_of: dict[str, dict[str, dict]] = {}
    for (s, c), sd in cam_sd.items():
        cams_of.setdefault(s, {})[c] = sd

    rows2d = []
    for (sample, cam), sd in cam_sd.items():
        boxes = anns.get(sample, [])
        if not boxes:
            continue
        calib = t.calibrated_sensor[sd["calibrated_sensor_token"]]
        ego = t.ego_pose[sd["ego_pose_token"]]
        K = np.asarray(calib["camera_intrinsic"], dtype=np.float64).reshape(3, 3)
        for b in boxes:
            corners = box_corners(b["translation"], b["size"], b["rotation"])
            c_cam = ego_to_cam(global_to_ego(corners, ego), calib)
            uv, z = cam_to_pixel(c_cam, K)
            if (z <= MIN_DEPTH).any():
                continue
            inside = (uv[0] >= 0) & (uv[0] < IMG_W) & (uv[1] >= 0) & (uv[1] < IMG_H)
            if not inside.any():
                continue
            centre = ego_to_cam(global_to_ego(np.asarray(b["translation"]).reshape(3, 1), ego),
                                calib)
            rows2d.append(dict(
                sample_token=sample, cam=cam, ann_token=b["token"], category=b["category"],
                x1=np.clip(uv[0].min(), 0, IMG_W), y1=np.clip(uv[1].min(), 0, IMG_H),
                x2=np.clip(uv[0].max(), 0, IMG_W), y2=np.clip(uv[1].max(), 0, IMG_H),
                corners=uv.T.reshape(16).astype(np.float32), depth=float(centre[2, 0]),
                visibility=b["visibility"], num_lidar_pts=b["num_lidar_pts"]))

    rows3d = []
    for sample in dict.fromkeys(frames["sample_token"]):
        boxes = anns.get(sample, [])
        if not boxes:
            continue
        ego = _lidar_ego_pose(t, lidar_by_sample.get(sample), cams_of[sample])
        for b in boxes:
            corners = global_to_ego(box_corners(b["translation"], b["size"], b["rotation"]), ego)
            rows3d.append(dict(sample_token=sample, ann_token=b["token"], category=b["category"],
                               corners=corners.T.reshape(24).astype(np.float32)))
    return (validate(pd.DataFrame(rows2d, columns=list(GT_BOXES_2D)), "gt_boxes_2d"),
            validate(pd.DataFrame(rows3d, columns=list(BOXES_3D)), "boxes_3d"))
