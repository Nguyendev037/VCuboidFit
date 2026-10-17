"""Lọc đối tượng AEB, giữ một camera có diện tích lớn nhất."""
import numpy as np
import pandas as pd

from c4.contracts import AEB_OBJECTS, ContractError, validate


def aeb_objects(gt_boxes_2d: pd.DataFrame, boxes_3d: pd.DataFrame, ann_meta: pd.DataFrame,
                max_dist_m: float = 40.0, corridor_half_m: float = 2.0,
                min_pts: int = 1) -> pd.DataFrame:
    meta = ann_meta.rename(columns={"token": "ann_token"})
    keys = ["sample_token", "ann_token"]
    merged = gt_boxes_2d.merge(
        boxes_3d[keys + ["corners"]].rename(columns={"corners": "corners_3d"}),
        on=keys, validate="many_to_one")
    meta_cols = ["ann_token", "instance_token", "scene_token", "num_lidar_pts"]
    if not set(meta_cols) <= set(meta):
        raise ContractError("ann_meta requires ann/instance/scene tokens and num_lidar_pts")
    merged = merged.drop(columns=["num_lidar_pts", "scene_token"], errors="ignore").merge(
        meta[meta_cols], on="ann_token", validate="many_to_one")
    rows = []
    for r in merged.itertuples():
        c = r.category
        vru = c.startswith("human.pedestrian.") or c in {"vehicle.bicycle", "vehicle.motorcycle"}
        vehicle = c in {"vehicle.car", "vehicle.truck", "vehicle.trailer"} or c.startswith(
            ("vehicle.bus.", "vehicle.emergency."))
        if not (vru or vehicle):
            continue
        corners = np.asarray(r.corners_3d, dtype=float).reshape(8, 3)
        uv = np.asarray(r.corners, dtype=float).reshape(8, 2)
        if not np.isfinite(corners).all() or not np.isfinite(uv).all():
            raise ContractError("nonfinite box corners")
        x, y = corners.mean(axis=0)[:2]
        dist = float(np.hypot(x, y))
        corridor = bool(0 < x <= max_dist_m and abs(y) <= corridor_half_m)
        area = max(0, r.x2 - r.x1) * max(0, r.y2 - r.y1)
        full = float(np.prod(np.ptp(uv, axis=0)))
        if (dist > max_dist_m or (vehicle and not corridor) or r.num_lidar_pts < min_pts
                or r.y2 - r.y1 < 20 or full <= 0 or area < 0.5 * full):
            continue
        rows.append(dict(sample_token=r.sample_token, cam=r.cam, ann_token=r.ann_token,
                         instance_token=r.instance_token, scene_token=r.scene_token,
                         category=c, group="vru" if vru else "vehicle", x1=r.x1, y1=r.y1,
                         x2=r.x2, y2=r.y2, dist_m=dist, in_corridor=corridor,
                         num_lidar_pts=r.num_lidar_pts, area=area))
    out = pd.DataFrame(rows, columns=[*AEB_OBJECTS, "area"])
    out = out.sort_values(["area", "cam"], ascending=[False, True], kind="stable")
    return validate(out.drop_duplicates(keys), "aeb_objects")
