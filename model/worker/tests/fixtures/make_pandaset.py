"""Tiny source-shaped PandaSet: two sequences, ten 10 Hz frames, trusted local pickles."""
import math
import tarfile
from pathlib import Path

import numpy as np
import pandas as pd
from PIL import Image

from c4.data.adapters.common import dump, pose, qmul, sha256, transform, yaw_q

YAW = math.radians(20)
# Documented dimensions.x=width, dimensions.y=length. The undocumented source
# yaw convention is an independent fixture choice: heading_nusc = yaw - pi/2.
YAW_OFFSET = -math.pi / 2
POINT_COUNT = 135
FRONT = [.5, -.5, .5, -.5]
CAM_YAWS = dict(front_camera=0, front_left_camera=55, front_right_camera=-55,
                left_camera=110, right_camera=-110, back_camera=180)


def source_pose(p):
    return dict(position=dict(zip("xyz", p["translation"])), heading=dict(zip("wxyz", p["rotation"])))


def make_pandaset(root: Path, n_sequences=2, n_frames=10):
    root = Path(root)
    root.mkdir(parents=True)
    for s in range(n_sequences):
        folder = root / f"{s:03d}"
        lidar = folder / "lidar"
        cuboids = folder / "annotations/cuboids"
        lidar.mkdir(parents=True)
        cuboids.mkdir(parents=True)
        times = [1_600_000_000. + i * .1 for i in range(n_frames)]
        # Sequence 1 turns 60 degrees across the +/-pi seam; sequence 0 is straight.
        start = YAW if s == 0 else math.radians(170)
        headings = np.full(n_frames, start) if s == 0 else np.linspace(start, start + math.pi / 3, n_frames)
        if s == 0:
            positions = transform([[i, 0, 0] for i in range(n_frames)], pose([0, 100*s, 0], yaw_q(start)))
        else:
            positions = np.column_stack([10 * (np.sin(headings) - math.sin(start)),
                                         100*s + 10 * (math.cos(start) - np.cos(headings)),
                                         np.zeros(n_frames)])
        egos = [pose(position, yaw_q(heading)) for position, heading in zip(positions, headings)]
        sensor_poses = [pose(e["translation"], yaw_q(heading + .2)) for e, heading in zip(egos, headings)]
        dump(lidar / "timestamps.json", times)
        dump(lidar / "poses.json", [source_pose(p) for p in sensor_poses])
        for cam in CAM_YAWS:
            directory = folder / "camera" / cam
            directory.mkdir(parents=True)
            camera_times = [t + .025 for t in times]
            dump(directory / "timestamps.json", camera_times)
            dump(directory / "intrinsics.json", dict(fx=1000., fy=1000., cx=960., cy=540.))
            camera_poses = []
            for t in camera_times:
                position = [np.interp(t, times, positions[:, a]) for a in range(3)]
                heading = np.interp(t, times, headings)
                rotations = qmul(yaw_q(heading + math.radians(CAM_YAWS[cam])), FRONT)
                camera_poses.append(source_pose(pose(np.array(position) + [0, 0, 1.5], rotations)))
            dump(directory / "poses.json", camera_poses)
            for i in range(n_frames):
                Image.new("RGB", (1920, 1080), (30+s, 70+i, 110)).save(directory / f"{i:02d}.jpg")
        for i, ego in enumerate(egos):
            # Elongated car: 135 primary points, enough for independent BEV PCA.
            offsets = np.array([(x, y, z) for x in np.linspace(-1.6, 1.6, 9)
                                for y in np.linspace(-.6, .6, 5) for z in [-.3, 0., .3]])
            world = transform(offsets + [12, 0, 1], ego)
            points = pd.DataFrame(world, columns=["x", "y", "z"])
            points["i"], points["d"] = 128., 0
            extra = points.iloc[[0]].copy()
            extra["d"] = 1
            pd.concat([points, extra], ignore_index=True).to_pickle(lidar / f"{i:02d}.pkl.gz")
            center = transform([[12, 0, 1]], ego)[0]
            box = {"uuid": "car-track", "label": "Car", "sensor_id": -1,
                   "yaw": headings[i] - YAW_OFFSET, **{f"position.{a}": float(v) for a, v in zip("xyz", center)},
                   "dimensions.x": 2., "dimensions.y": 4., "dimensions.z": 1.6}
            pd.DataFrame([box, dict(box, sensor_id=1)]).to_pickle(cuboids / f"{i:02d}.pkl.gz")
    trust = root / "evidence/P2/source.txt"
    trust.parent.mkdir(parents=True)
    archive = root / "source-fixture.tar"
    with tarfile.open(archive, "w") as stream:
        for path in sorted(root.rglob("*.pkl.gz")):
            stream.add(path, arcname=path.relative_to(root).as_posix())
    trust.write_text(f"{sha256(archive)}  {archive.name}\n", encoding="utf-8")
    return root
