"""Chẩn đoán PROJ_FAIL AV2: mỗi log đo 3 thước, chỉ đọc nguồn. Dùng đúng hàm adapter (không sửa adapter)."""
import json
import math
import sys
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, sys.argv[2])
from c4.data.adapters.common import box_axis_angles, global_to_ego, qmul, transform  # noqa: E402
from c4.data.adapters.av2 import row_pose  # noqa: E402

BASE = Path(sys.argv[1])


def yaw_of(q):
    w, x, y, z = q
    return math.atan2(2 * (w * z + x * y), 1 - 2 * (y * y + z * z))


def angles_no_ground(points, boxes):
    out = []
    for box in boxes:
        if box["category"] != "vehicle.car":
            continue
        local = global_to_ego(points.T, box).T
        w, length, h = box["size"]
        inside = ((np.abs(local[:, :2]) <= np.array([length, w]) / 2 + .2).all(axis=1)
                  & (local[:, 2] >= -h / 2 + .3) & (local[:, 2] <= h / 2))
        if inside.sum() < 50:
            continue
        vals, vecs = np.linalg.eigh(np.cov(local[inside, :2], rowvar=False))
        axis = 0 if length >= w else 1
        out.append(float(np.degrees(np.arccos(np.clip(abs(vecs[axis, -1]), 0, 1)))))
    return out


def one(name):
    folder = BASE / name
    poses = pd.read_feather(folder / "city_SE3_egovehicle.feather")
    by_ts = {int(r["timestamp_ns"]): row_pose(r) for r in poses.to_dict("records")}
    anns = pd.read_feather(folder / "annotations.feather")
    files = sorted((folder / "sensors/lidar").glob("*.feather"), key=lambda p: int(p.stem))[::5]
    a_cur, a_ng = [], []
    for path in files:
        ts = int(path.stem)
        pts = pd.read_feather(path)[["x", "y", "z"]].to_numpy()
        boxes = [dict(**row_pose(b), size=[b["width_m"], b["length_m"], b["height_m"]],
                      category="vehicle.car" if b["category"] in ("REGULAR_VEHICLE", "LARGE_VEHICLE") else "x")
                 for b in anns.loc[anns.timestamp_ns == ts].to_dict("records")]
        a_cur += box_axis_angles(pts, boxes)
        a_ng += angles_no_ground(pts, boxes)
    # Thước 3: hướng hộp (city) so với hướng di chuyển của track (city), xe > 2 m/s, mod pi
    rows = []
    for b in anns.loc[anns.category == "REGULAR_VEHICLE"].to_dict("records"):
        ego = by_ts.get(int(b["timestamp_ns"]))
        if ego is None:
            continue
        c = transform([[b["tx_m"], b["ty_m"], b["tz_m"]]], ego)[0]
        q = qmul(ego["rotation"], [b["qw"], b["qx"], b["qy"], b["qz"]])
        rows.append((b["track_uuid"], int(b["timestamp_ns"]), c[0], c[1], yaw_of(q)))
    df = pd.DataFrame(rows, columns=["uuid", "ts", "x", "y", "yaw"]).sort_values(["uuid", "ts"])
    err = []
    for _, g in df.groupby("uuid"):
        if len(g) < 3:
            continue
        dt = np.diff(g.ts.to_numpy()) / 1e9
        dx, dy = np.diff(g.x.to_numpy()), np.diff(g.y.to_numpy())
        sp = np.hypot(dx, dy) / np.maximum(dt, 1e-9)
        head = np.arctan2(dy, dx)
        yaw = g.yaw.to_numpy()[1:]
        d = np.abs((head - yaw + np.pi / 2) % np.pi - np.pi / 2)   # mod pi (lùi xe)
        err += list(np.degrees(d[(sp > 2) & (dt < 0.6)]))
    def stats(a):
        return dict(n=len(a), median=float(np.median(a)) if a else None,
                    aligned=float(np.mean(np.array(a) < 20)) if a else None)
    return name, dict(pca=stats(a_cur), pca_no_ground=stats(a_ng),
                      motion=dict(n=len(err), median=float(np.median(err)) if err else None,
                                  p95=float(np.percentile(err, 95)) if err else None,
                                  within5=float(np.mean(np.array(err) < 5)) if err else None))


if __name__ == "__main__":
    names = sorted(p.name for p in BASE.iterdir() if p.is_dir())
    with ProcessPoolExecutor(int(sys.argv[3])) as ex:
        res = dict(ex.map(one, names))
    Path(sys.argv[4]).write_text(json.dumps(res, indent=1), encoding="utf-8")
    fail = {k: v for k, v in res.items() if v["pca"]["aligned"] is not None and v["pca"]["aligned"] < .8}
    print("logs", len(res), "pca_fail", len(fail))
    for k, v in fail.items():
        print("FAIL", k, v)
    ng = [v["pca_no_ground"]["aligned"] for v in res.values() if v["pca_no_ground"]["aligned"] is not None]
    mo = [v["motion"]["p95"] for v in res.values() if v["motion"]["p95"] is not None]
    allm = [v["motion"]["median"] for v in res.values() if v["motion"]["median"] is not None]
    print("pca_no_ground aligned: min", min(ng), "n<0.8", sum(a < .8 for a in ng))
    print("motion p95 deg: median", float(np.median(mo)), "max", max(mo), "logs p95>5:", sum(m > 5 for m in mo),
          "| motion median deg max", max(allm))
