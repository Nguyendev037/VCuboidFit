"""nuScenes giả (định dạng v1.0-mini) để test S0/S1-S3 trên CPU mà không cần dữ liệu thật.

Tên file ảnh tất định: ``samples/<CAM>/<scene.name>_f<i>__<CAM>.jpg``;
sample_token = ``<scene.name>_f<i>``.
"""
import json
import math
from pathlib import Path

import numpy as np
from PIL import Image

from c4.contracts import CAMS

IMG_W, IMG_H = 1600, 900
N_LIDAR_PTS = 300
# camera→ego: quay quanh trục z của ego (độ) rồi nhân với hướng nhìn thẳng của CAM_FRONT
CAM_YAW_DEG = {"CAM_FRONT": 0, "CAM_FRONT_LEFT": 55, "CAM_FRONT_RIGHT": -55,
               "CAM_BACK": 180, "CAM_BACK_LEFT": 110, "CAM_BACK_RIGHT": -110}
_Q_FRONT = np.array([0.5, -0.5, 0.5, -0.5])  # (w, x, y, z): trục z camera -> trục x ego
_INTRINSIC = [[1266.4, 0.0, 816.3], [0.0, 1266.4, 491.5], [0.0, 0.0, 1.0]]
_CATEGORIES = ["human.pedestrian.adult", "vehicle.motorcycle", "vehicle.car", "animal"]
_VIS_LEVELS = {"1": "0-40%", "2": "40-60%", "3": "60-80%", "4": "80-100%"}
_BOXES = [  # (category, ego-frame xyz, size w/l/h, visibility token, lidar points)
    ("human.pedestrian.adult", (10.0, 0.0, 0.9), (0.7, 0.7, 1.8), "4", 50),
    ("vehicle.motorcycle", (15.0, 2.0, 0.8), (0.8, 2.2, 1.5), "4", 20),
]


def _qmul(a, b):
    w1, x1, y1, z1 = a
    w2, x2, y2, z2 = b
    return np.array([w1 * w2 - x1 * x2 - y1 * y2 - z1 * z2, w1 * x2 + x1 * w2 + y1 * z2 - z1 * y2,
                     w1 * y2 - x1 * z2 + y1 * w2 + z1 * x2, w1 * z2 + x1 * y2 - y1 * x2 + z1 * w2])


def _cam_rotation(cam: str) -> list[float]:
    half = math.radians(CAM_YAW_DEG[cam]) / 2
    return _qmul(np.array([math.cos(half), 0, 0, math.sin(half)]), _Q_FRONT).tolist()


def _dump(d: Path, name: str, rows: list) -> None:
    (d / f"{name}.json").write_text(json.dumps(rows), encoding="utf-8")


def _jpeg(path: Path, color) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    Image.new("RGB", (IMG_W, IMG_H), color).save(path, "JPEG", quality=30)


def make_nuscenes(root: Path, n_scenes=2, frames_per_scene=6, cams=CAMS,
                  drop_cams: dict[str, list[str]] | None = None, with_lidar=True,
                  with_annotations=True, night_scenes=(0,), rain_scenes=(),
                  corrupt: list[str] = (),
                  rare_frames: dict | None = None) -> Path:
    """Ghi bộ nuScenes giả vào ``root/data`` và trả về đường dẫn đó.

    ``drop_cams`` khoá theo tên scene ("scene0"): bỏ FILE ảnh, giữ dòng sample_data.
    ``corrupt`` là danh sách ``sample_data.filename`` được ghi thành file 0 byte.
    ``rare_frames``: ``{(scene_idx, frame_idx): [(category, (x, y, z) hệ ego, num_lidar_pts)]}``
    thêm box (category tự thêm vào bảng category) và một cụm 150 điểm dày quanh box vào LiDAR
    của frame đó (rng riêng, không đổi dữ liệu các frame khác).
    """
    data = Path(root) / "data"
    tdir = data / "v1.0-mini"
    tdir.mkdir(parents=True, exist_ok=True)
    drop_cams = drop_cams or {}
    rare_frames = rare_frames or {}
    rng = np.random.default_rng(0)
    channels = [*cams, *(["LIDAR_TOP"] if with_lidar else [])]

    sensors = [dict(token=f"sensor_{c}", channel=c,
                    modality="lidar" if c == "LIDAR_TOP" else "camera") for c in channels]
    cal, ego, scenes, samples, sds = {}, [], [], [], []
    extra_cats = [c for v in rare_frames.values() for c, *_ in v if c not in _CATEGORIES]
    cats = {n: f"cat_{i}" for i, n in enumerate([*_CATEGORIES, *dict.fromkeys(extra_cats)])}
    insts, anns = [], []
    for c in channels:
        is_cam = c != "LIDAR_TOP"
        cal[c] = dict(token=f"cal_{c}", sensor_token=f"sensor_{c}",
                      translation=[1.5, 0.0, 1.5] if is_cam else [0.9, 0.0, 1.8],
                      rotation=_cam_rotation(c) if is_cam else [1.0, 0.0, 0.0, 0.0],
                      camera_intrinsic=_INTRINSIC if is_cam else [])
    for s in range(n_scenes):
        name = f"scene{s}"
        desc = "Parked cars, Night" if s in night_scenes else (
            "Rain, wet roads" if s in rain_scenes else "Sunny, busy street")
        tokens = [f"{name}_f{i}" for i in range(frames_per_scene)]
        color = ((30 + 70 * s) % 256, (90 + 40 * s) % 256, (150 + 20 * s) % 256)
        scenes.append(dict(token=f"sc{s}", name=name, description=desc, log_token="log0",
                           nbr_samples=frames_per_scene, first_sample_token=tokens[0],
                           last_sample_token=tokens[-1]))
        prev_ann = {}
        for i, tok in enumerate(tokens):
            ts = 1_500_000_000_000_000 + s * 10_000_000_000 + i * 500_000
            ego_t = [2.0 * i, 100.0 * s, 0.0]
            ego.append(dict(token=f"ego_{tok}", timestamp=ts, rotation=[1.0, 0.0, 0.0, 0.0],
                            translation=ego_t))
            samples.append(dict(token=tok, timestamp=ts, scene_token=f"sc{s}",
                                prev=tokens[i - 1] if i else "",
                                next=tokens[i + 1] if i + 1 < frames_per_scene else ""))
            for c in channels:
                ext = "pcd.bin" if c == "LIDAR_TOP" else "jpg"
                fn = f"samples/{c}/{name}_f{i}__{c}.{ext}"
                sds.append(dict(token=f"sd_{tok}_{c}", sample_token=tok,
                                ego_pose_token=f"ego_{tok}", calibrated_sensor_token=f"cal_{c}",
                                timestamp=ts + 1000,
                                fileformat=ext, is_key_frame=True, filename=fn,
                                width=0 if c == "LIDAR_TOP" else IMG_W,
                                height=0 if c == "LIDAR_TOP" else IMG_H, prev="", next=""))
                path = data / fn
                if c == "LIDAR_TOP":
                    path.parent.mkdir(parents=True, exist_ok=True)
                    pts = rng.uniform(-30, 30, (N_LIDAR_PTS, 5)).astype(np.float32)
                    for j, (_, xyz, _) in enumerate(rare_frames.get((s, i), [])):
                        crng = np.random.default_rng(1000 + 100 * s + 10 * i + j)
                        blob = crng.normal(0.0, 0.5, (150, 5)).astype(np.float32)
                        blob[:, :3] += np.asarray(xyz, np.float32) + (0, 0, 1.0)
                        pts = np.vstack([pts, blob])
                    path.write_bytes(pts.tobytes())
                elif c in drop_cams.get(name, []):
                    continue
                elif fn in corrupt:
                    path.parent.mkdir(parents=True, exist_ok=True)
                    path.write_bytes(b"")
                else:
                    _jpeg(path, color)
            if cams:  # một sweep không phải keyframe: loader phải bỏ qua
                c = cams[0]
                fn = f"sweeps/{c}/{name}_f{i}__{c}__sweep.jpg"
                sds.append(dict(token=f"sw_{tok}_{c}", sample_token=tok,
                                ego_pose_token=f"ego_{tok}", calibrated_sensor_token=f"cal_{c}",
                                timestamp=ts + 50_000,
                                fileformat="jpg", is_key_frame=False, filename=fn,
                                width=IMG_W, height=IMG_H, prev="", next=""))
                _jpeg(data / fn, color)
            if with_annotations:
                extra = [(cat, xyz, (0.7, 0.7, 1.0), "4", npts)
                         for cat, xyz, npts in rare_frames.get((s, i), [])]
                for cat, xyz, size, vis, npts in [*_BOXES, *extra]:
                    atok = f"ann_{tok}_{cat}"
                    itok = f"inst_{name}_{cat}"
                    anns.append(dict(
                        token=atok, sample_token=tok, instance_token=itok, attribute_tokens=[],
                        visibility_token=vis, num_lidar_pts=npts, num_radar_pts=0,
                        translation=[ego_t[0] + xyz[0], ego_t[1] + xyz[1], xyz[2]],
                        size=list(size), rotation=[1.0, 0.0, 0.0, 0.0],
                        prev=prev_ann.get(cat, ""), next=""))
                    if cat in prev_ann:
                        next(a for a in anns if a["token"] == prev_ann[cat])["next"] = atok
                    prev_ann[cat] = atok
        if with_annotations:
            used = dict.fromkeys([c for c, *_ in _BOXES]
                                 + [c for (si, _), v in rare_frames.items() if si == s
                                    for c, *_ in v])
            for cat in used:
                mine = [a for a in anns if a["instance_token"] == f"inst_{name}_{cat}"]
                insts.append(dict(token=f"inst_{name}_{cat}", category_token=cats[cat],
                                  nbr_annotations=len(mine),
                                  first_annotation_token=mine[0]["token"],
                                  last_annotation_token=mine[-1]["token"]))

    # sample.json ghi ngược trong từng scene: loader phải đi theo chuỗi `next`
    samples_out = [x for s in range(n_scenes)
                   for x in reversed([m for m in samples if m["scene_token"] == f"sc{s}"])]
    _dump(tdir, "scene", scenes)
    _dump(tdir, "sample", samples_out)
    _dump(tdir, "sample_data", sds)
    _dump(tdir, "sensor", sensors)
    _dump(tdir, "calibrated_sensor", list(cal.values()))
    _dump(tdir, "ego_pose", ego)
    _dump(tdir, "log", [dict(token="log0", logfile="fake", vehicle="fake",
                             date_captured="2026-01-01", location="fake-city")])
    _dump(tdir, "map", [])
    _dump(tdir, "category", [dict(token=t, name=n, description="") for n, t in cats.items()])
    _dump(tdir, "attribute", [])
    _dump(tdir, "visibility",
          [dict(token=k, level=v, description=v) for k, v in _VIS_LEVELS.items()])
    if with_annotations:
        _dump(tdir, "instance", insts)
        _dump(tdir, "sample_annotation", anns)
    return data
