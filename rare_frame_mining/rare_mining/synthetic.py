"""Nguồn dữ liệu tổng hợp (synthetic) — dùng cho demo/test end-to-end KHÔNG cần nuScenes.

Thiết kế sao cho các slice hiếm của đề bài đều xuất hiện thật sự:
- xe đạp / xe máy (lớp hiếm) đặt rải dọc đường, một phần ở xa (>30 m);
- vật "bị chiếu yếu" (sparse factor) → <10 điểm;
- scene 'crowd' → 7-10 người gần đường;
- scene 'rain' → điểm backscatter trên không + suy giảm điểm vật thể;
- scene 'night' → CHỈ cờ metadata (LiDAR chủ động: ban đêm không thay đổi điểm —
  đúng cơ chế thật, đúng kết luận phản biện domain).
Mỗi frame: ego đi thẳng +x (8 m/s, keyframe 2 Hz). Điểm + GT đều ở frame ego.
"""
import math
from dataclasses import dataclass, field
from typing import Dict, List, Optional

import numpy as np

from .data import Frame, GTBox

SIZES = {  # (L, W, H)
    "car": (4.3, 1.9, 1.6),
    "pedestrian": (0.5, 0.5, 1.7),
    "bicycle": (1.7, 0.6, 1.5),
    "motorcycle": (2.1, 0.8, 1.5),
}
DENSITY = {"car": 900, "pedestrian": 120, "bicycle": 150, "motorcycle": 180}
INTENSITY = {"car": 0.6, "pedestrian": 0.45, "bicycle": 0.5, "motorcycle": 0.5, "ground": 0.28}


@dataclass
class _Obj:
    cls: str
    x: float
    y: float
    yaw: float
    sparse: bool = False
    attrs: tuple = ()


class SyntheticSource:
    """Sinh 1 làng đường thẳng; points được tái sinh lazy theo seed frame."""

    def __init__(self, n_scenes: int = 8, frames_per_scene: int = 50, seed: int = 0,
                 dt: float = 0.5, speed: float = 8.0):
        self.n_scenes = n_scenes
        self.nf = frames_per_scene
        self.seed = seed
        self.dt = dt
        self.speed = speed
        self._scenes = [self._build_scene(s) for s in range(n_scenes)]

    # ---------------- dựng scene ----------------
    def _build_scene(self, s: int) -> dict:
        rng = np.random.default_rng(self.seed * 977 + s)
        kind = rng.choice(["normal", "normal", "normal", "crowd", "rain", "mixed"],
                          p=[0.4, 0.15, 0.1, 0.15, 0.1, 0.1])
        night = bool(kind == "mixed" or rng.random() < 0.2)
        rain = float(rng.uniform(0.4, 1.0)) if kind in ("rain", "mixed") else 0.0
        road_len = self.speed * self.dt * self.nf + 60.0

        objs: List[_Obj] = []
        n_car = int(rng.integers(10, 16))
        for _ in range(n_car):
            lane = rng.choice([-3.5, 3.5, -7.5, 7.5])
            objs.append(_Obj("car", float(rng.uniform(10, road_len)),
                             float(lane + rng.normal(0, 0.4)), float(rng.uniform(-0.2, 0.2))))
        n_ped = int(rng.integers(0, 5))
        for _ in range(n_ped):
            objs.append(_Obj("pedestrian", float(rng.uniform(10, road_len)),
                             float(rng.choice([-10.0, 10.0]) + rng.normal(0, 1.0)),
                             float(rng.uniform(-math.pi, math.pi))))
        if kind == "crowd":
            cx, cy = float(rng.uniform(30, road_len - 30)), float(rng.uniform(6.0, 9.0))
            for _ in range(int(rng.integers(7, 11))):
                objs.append(_Obj("pedestrian", cx + float(rng.normal(0, 3.5)),
                                 cy + float(rng.normal(0, 1.5)),
                                 float(rng.uniform(-math.pi, math.pi))))
        # lớp hiếm: xe đạp / xe máy — 45% được đặt ở vùng "xa" phía trước
        for cls, p in (("bicycle", 0.8), ("motorcycle", 0.6)):
            if rng.random() < p:
                for _ in range(int(rng.integers(1, 3))):
                    far = rng.random() < 0.45
                    lane_y = float(rng.choice([-3.5, 3.5, -5.0, 5.0]))
                    objs.append(_Obj(
                        cls, float(rng.uniform(road_len * 0.55, road_len - 15) if far
                                  else rng.uniform(10, road_len)),
                        lane_y + float(rng.normal(0, 0.3)),
                        float(rng.uniform(-0.3, 0.3) + (0 if lane_y < 0 else math.pi)),
                        attrs=("cycle.with_rider",) if rng.random() < 0.6 else ()))
        for o in objs:
            if rng.random() < 0.15:
                o.sparse = True  # góc chiếu hớt → ít điểm (slice <10 điểm)

        desc = ("Night, " if night else "Daytime, ") + \
               ("heavy rain." if rain > 0.6 else ("light rain." if rain > 0 else "clear."))
        return {"id": f"scene_{s:03d}", "kind": kind, "night": night, "rain": rain,
                "desc": desc, "objs": objs, "t0": float(s) * 1e6}

    # ---------------- sinh điểm 1 frame ----------------
    def _render_frame(self, si: int, k: int) -> tuple:
        sc = self._scenes[si]
        rng = np.random.default_rng(hash((self.seed, si, k)) % (2 ** 32))
        ego_x = self.speed * self.dt * k
        ego = np.array([ego_x, 0.0])
        t = k * self.dt

        # mặt đất: đĩa bán kính 50 m quanh ego
        r = 50.0 * np.sqrt(rng.random(9000))
        th = rng.uniform(0, 2 * math.pi, 9000)
        gx, gy = ego[0] + r * np.cos(th), ego[1] + r * np.sin(th)
        gz = rng.normal(0.0, 0.03, 9000)
        gi = rng.uniform(0.18, 0.36, 9000)
        pts = [np.stack([gx, gy, gz, gi], axis=1)]
        gt_boxes: List[GTBox] = []

        n_rain = int(sc["rain"] * 1200)
        for o in sc["objs"]:
            rel = np.array([o.x - ego[0], o.y - ego[1]])
            dist = float(np.hypot(rel[0], rel[1]))
            if dist > 48.0 or rel[0] < -5.0:
                continue
            L, W, H = SIZES[o.cls]
            lam = DENSITY[o.cls] * math.exp(-dist / 18.0) * (0.75 if sc["rain"] else 1.0)
            if o.sparse:
                lam *= 0.06
            n = int(rng.poisson(max(lam, 0.0)))
            if n <= 0:
                continue
            loc = rng.uniform([-L / 2, -W / 2, 0.0], [L / 2, W / 2, H], size=(n, 3))
            c, s = math.cos(o.yaw), math.sin(o.yaw)
            R = np.array([[c, -s], [s, c]])
            xy = loc[:, :2] @ R.T + rel
            z = loc[:, 2]
            inten = rng.normal(INTENSITY[o.cls], 0.08, n).clip(0.02, 0.95)
            pts.append(np.stack([xy[:, 0], xy[:, 1], z, inten], axis=1))
            cbox = np.array([rel[0], rel[1], H / 2])
            gt_boxes.append(GTBox(center=(float(cbox[0]), float(cbox[1]), float(cbox[2])),
                                  size=(L, W, H), yaw=float(o.yaw), class_name=o.cls,
                                  attributes=o.attrs))
        if n_rain:
            rr = 45.0 * np.sqrt(rng.random(n_rain))
            th2 = rng.uniform(0, 2 * math.pi, n_rain)
            rx, ry = ego[0] + rr * np.cos(th2), ego[1] + rr * np.sin(th2)
            rz = rng.uniform(0.2, 3.5, n_rain)
            ri = rng.uniform(0.02, 0.15, n_rain)
            pts.append(np.stack([rx, ry, rz, ri], axis=1))

        P = np.concatenate(pts, axis=0).astype(np.float32)
        P = P[rng.permutation(P.shape[0])]
        # đếm num_lidar_pts trong từng GT box (đúng định nghĩa nuScenes)
        for g in gt_boxes:
            L, W, H = g.size
            c, s = math.cos(g.yaw), math.sin(g.yaw)
            dx, dy = P[:, 0] - g.center[0], P[:, 1] - g.center[1]
            u = dx * c + dy * s
            v = -dx * s + dy * c
            inside = (np.abs(u) <= L / 2) & (np.abs(v) <= W / 2) \
                & (P[:, 2] >= g.center[2] - H / 2) & (P[:, 2] <= g.center[2] + H / 2)
            g.num_lidar_pts = int(inside.sum())
        return P, gt_boxes, t

    # ---------------- interface giống các nguồn khác ----------------
    def frames(self) -> List[Frame]:
        out: List[Frame] = []
        for si, sc in enumerate(self._scenes):
            for k in range(self.nf):
                fid = f"{sc['id']}_f{k:04d}"
                ego = (self.speed * self.dt * k, 0.0)

                def loader(si=si, k=k):
                    return self._render_frame(si, k)[0]

                def gtget(si=si, k=k):
                    return self._render_frame(si, k)[1]

                out.append(Frame(fid=fid, scene=sc["id"], t=k * self.dt, ego_xy=ego,
                                 desc=sc["desc"], loader=loader, gt_fn=gtget))
        return out
