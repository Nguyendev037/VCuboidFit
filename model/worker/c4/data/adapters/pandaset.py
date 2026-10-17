"""PandaSet world points -> LiDAR; world cuboids stay global.

Ego origin is Pandar64; each frame's +x is LiDAR yaw plus a fixed mounting delta.
Camera->world is composed with world->ego for every camera timestamp.
Pickles must match members of an archive SHA256-pinned in evidence/P2/source.txt.
Use an isolated interpreter from the installed code directory (python -I).
"""
import math
import hashlib
import tarfile
import zipfile
from pathlib import Path

import numpy as np
import pandas as pd

from c4.data.geometry import global_to_ego, quat_to_mat
from .common import (AdapterError, Writer, box_axis_angles, box_axis_check, count_points, nearest, pose, read_json,
                     relative, require, sha256, yaw_q)

CAMERAS = dict(front_camera="CAM_FRONT", front_left_camera="CAM_FRONT_LEFT",
               front_right_camera="CAM_FRONT_RIGHT", left_camera="CAM_BACK_LEFT",
               right_camera="CAM_BACK_RIGHT", back_camera="CAM_BACK")
CATEGORIES = {"Pedestrian": "human.pedestrian.adult", "Pedestrian with Object": "human.pedestrian.adult",
    "Bicycle": "vehicle.bicycle", "Motorcycle": "vehicle.motorcycle",
    "Motorized Scooter": "vehicle.motorcycle", "Personal Mobility Device": "vehicle.motorcycle",
    "Car": "vehicle.car", "Pickup Truck": "vehicle.car", "Medium-sized Truck": "vehicle.truck",
    "Semi-truck": "vehicle.truck", "Bus": "vehicle.bus.rigid",
    "Emergency Vehicle": "vehicle.emergency.police", "Cones": "movable_object.trafficcone",
    "Temporary Construction Barriers": "movable_object.barrier"}


def category(label):
    return CATEGORIES.get(label, "vehicle.truck" if label.startswith("Other Vehicle - ") else f"other.{label}")


def source_pose(row):
    return pose([row["position"][axis] for axis in "xyz"],
                [row["heading"][axis] for axis in ("w", "x", "y", "z")])


def trusted_pickles(src):
    """sha256sum lines pin original tar/zip archives, with paths relative to src.

    Verify archive bytes first, then hash pickle members without extracting them.
    Each local pickle must match its archived member before pandas may read it.
    """
    manifest = require(src / "evidence/P2/source.txt")
    entries = {}
    for line in manifest.read_text(encoding="utf-8").splitlines():
        fields = line.split(maxsplit=1)
        if len(fields) == 2 and len(fields[0]) == 64:
            entries[fields[1].lstrip("*").replace("\\", "/")] = fields[0].lower()
    hashes = {}
    for name, digest in entries.items():
        archive = require(src / name).resolve()
        if not archive.is_relative_to(src) or sha256(archive) != digest:
            raise AdapterError("SOURCE_LAYOUT", f"untrusted source archive: {archive}", 2)
        if not (tarfile.is_tarfile(archive) or zipfile.is_zipfile(archive)):
            raise AdapterError("SOURCE_LAYOUT", f"expected original tar/zip archive: {archive}", 2)

        def remember(member_name, stream):
            if not member_name.endswith(".pkl.gz"):
                return
            relative_name = member_name.removeprefix("./")
            # Archives may contain one enclosing 'pandaset' directory.
            parts = Path(relative_name).parts
            if parts and parts[0] == "pandaset":
                relative_name = Path(*parts[1:]).as_posix()
            h = hashlib.sha256()
            for block in iter(lambda: stream.read(1024 * 1024), b""):
                h.update(block)
            if relative_name in hashes and hashes[relative_name] != h.hexdigest():
                raise AdapterError("SOURCE_LAYOUT", f"conflicting archived pickle: {relative_name}", 2)
            hashes[relative_name] = h.hexdigest()

        if zipfile.is_zipfile(archive):
            with zipfile.ZipFile(archive) as source:
                for member in source.infolist():
                    if member.filename.endswith(".pkl.gz"):
                        with source.open(member) as stream:
                            remember(member.filename, stream)
        else:
            with tarfile.open(archive) as source:
                for member in source:
                    if member.isfile() and member.name.endswith(".pkl.gz"):
                        with source.extractfile(member) as stream:
                            remember(member.name, stream)
    if not hashes:
        raise AdapterError("SOURCE_LAYOUT", f"{manifest}: no pinned archive pickle members", 2)
    return hashes


def read_pickle(path, src, hashes):
    key = path.relative_to(src).as_posix()
    require(path)
    if key not in hashes or sha256(path) != hashes[key]:
        raise AdapterError("SOURCE_LAYOUT", f"untrusted pickle: {path}", 2)
    return pd.read_pickle(path)


def motion(times, poses):
    """Centred i-1 -> i+1 world displacement / elapsed seconds (one-sided ends)."""
    times = np.asarray(times, dtype=float)
    if not np.isfinite(times).all() or np.any(np.diff(times) <= 0):
        raise AdapterError("SOURCE_LAYOUT", "LiDAR timestamps must strictly increase", 2)
    positions = np.asarray([p["translation"] for p in poses])
    velocities = np.zeros_like(positions)
    if len(times) > 1:
        left = np.maximum(np.arange(len(times)) - 1, 0)
        right = np.minimum(np.arange(len(times)) + 1, len(times) - 1)
        velocities = (positions[right] - positions[left]) / (times[right] - times[left])[:, None]
    return np.arctan2(velocities[:, 1], velocities[:, 0]), np.linalg.norm(velocities[:, :2], axis=1) > 1


def pose_yaws(poses):
    return np.array([math.atan2(quat_to_mat(p["rotation"])[1, 0],
                                quat_to_mat(p["rotation"])[0, 0]) for p in poses])


def sequence_egos(times, poses, previous_delta):
    """LiDAR->world yaw + median mounting delta -> per-frame FLU ego->world."""
    headings, moving = motion(times, poses)
    lidar_yaws = pose_yaws(poses)
    borrowed = not moving.any()
    if borrowed:
        if previous_delta is None:
            raise AdapterError("EGO_AXIS", "stationary first sequence has no mounting delta to borrow")
        delta = previous_delta
    else:
        offsets = np.angle(np.exp(1j * (headings[moving] - lidar_yaws[moving])))
        delta = float(np.angle(np.exp(1j * np.median(np.unwrap(offsets)))))
    egos = [pose(p["translation"], yaw_q(yaw + delta)) for p, yaw in zip(poses, lidar_yaws)]
    return egos, delta, borrowed


def check_ego_axes(times, poses, egos):
    """Independent motion-versus-written-ego gate, including fixed-yaw mutations."""
    headings, moving = motion(times, poses)
    errors = np.degrees(np.abs(np.angle(np.exp(1j * (headings[moving] - pose_yaws(egos)[moving])))))
    p95 = float(np.percentile(errors, 95)) if len(errors) else None
    if p95 is not None and (not math.isfinite(p95) or p95 >= 5):
        raise AdapterError("EGO_AXIS", f"ego heading p95={p95} degrees")
    return p95


def interpolate_ego(timestamp, times, egos):
    """Interpolate ego->global translation and unwrapped yaw at camera time."""
    position = [np.interp(timestamp, times, [p["translation"][a] for p in egos]) for a in range(3)]
    return pose(position, yaw_q(float(np.interp(timestamp, times, np.unwrap(pose_yaws(egos))))))


def source_boxes(cuboids, offset):
    """World cuboids -> global nuScenes boxes: documented xyz=wlh, measured yaw+o."""
    preferred = set(cuboids.loc[cuboids.sensor_id.isin([-1, 0]), "uuid"])
    cuboids = cuboids.loc[~((cuboids.sensor_id == 1) & cuboids.uuid.isin(preferred))]
    return [dict(uuid=b["uuid"], label=str(b["label"]), category=category(str(b["label"])),
                 translation=[b[f"position.{a}"] for a in "xyz"],
                 size=[b[f"dimensions.{a}"] for a in "xyz"], rotation=yaw_q(b["yaw"] + offset))
            for b in cuboids.to_dict("records")]


def measure_yaw_offset(seq, n, src, hashes):
    """Measure all four yaw conventions on world car points, pooled per sequence.

    Opposite headings share one PCA axis; choose the numerically smaller offset
    in that family. A missing or ambiguous family fails closed.
    """
    offsets = (0., math.pi / 2, -math.pi / 2, math.pi)
    angles = {o: [] for o in offsets}
    clouds, cuboid_frames = [], []
    for i in range(0, n, 5):
        cloud = read_pickle(seq / f"lidar/{i:02d}.pkl.gz", src, hashes)
        xyz = cloud.loc[cloud.d == 0, ["x", "y", "z"]].to_numpy(dtype=float)
        cuboids = read_pickle(seq / f"annotations/cuboids/{i:02d}.pkl.gz", src, hashes)
        clouds.append(xyz)
        cuboid_frames.append(cuboids)
        for offset in offsets:
            angles[offset].extend(box_axis_angles(xyz, source_boxes(cuboids, offset)))
    stats = {str(o): dict(eligible_boxes=len(a), median_deg=float(np.median(a)) if a else None,
                         aligned_ratio=sum(v < 20 for v in a) / len(a) if a else None)
             for o, a in angles.items()}
    valid = {o for o, a in angles.items() if a and np.median(a) < 15 and sum(v < 20 for v in a) / len(a) >= .8}
    families = [family for family in ((0., math.pi), (-math.pi / 2, math.pi / 2)) if valid.intersection(family)]
    if len(families) != 1:
        raise AdapterError("PROJ_FAIL", f"{seq.name}: expected one yaw-offset axis family: {stats}")
    selected = min(families[0])
    check = box_axis_check(clouds, [source_boxes(c, selected) for c in cuboid_frames])
    return selected, stats, check


def adapt(src, out, logs=None, limit=None, workers=8):
    src = require(src).resolve()
    if Path.cwd().resolve() == src or src in Path.cwd().resolve().parents:
        raise AdapterError("SOURCE_LAYOUT", "do not execute from the dataset directory", 2)
    hashes = trusted_pickles(src)
    names = sorted(logs if logs is not None else [p.name for p in src.iterdir()
                                                   if p.is_dir() and (p / "lidar").is_dir()])
    if not names:
        raise AdapterError("SOURCE_LAYOUT", f"no sequences: {src}", 2)
    w = Writer("pandaset", out)
    license_file = next((p for p in [src / "LICENSE", src / "LICENSE.txt"] if p.is_file()), None)
    w.report.update(license_source=str(license_file) if license_file else "",
                    source_provenance=str(src / "evidence/P2/source.txt"), workers=workers,
                    pickle_trust="sha256-pinned archive plus member-byte verification", ego_axis_angles_deg={},
                    ego_mounting_delta={}, delta_borrowed={}, yaw_offset_stats={}, box_axis_checks={})
    previous_delta, run_offset = None, None
    for name in names:
        seq = require(src / name)
        times = read_json(seq / "lidar/timestamps.json")
        poses = [source_pose(p) for p in read_json(seq / "lidar/poses.json")]
        if len(times) != len(poses) or not times:
            raise AdapterError("SOURCE_LAYOUT", f"pose/timestamp lengths: {seq}", 2)
        egos, delta, borrowed = sequence_egos(times, poses, previous_delta)
        w.report["ego_axis_angles_deg"][name] = check_ego_axes(times, poses, egos)
        w.report["ego_mounting_delta"][name] = delta
        w.report["delta_borrowed"][name] = borrowed
        previous_delta = delta
        n = min(len(times), limit) if limit else len(times)
        offset, stats, check = measure_yaw_offset(seq, n, src, hashes)
        if run_offset is not None and offset != run_offset:
            raise AdapterError("PROJ_FAIL", f"{name}: yaw offset differs across sequences")
        run_offset = offset
        w.report["yaw_offset"] = offset
        w.report["yaw_offset_stats"][name] = stats
        w.report["box_axis_checks"][name] = check
        samples = w.scene(name, [round(times[i] * 1e6) for i in range(0, n, 5)], "pandaset")
        cameras = {}
        for cam in CAMERAS:
            folder = require(seq / "camera" / cam)
            intr = read_json(folder / "intrinsics.json")
            k = [[intr["fx"], 0, intr["cx"]], [0, intr["fy"], intr["cy"]], [0, 0, 1]]
            cameras[cam] = (folder, read_json(folder / "timestamps.json"),
                            [source_pose(p) for p in read_json(folder / "poses.json")], k)
        for i in range(n):
            sample = samples[i // 5]
            ts = round(times[i] * 1e6)
            cloud = read_pickle(seq / f"lidar/{i:02d}.pkl.gz", src, hashes)
            cloud = cloud.loc[cloud.d == 0]
            xyz = cloud[["x", "y", "z"]].to_numpy(dtype=float)
            points = np.column_stack([global_to_ego(xyz.T, poses[i]).T,
                cloud["i"].to_numpy(), np.zeros(len(cloud))])
            w.media_row(name, sample, "LIDAR_TOP", ts, egos[i], relative(poses[i], egos[i]),
                        points=points, keyframe=i % 5 == 0)
            if i % 5:
                continue
            for cam, (folder, ctimes, cposes, k) in cameras.items():
                w.report["camera_frames"] += 1
                j = nearest(ctimes, times[i], .05 + 1e-9)
                if j is None:
                    w.report["unsynced_camera_frames"] += 1
                    continue
                ego = interpolate_ego(ctimes[j], times, egos)
                w.media_row(name, sample, CAMERAS[cam], round(ctimes[j] * 1e6), ego,
                            relative(cposes[j], ego), image=folder / f"{j:02d}.jpg", intrinsic=k)
            cuboids = read_pickle(seq / f"annotations/cuboids/{i:02d}.pkl.gz", src, hashes)
            boxes = source_boxes(cuboids, offset)
            for box in boxes:
                label = str(box["label"])
                w.report["source_labels"].append(label)
                center, size, rotation = box["translation"], box["size"], box["rotation"]
                w.annotation(name, sample, box["uuid"], category(label), center, size, rotation,
                             count_points(xyz, center, size, rotation))
    return w.finish()
