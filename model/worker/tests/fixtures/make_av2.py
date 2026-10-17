"""Tiny AV2 Sensor VAL source with genuine feather/image paths and nontrivial poses."""
import math
from pathlib import Path

import numpy as np
import pandas as pd
from PIL import Image

from c4.data.adapters.common import pose, qmul, yaw_q

YAW = dict(ring_front_center=0, ring_front_left=45, ring_front_right=-45,
           ring_side_left=90, ring_side_right=-90, ring_rear_left=150, ring_rear_right=-150)


def pose_row(p):
    return {**dict(zip([f"t{a}_m" for a in "xyz"], p["translation"])),
            **dict(zip([f"q{a}" for a in "wxyz"], p["rotation"]))}


def make_av2(root: Path, n_sequences=2, n_frames=10):
    root = Path(root)
    for s in range(n_sequences):
        folder = root / "val" / f"log-{s}"
        (folder / "calibration").mkdir(parents=True)
        (folder / "sensors/lidar").mkdir(parents=True)
        times = [1_600_000_000_000_000_000 + i * 100_000_000 for i in range(n_frames)]
        intr, extr = [], [dict(sensor_name="up_lidar", **pose_row(pose([.3, -.2, 1.], yaw_q(.15))))]
        for cam, yaw in YAW.items():
            width, height = (1550, 2048) if cam == "ring_front_center" else (2048, 1550)
            intr.append(dict(sensor_name=cam, fx_px=1100., fy_px=1100., cx_px=width/2, cy_px=height/2))
            rotation = qmul(yaw_q(math.radians(yaw)), [.5, -.5, .5, -.5])
            extr.append(dict(sensor_name=cam, **pose_row(pose([0, 0, 1.5], rotation))))
            camera = folder / "sensors/cameras" / cam
            camera.mkdir(parents=True)
            for i, ts in enumerate(times):
                Image.new("RGB", (width, height), (40+s, 80+i, 120)).save(camera / f"{ts}.jpg")
        pd.DataFrame(intr).to_feather(folder / "calibration/intrinsics.feather")
        pd.DataFrame(extr).to_feather(folder / "calibration/egovehicle_SE3_sensor.feather")
        poses, anns = [], []
        for i, ts in enumerate(times):
            ego = pose([i * math.cos(.3), 100*s + i * math.sin(.3), 0], yaw_q(.3))  # chạy theo mũi xe
            poses.append(dict(timestamp_ns=ts, city_name="PIT", **pose_row(ego)))
            points = np.array([(x+12, y, z+1) for x in np.linspace(-1.6, 1.6, 9)
                               for y in np.linspace(-.6, .6, 5) for z in [-.3, 0., .3]])
            cloud = pd.DataFrame(points, columns=["x", "y", "z"])
            cloud["intensity"], cloud["laser_number"] = 128., np.arange(len(points)) % 2
            cloud.to_feather(folder / f"sensors/lidar/{ts}.feather")
            anns.append(dict(timestamp_ns=ts, track_uuid="car-track", category="REGULAR_VEHICLE",
                **pose_row(pose([12, 0, 1], yaw_q(0))), length_m=4., width_m=2., height_m=1.6,
                num_interior_pts=len(points)))
        pd.DataFrame(poses).to_feather(folder / "city_SE3_egovehicle.feather")
        pd.DataFrame(anns).to_feather(folder / "annotations.feather")
    return root
