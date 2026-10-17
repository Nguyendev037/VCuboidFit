"""Deterministic nuScenes writer. Source -> global -> ego -> sensor uses column vectors."""
import hashlib
import json
import math
import os
from pathlib import Path
from datetime import datetime, timezone

import numpy as np
import pandas as pd
from PIL import Image

from c4.contracts import write_table
from c4.data.geometry import global_to_ego, quat_to_mat


class AdapterError(ValueError):
    def __init__(self, code, message, exit_code=3):
        super().__init__(message)
        self.code, self.exit_code = code, exit_code


def require(path):
    path = Path(path)
    if not path.exists():
        raise AdapterError("SOURCE_LAYOUT", str(path), 2)
    return path


def read_json(path):
    return json.loads(require(path).read_text(encoding="utf-8"))


def token(dataset, kind, key):
    return hashlib.sha1(f"{dataset}|{kind}|{key}".encode()).hexdigest()[:32]


def sha256(path):
    h = hashlib.sha256()
    with open(path, "rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            h.update(block)
    return h.hexdigest()


def dump(path, value):
    Path(path).write_text(json.dumps(value, sort_keys=True, indent=1,
                                    ensure_ascii=False, allow_nan=False) + "\n", encoding="utf-8",
                          newline="\n")  # LF trên mọi OS: output trùng byte giữa Windows và Colab


def qmul(a, b):
    w, x, y, z = a
    v, i, j, k = b
    return [w*v-x*i-y*j-z*k, w*i+x*v+y*k-z*j,
            w*j-x*k+y*v+z*i, w*k+x*j-y*i+z*v]


def yaw_q(yaw):
    return [math.cos(yaw / 2), 0., 0., math.sin(yaw / 2)]


def pose(translation, rotation):
    return dict(translation=list(map(float, translation)), rotation=list(map(float, rotation)))


def relative(child, parent):
    """child->global and ego->global => child->ego (inverse parent * child)."""
    q = parent["rotation"]
    return pose(global_to_ego(np.array(child["translation"]).reshape(3, 1), parent)[:, 0],
                qmul([q[0], -q[1], -q[2], -q[3]], child["rotation"]))


def transform(points, p):
    return np.asarray(points) @ quat_to_mat(p["rotation"]).T + p["translation"]


def count_points(points_global, center, size, rotation):
    local = global_to_ego(np.asarray(points_global).T, pose(center, rotation)).T
    w, length, h = size
    return int((np.abs(local) <= np.array([length, w, h]) / 2 + 1e-6).all(axis=1).sum())


def box_axis_angles(points, boxes):
    """BEV PCA versus the box's longest horizontal side (local +x if length >= width), modulo pi.

    Boxes use translation/rotation/size=[width,length,height] and category.
    Only cars with >=50 points in the rotated box, expanded 0.2m per face,
    contribute. A degenerate PCA contributes 90 degrees (cannot prove alignment).
    """
    xyz = np.asarray(points, dtype=float)[:, :3]
    angles = []
    for box in boxes:
        if box["category"] != "vehicle.car":
            continue
        local = global_to_ego(xyz.T, box).T
        width, length, height = box["size"]
        inside = (np.abs(local) <= np.array([length, width, height]) / 2 + .2).all(axis=1)
        if int(inside.sum()) < 50:
            continue
        bev = local[inside, :2]
        values, vectors = np.linalg.eigh(np.cov(bev, rowvar=False))
        if not np.isfinite(values).all() or values[-1] <= 1e-12 or values[-1] - values[0] <= 1e-12:
            angles.append(90.)
        else:
            # so với trục của cạnh ngang DÀI NHẤT: hộp đảo dài/rộng (width > length) phải lệch ~90°
            axis = 0 if length >= width else 1
            angles.append(float(np.degrees(np.arccos(np.clip(abs(vectors[axis, -1]), 0, 1)))))
    return angles


def box_axis_check(points, boxes, strict: bool = True) -> dict:
    """Check source-frame points against boxes in that same frame; fail exit 3.

    Accept one N x 3 cloud and its boxes, or matched lists of clouds/box lists
    to pool a whole sequence without mixing points from different timestamps.
    No eligible cars is reported explicitly, never used to infer a yaw offset.
    """
    if isinstance(points, np.ndarray):
        angles = box_axis_angles(points, boxes)
    else:
        angles = [a for cloud, frame_boxes in zip(points, boxes, strict=True)
                  for a in box_axis_angles(cloud, frame_boxes)]
    result = dict(eligible_boxes=len(angles), angles_deg=angles,
                  median_deg=float(np.median(angles)) if angles else None,
                  aligned_ratio=sum(a < 20 for a in angles) / len(angles) if angles else None)
    if strict and angles and result["aligned_ratio"] < .8:
        raise AdapterError("PROJ_FAIL", f"PCA/length alignment: {result}")
    return result


def pooled_axis_check(checks: dict) -> dict:
    """SPEC-P01 §6.6 trên CẢ BỘ: >= 80 % hộp car (mọi chuỗi gộp lại) có góc PCA–trục dài < 20°.

    Từng chuỗi vẫn được ghi (`box_axis_checks`); một chuỗi thấp hơn 80 % không tự làm hỏng bộ,
    vì PCA lệch khi LiDAR chỉ thấy một mặt xe. Lỗi hệ thống (đảo dài/rộng, sai yaw) làm tụt cả bộ.
    """
    angles = [a for c in checks.values() for a in c["angles_deg"]]
    result = dict(eligible_boxes=len(angles), median_deg=float(np.median(angles)) if angles else None,
                  aligned_ratio=sum(a < 20 for a in angles) / len(angles) if angles else None,
                  sequences_below_80=sorted(k for k, c in checks.items()
                                            if c["aligned_ratio"] is not None and c["aligned_ratio"] < .8))
    if angles and result["aligned_ratio"] < .8:
        raise AdapterError("PROJ_FAIL", f"PCA/length alignment (pooled): {result}")
    return result


def motion_heading_check(tracks: pd.DataFrame, min_speed: float = 2.0, max_dt: float = 0.6,
                         max_median_deg: float = 10.0) -> dict:
    """Hướng hộp so với hướng di chuyển của chính track (hệ global), mod π, độc lập với điểm LiDAR.

    tracks: uuid, ts_ns, x, y, yaw (global). Bắt lỗi thô (xoay 90°, đảo trục) mà PCA không phân xử được.
    Không có xe nào chạy > min_speed ⇒ n=0, không kết luận (không fail).
    """
    err = []
    for _, g in tracks.sort_values(["uuid", "ts_ns"]).groupby("uuid"):
        if len(g) < 2:
            continue
        dt = np.diff(g.ts_ns.to_numpy()) / 1e9
        dx, dy = np.diff(g.x.to_numpy()), np.diff(g.y.to_numpy())
        speed = np.hypot(dx, dy) / np.maximum(dt, 1e-9)
        d = np.abs((np.arctan2(dy, dx) - g.yaw.to_numpy()[1:] + np.pi / 2) % np.pi - np.pi / 2)
        err += list(np.degrees(d[(speed > min_speed) & (dt < max_dt)]))
    result = dict(n=len(err), median_deg=float(np.median(err)) if err else None,
                  p95_deg=float(np.percentile(err, 95)) if err else None)
    if err and result["median_deg"] >= max_median_deg:
        raise AdapterError("PROJ_FAIL", f"box yaw vs track motion: {result}")
    return result


def normalize_image(src, dst, intrinsic):
    """Principal-point-centred crop in source pixels -> 1600x900, K' = A K."""
    with Image.open(require(src)) as image:
        w, h = image.size
        k = np.asarray(intrinsic, dtype=float).copy()
        cw = min(w, round(h * 16 / 9))
        ch = min(h, round(w * 9 / 16))
        x0 = max(0, min(w - cw, int(round(k[0, 2] - cw / 2))))
        y0 = max(0, min(h - ch, int(round(k[1, 2] - ch / 2))))
        sx, sy = 1600 / cw, 900 / ch
        k[0] *= sx
        k[1] *= sy
        k[0, 2] -= x0 * sx
        k[1, 2] -= y0 * sy
        dst.parent.mkdir(parents=True, exist_ok=True)
        image.convert("RGB").crop((x0, y0, x0 + cw, y0 + ch)).resize(
            (1600, 900), Image.Resampling.LANCZOS).save(dst, "JPEG", quality=95)
    return k.tolist()


def nearest(times, timestamp, tolerance):
    if not times:
        return None
    i = min(range(len(times)), key=lambda j: (abs(times[j] - timestamp), times[j]))
    return i if abs(times[i] - timestamp) <= tolerance else None


class Writer:
    def __init__(self, dataset, out):
        self.dataset, self.out = dataset, Path(out)
        self.tmp = Path(str(self.out) + ".tmp")
        if self.out.exists() or self.tmp.exists():
            raise AdapterError("SOURCE_LAYOUT", f"destination already exists: {self.out} / {self.tmp}", 2)
        self.tmp.mkdir(parents=True)
        self.tables = {n: [] for n in ("scene", "sample", "sample_data", "calibrated_sensor",
                       "ego_pose", "sensor", "log", "category", "instance",
                       "sample_annotation", "visibility", "attribute")}
        self.media, self.categories, self.instances, self.streams = [], {}, {}, {}
        self.report = dict(dataset=dataset, source_labels=[], dropped_cameras={},
                           camera_frames=0, unsynced_camera_frames=0, skipped_logs=[],
                           license_source="", devkit=None)

    def tok(self, kind, key):
        return token(self.dataset, kind, key)

    def scene(self, name, timestamps, location):
        sc = self.tok("scene", name)
        log = self.tok("log", name)
        samples = [self.tok("sample", f"{name}/{i}") for i in range(len(timestamps))]
        self.tables["log"].append(dict(token=log, location=location, logfile=name,
                                       vehicle="", date_captured=""))
        self.tables["scene"].append(dict(token=sc, name=f"{self.dataset}-{name}", description="",
            log_token=log, nbr_samples=len(samples), first_sample_token=samples[0], last_sample_token=samples[-1]))
        for i, (s, ts) in enumerate(zip(samples, timestamps)):
            self.tables["sample"].append(dict(token=s, timestamp=int(ts), scene_token=sc,
                prev=samples[i-1] if i else "", next=samples[i+1] if i+1 < len(samples) else ""))
        return samples

    def media_row(self, name, sample, channel, timestamp, ego, calib, *, points=None,
                  image=None, intrinsic=None, keyframe=True):
        key = f"{name}/{channel}/{timestamp}"
        sd, ep, cs = [self.tok(k, key) for k in ("sd", "ego", "calib")]
        sensor = self.tok("sensor", channel)
        is_cam = image is not None
        if not any(r["token"] == sensor for r in self.tables["sensor"]):
            self.tables["sensor"].append(dict(token=sensor, channel=channel,
                                             modality="camera" if is_cam else "lidar"))
        filename = f"{'samples' if keyframe else 'sweeps'}/{channel}/{sd}.{'jpg' if is_cam else 'bin'}"
        target = self.tmp / filename
        target.parent.mkdir(parents=True, exist_ok=True)
        k = normalize_image(image, target, intrinsic) if is_cam else []
        if not is_cam:
            pts = np.asarray(points, dtype=np.float32)
            if pts.ndim != 2 or pts.shape[1] != 5 or not np.isfinite(pts).all():
                raise AdapterError("SOURCE_LAYOUT", "LiDAR must have finite N x 5 points", 2)
            pts[:, 3] = np.clip(pts[:, 3], 0, 255)
            pts.tofile(target)
        self.tables["ego_pose"].append(dict(token=ep, timestamp=int(timestamp), **ego))
        self.tables["calibrated_sensor"].append(dict(token=cs, sensor_token=sensor,
                                                    camera_intrinsic=k, **calib))
        row = dict(token=sd, sample_token=sample, ego_pose_token=ep, calibrated_sensor_token=cs,
                   timestamp=int(timestamp), fileformat="jpg" if is_cam else "bin",
                   is_key_frame=keyframe, filename=filename, width=1600 if is_cam else 0,
                   height=900 if is_cam else 0, prev="", next="")
        stream = self.streams.setdefault((name, channel), [])
        if stream:
            row["prev"] = stream[-1]["token"]
            stream[-1]["next"] = sd
        stream.append(row)
        self.tables["sample_data"].append(row)
        if is_cam:
            self.media.append(dict(sample_token=sample, cam=channel, img_path=filename,
                                   sha256=sha256(target), w=1600, h=900))

    def annotation(self, name, sample, uuid, category, center, size, rotation, npts):
        cat = self.tok("category", category)
        if category not in self.categories:
            self.tables["category"].append(dict(token=cat, name=category, description=""))
            self.categories[category] = cat
        inst = self.tok("instance", f"{name}/{uuid}")
        ann = dict(token=self.tok("ann", f"{sample}/{uuid}"), sample_token=sample,
            instance_token=inst, translation=list(map(float, center)), size=list(map(float, size)),
            rotation=list(map(float, rotation)), num_lidar_pts=int(npts), num_radar_pts=0,
            visibility_token="", attribute_tokens=[], prev="", next="")
        rows = self.instances.setdefault(inst, [])
        if rows:
            ann["prev"] = rows[-1]["token"]
            rows[-1]["next"] = ann["token"]
        else:
            self.tables["instance"].append(dict(token=inst, category_token=cat))
        rows.append(ann)
        self.tables["sample_annotation"].append(ann)

    def finish(self):
        for row in self.tables["instance"]:
            anns = self.instances[row["token"]]
            row.update(nbr_annotations=len(anns), first_annotation_token=anns[0]["token"],
                       last_annotation_token=anns[-1]["token"])
        version = self.tmp / f"v1.0-{self.dataset}"
        version.mkdir()
        for name, rows in self.tables.items():
            dump(version / f"{name}.json", rows)
        write_table(pd.DataFrame(self.media, columns=["sample_token", "cam", "img_path", "sha256", "w", "h"]),
                    self.tmp / "media_manifest.parquet", "media_manifest")
        # write_table adds wall-clock/git metadata. Adapter round trips include ALL JSON files.
        sidecar = self.tmp / "media_manifest.parquet.manifest.json"
        metadata = read_json(sidecar)
        first_ts = min(row["timestamp"] for row in self.tables["sample"])
        metadata["created_at"] = datetime.fromtimestamp(first_ts / 1e6, timezone.utc).isoformat()
        metadata["git_sha"] = ""
        metadata["provenance"] = "source timestamp; adapter JSON must be byte deterministic"
        dump(sidecar, metadata)
        self.report["counts"] = {n: len(rows) for n, rows in self.tables.items()}
        self.report["source_labels"] = sorted(set(self.report["source_labels"]))
        self.report["sync_ratio"] = 1 - self.report["unsynced_camera_frames"] / max(1, self.report["camera_frames"])
        self.report["validation"] = validate_output(self.tmp, self.report)
        dump(self.tmp / "ADAPTER_REPORT.json", self.report)
        os.replace(self.tmp, self.out)
        return self.report


def validate_output(root, report):
    from c4.data.index import build_frames
    from c4.data.nusc import NuscTables
    from c4.data.project import project_boxes
    from c4.lidar.index import build_lidar_index, lidar_keyframes

    if report["sync_ratio"] < .9:
        raise AdapterError("SYNC_LOW", f"sync ratio {report['sync_ratio']}")
    t = NuscTables.load(root)
    if build_lidar_index(t, root).empty:
        raise AdapterError("SOURCE_LAYOUT", "no LiDAR keyframes", 2)
    frames = build_frames(t, root)
    b2, _ = project_boxes(t, frames)
    cars = [a for a in t.sample_annotation.values()
            if t.category[t.instance[a["instance_token"]]["category_token"]]["name"] == "vehicle.car"]
    ratio = sum(a["size"][1] > a["size"][0] for a in cars) / max(1, len(cars))
    if cars and ratio < .9:
        raise AdapterError("PROJ_FAIL", "less than 90% car boxes have length > width")
    lidar = lidar_keyframes(t)
    projected = set(b2["ann_token"])
    near = [a for a in cars if a["token"] in projected and np.linalg.norm(global_to_ego(
        np.array(a["translation"]).reshape(3, 1), t.ego_pose[lidar[a["sample_token"]]["ego_pose_token"]])) <= 30]
    good = set(b2.loc[(b2.x1 + b2.x2).between(0, 3200, inclusive="left") &
                     (b2.y1 + b2.y2).between(0, 1800, inclusive="left") &
                     (b2.num_lidar_pts >= 5), "ann_token"])
    projection_ratio = sum(a["token"] in good for a in near) / max(1, len(near))
    if near and projection_ratio < .9:
        raise AdapterError("PROJ_FAIL", "less than 90% near projected cars pass")
    for media in pd.read_parquet(Path(root) / "media_manifest.parquet").to_dict("records"):
        path = Path(root) / media["img_path"]
        with Image.open(path) as im:
            if im.size != (1600, 900) or sha256(path) != media["sha256"]:
                raise AdapterError("PROJ_FAIL", str(path))
    return dict(car_length_ratio=ratio, projected_near_cars=len(near),
                projection_ratio=projection_ratio, image_count=len(frames))
