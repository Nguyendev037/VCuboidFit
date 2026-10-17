"""AV2 ego points -> up_lidar sensor; ego annotations -> city/global.

Camera optical +z transformed by ego_SE3_camera determines yaw (not optical +x).
Sensor extrinsics are sensor->ego; city poses are ego->global at each media timestamp.
"""
import math

import numpy as np
import pandas as pd

from .common import (AdapterError, Writer, box_axis_check, motion_heading_check, nearest, pooled_axis_check,
                     pose, qmul, require, transform)
from c4.data.geometry import global_to_ego, quat_to_mat

SLOTS = [("CAM_FRONT", 0), ("CAM_FRONT_LEFT", 55), ("CAM_FRONT_RIGHT", -55),
         ("CAM_BACK_LEFT", 110), ("CAM_BACK_RIGHT", -110), ("CAM_BACK", 180)]
GROUPS = {
    "human.pedestrian.adult": ["PEDESTRIAN", "OFFICIAL_SIGNALER"],
    "human.pedestrian.stroller": ["STROLLER"], "human.pedestrian.wheelchair": ["WHEELCHAIR"],
    "vehicle.bicycle": ["BICYCLE", "BICYCLIST"],
    "vehicle.motorcycle": ["MOTORCYCLE", "MOTORCYCLIST", "WHEELED_RIDER"],
    "vehicle.car": ["REGULAR_VEHICLE", "LARGE_VEHICLE"],
    "vehicle.truck": ["BOX_TRUCK", "TRUCK", "TRUCK_CAB"],
    "vehicle.bus.rigid": ["BUS", "SCHOOL_BUS", "ARTICULATED_BUS"],
    "movable_object.trafficcone": ["CONSTRUCTION_CONE"],
    "movable_object.barrier": ["CONSTRUCTION_BARREL"]}
CATEGORIES = {label: category for category, labels in GROUPS.items() for label in labels}


def row_pose(row):
    return pose([row[f"t{a}_m"] for a in "xyz"], [row[f"q{a}"] for a in "wxyz"])


def select_cameras(calibrations):
    yaws = {}
    for name, p in calibrations.items():
        optical_z = quat_to_mat(p["rotation"])[:, 2]
        yaws[name] = math.degrees(math.atan2(optical_z[1], optical_z[0]))
    available, selected = set(yaws), {}
    for slot, yaw in SLOTS:
        if not available:
            raise AdapterError("SOURCE_LAYOUT", "AV2 requires at least six ring cameras", 2)
        best = min(available, key=lambda c: (round(abs((yaws[c] - yaw + 180) % 360 - 180), 8), c))
        selected[slot] = best
        available.remove(best)
    return selected, sorted(available)


def feather(path):
    return pd.read_feather(require(path))


def adapt(src, out, logs=None, limit=None, workers=8):
    src = require(src)
    base = src / "val" if (src / "val").is_dir() else src
    names = sorted(logs if logs is not None else [p.name for p in base.iterdir() if p.is_dir()])
    if not names:
        raise AdapterError("SOURCE_LAYOUT", f"no logs: {base}", 2)
    w = Writer("av2", out)
    w.report.update(license_source="Argoverse 2 Sensor: CC BY-NC-SA 4.0 (source distribution)",
                    workers=workers, camera_assignment={}, box_axis_checks={}, motion_heading_checks={})
    for name in names:
        folder = require(base / name)
        axis_clouds, axis_boxes, tracks = [], [], []
        intr = feather(folder / "calibration/intrinsics.feather").set_index("sensor_name")
        extr = feather(folder / "calibration/egovehicle_SE3_sensor.feather")
        calib = {row["sensor_name"]: row_pose(row) for row in extr.to_dict("records")}
        if "up_lidar" not in calib:
            raise AdapterError("SOURCE_LAYOUT", f"{folder}: up_lidar calibration", 2)
        selected, dropped = select_cameras({k: v for k, v in calib.items() if k.startswith("ring_")})
        w.report["dropped_cameras"][name] = dropped
        w.report["camera_assignment"][name] = selected
        poses = feather(folder / "city_SE3_egovehicle.feather")
        by_ts = {int(row["timestamp_ns"]): row_pose(row) for row in poses.to_dict("records")}
        anns = feather(folder / "annotations.feather")
        files = sorted(require(folder / "sensors/lidar").glob("*.feather"), key=lambda p: int(p.stem))
        if limit:
            files = files[:limit]
        if not files:
            raise AdapterError("SOURCE_LAYOUT", f"no LiDAR: {folder}", 2)
        samples = w.scene(name, [int(p.stem) // 1000 for p in files[::5]],
                          str(poses["city_name"].iloc[0]) if "city_name" in poses else "")
        camfiles = {}
        for cam in selected.values():
            paths = sorted(require(folder / "sensors/cameras" / cam).glob("*.jpg"), key=lambda p: int(p.stem))
            camfiles[cam] = (paths, [int(p.stem) for p in paths])
        for i, path in enumerate(files):
            ts = int(path.stem)
            if ts not in by_ts:
                raise AdapterError("SOURCE_LAYOUT", f"missing ego pose {name}/{ts}", 2)
            ego, sample = by_ts[ts], samples[i // 5]
            cloud = feather(path)
            points = np.column_stack([global_to_ego(cloud[["x", "y", "z"]].to_numpy().T,
                                                   calib["up_lidar"]).T,
                                      cloud["intensity"], cloud["laser_number"]])
            w.media_row(name, sample, "LIDAR_TOP", ts // 1000, ego, calib["up_lidar"],
                        points=points, keyframe=i % 5 == 0)
            if i % 5:
                continue
            for slot, cam in selected.items():
                w.report["camera_frames"] += 1
                paths, times = camfiles[cam]
                j = nearest(times, ts, 50_000_000)
                if j is None:
                    w.report["unsynced_camera_frames"] += 1
                    continue
                cts = times[j]
                if cts not in by_ts:
                    raise AdapterError("SOURCE_LAYOUT", f"missing camera ego pose {name}/{cts}", 2)
                row = intr.loc[cam]
                k = [[row["fx_px"], 0, row["cx_px"]], [0, row["fy_px"], row["cy_px"]], [0, 0, 1]]
                w.media_row(name, sample, slot, cts // 1000, by_ts[cts], calib[cam], image=paths[j], intrinsic=k)
            frame_boxes = anns.loc[anns.timestamp_ns == ts].to_dict("records")
            # AV2 points and annotations are both ego-frame here; no global/sensor mix.
            axis_clouds.append(cloud[["x", "y", "z"]].to_numpy())
            axis_boxes.append([dict(**row_pose(b), size=[b["width_m"], b["length_m"], b["height_m"]],
                      category=CATEGORIES.get(str(b["category"]), f"other.{b['category']}"))
                 for b in frame_boxes])
            for box in frame_boxes:
                label = str(box["category"])
                w.report["source_labels"].append(label)
                center = transform([[box[f"t{a}_m"] for a in "xyz"]], ego)[0]
                rotation = qmul(ego["rotation"], [box[f"q{a}"] for a in "wxyz"])
                if CATEGORIES.get(label) == "vehicle.car":
                    w_, x_, y_, z_ = rotation
                    tracks.append((box["track_uuid"], ts, center[0], center[1],
                                   math.atan2(2 * (w_ * z_ + x_ * y_), 1 - 2 * (y_ * y_ + z_ * z_))))
                w.annotation(name, sample, box["track_uuid"], CATEGORIES.get(label, f"other.{label}"),
                    center, [box["width_m"], box["length_m"], box["height_m"]], rotation,
                    box["num_interior_pts"])
        w.report["box_axis_checks"][name] = box_axis_check(axis_clouds, axis_boxes, strict=False)
        w.report["motion_heading_checks"][name] = motion_heading_check(
            pd.DataFrame(tracks, columns=["uuid", "ts_ns", "x", "y", "yaw"]))
    w.report["box_axis_pooled"] = pooled_axis_check(w.report["box_axis_checks"])
    return w.finish()
