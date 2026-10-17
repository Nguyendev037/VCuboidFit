"""Cắt một data-root nuScenes con theo danh sách scene (hồ sơ 21, pilot P1 — 15 scene VAL / 602 kf).

python -I model/scripts/subset_nusc.py --src E:/nuscenes_trainval --version v1.0-trainval \
    --scenes scene-1059..scene-1073 --out F:/vcf_ext/nusc_pilot/root

Giữ: bảng JSON lọc theo scene (con trỏ prev/next trỏ ra ngoài tập giữ ⇒ ""), ảnh 6 camera keyframe,
LIDAR_TOP keyframe + sweeps. Bỏ radar và sweeps camera (selector/giám khảo không đọc). Bảng nhỏ
(sensor, category, attribute, visibility, map) chép nguyên. Ghi SUBSET_REPORT.json (đếm + byte).
"""
from __future__ import annotations

import argparse
import json
import shutil
from pathlib import Path

KEEP_CHANNELS = ("CAM_", "LIDAR_TOP")


def _scene_names(spec: str) -> set[str]:
    out: set[str] = set()
    for part in spec.split(","):
        if ".." in part:
            a, b = part.split("..")
            lo, hi = int(a.split("-")[1]), int(b.split("-")[1])
            out |= {f"scene-{i:04d}" for i in range(lo, hi + 1)}
        else:
            out.add(part.strip())
    return out


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--src", type=Path, required=True)
    ap.add_argument("--version", default="v1.0-trainval")
    ap.add_argument("--scenes", required=True, help="scene-a..scene-b hoặc danh sách cách bằng dấu phẩy")
    ap.add_argument("--out", type=Path, required=True)
    args = ap.parse_args()

    src_t = args.src / args.version
    load = lambda name: json.loads((src_t / f"{name}.json").read_text(encoding="utf-8"))  # noqa: E731
    names = _scene_names(args.scenes)
    scenes = [s for s in load("scene") if s["name"] in names]
    if len(scenes) != len(names):
        raise SystemExit(f"thiếu scene: {sorted(names - {s['name'] for s in scenes})}")
    scene_tok = {s["token"] for s in scenes}
    samples = [s for s in load("sample") if s["scene_token"] in scene_tok]
    sample_tok = {s["token"] for s in samples}
    sensors = load("sensor")
    calib_all = {c["token"]: c for c in load("calibrated_sensor")}
    sensor_of = {c["token"]: c["sensor_token"] for c in calib_all.values()}
    channel = {s["token"]: s["channel"] for s in sensors}
    sdata = [
        d for d in load("sample_data")
        if d["sample_token"] in sample_tok
        and channel[sensor_of[d["calibrated_sensor_token"]]].startswith(KEEP_CHANNELS)
        and (d["is_key_frame"] or channel[sensor_of[d["calibrated_sensor_token"]]] == "LIDAR_TOP")
    ]
    sd_tok = {d["token"] for d in sdata}
    for d in sdata:
        for k in ("prev", "next"):
            if d[k] and d[k] not in sd_tok:
                d[k] = ""
    anns = [a for a in load("sample_annotation") if a["sample_token"] in sample_tok]
    inst_tok = {a["instance_token"] for a in anns}
    instances = [i for i in load("instance") if i["token"] in inst_tok]
    ego_tok = {d["ego_pose_token"] for d in sdata}
    ego = [e for e in load("ego_pose") if e["token"] in ego_tok]
    calib = [calib_all[t] for t in sorted({d["calibrated_sensor_token"] for d in sdata})]
    log_tok = {s["log_token"] for s in scenes}
    logs = [x for x in load("log") if x["token"] in log_tok]

    out_t = args.out / args.version
    out_t.mkdir(parents=True, exist_ok=True)
    tables = {
        "scene": scenes, "sample": samples, "sample_data": sdata, "sample_annotation": anns,
        "instance": instances, "ego_pose": ego, "calibrated_sensor": calib, "log": logs,
        "sensor": sensors, "category": load("category"), "attribute": load("attribute"),
        "visibility": load("visibility"), "map": load("map"),
    }
    for name, rows in tables.items():
        (out_t / f"{name}.json").write_text(json.dumps(rows, indent=0), encoding="utf-8")

    nbytes = 0
    for d in sdata:
        dst = args.out / d["filename"]
        if not dst.is_file():
            dst.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(args.src / d["filename"], dst)
        nbytes += dst.stat().st_size
    report = {
        "src": str(args.src), "version": args.version, "scenes": sorted(names),
        "samples": len(samples), "sample_data": len(sdata),
        "keyframe_files": sum(d["is_key_frame"] for d in sdata),
        "lidar_sweeps": sum(not d["is_key_frame"] for d in sdata),
        "annotations": len(anns), "bytes": nbytes,
    }
    (args.out / "SUBSET_REPORT.json").write_text(json.dumps(report, indent=1), encoding="utf-8")
    print(json.dumps(report))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
