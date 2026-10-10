"""Hàm tiện ích: hình học BEV, rank, Mahalanobis, thống kê, IO."""
import csv
import json
import logging
import math
import os
import random
from typing import List, Sequence

import numpy as np


def set_seed(seed: int) -> None:
    np.random.seed(seed)
    random.seed(seed)


def get_logger(name: str) -> logging.Logger:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    return logging.getLogger(name)


# ---------------------------------------------------------------------------
# Hình học BEV (box xoay) — polygon clip, không phụ thuộc thư viện ngoài
# ---------------------------------------------------------------------------

def rot2d(deg: float) -> np.ndarray:
    r = math.radians(deg)
    c, s = math.cos(r), math.sin(r)
    return np.array([[c, -s], [s, c]])


def box_corners_bev(cx: float, cy: float, length: float, width: float, yaw: float) -> np.ndarray:
    c, s = math.cos(yaw), math.sin(yaw)
    R = np.array([[c, -s], [s, c]])
    local = np.array([
        [length / 2, width / 2], [length / 2, -width / 2],
        [-length / 2, -width / 2], [-length / 2, width / 2],
    ])
    return local @ R.T + np.array([cx, cy])


def poly_area(poly: np.ndarray) -> float:
    if len(poly) < 3:
        return 0.0
    x, y = poly[:, 0], poly[:, 1]
    return 0.5 * abs(float(np.dot(x, np.roll(y, -1)) - np.dot(y, np.roll(x, -1))))


def _signed_area(poly: np.ndarray) -> float:
    # cùng quy ước poly_area (roll -1): CCW → dương
    x, y = poly[:, 0], poly[:, 1]
    return 0.5 * float(np.dot(x, np.roll(y, -1)) - np.dot(y, np.roll(x, -1)))


def clip_polygon(subject: np.ndarray, clip: np.ndarray) -> np.ndarray:
    """Sutherland–Hodgman: cắt polygon `subject` bởi polygon lồi `clip`.
    Clip được chuẩn hoá ngược chiều kim đồng hồ; subject bất kỳ chiều nào."""
    clip = np.asarray(clip, dtype=float)
    if _signed_area(clip) < 0:
        clip = clip[::-1]
    out = [tuple(p) for p in np.asarray(subject, dtype=float)]
    n = len(clip)
    for i in range(n):
        a, b = clip[i], clip[(i + 1) % n]
        ax, ay, bx, by = a[0], a[1], b[0], b[1]
        inp = out
        out = []
        if not inp:
            break
        for j in range(len(inp)):
            p = inp[j]
            q = inp[(j + 1) % len(inp)]
            side_p = (bx - ax) * (p[1] - ay) - (by - ay) * (p[0] - ax)
            side_q = (bx - ax) * (q[1] - ay) - (by - ay) * (q[0] - ax)
            if side_p >= 0:
                out.append(p)
            if (side_p >= 0) != (side_q >= 0):
                # giao của đoạn p→q với ĐƯỜNG THẲNG clip a→b
                d2x, d2y = q[0] - p[0], q[1] - p[1]
                den = (bx - ax) * d2y - (by - ay) * d2x
                if abs(den) > 1e-12:
                    s = ((p[0] - ax) * d2y - (p[1] - ay) * d2x) / den
                    out.append((ax + s * (bx - ax), ay + s * (by - ay)))
    return np.array(out) if out else np.zeros((0, 2))


def bev_iou(a: Sequence[float], b: Sequence[float]) -> float:
    """IoU BEV của 2 box (cx, cy, length, width, yaw)."""
    ca = box_corners_bev(a[0], a[1], a[2], a[3], a[4])
    cb = box_corners_bev(b[0], b[1], b[2], b[3], b[4])
    area_a, area_b = poly_area(ca), poly_area(cb)
    if area_a <= 1e-9 or area_b <= 1e-9:
        return 0.0
    inter = poly_area(clip_polygon(ca, cb))
    if inter <= 0:
        return 0.0
    union = area_a + area_b - inter
    return float(inter / union)


# ---------------------------------------------------------------------------
# Rank & thống kê
# ---------------------------------------------------------------------------

def rank_pct(x: Sequence[float]) -> np.ndarray:
    """Percentile rank trong (0, 1]: giá trị lớn → gần 1. Ổn định với scale khác nhau
    giữa các thành phần (phản biện: thay tổng tuyến tính thô bằng rank-aggregation)."""
    x = np.asarray(x, dtype=float)
    n = x.shape[0]
    if n == 0:
        return np.zeros(0)
    if n == 1:
        return np.ones(1)
    order = np.argsort(x, kind="stable")
    ranks = np.empty(n, dtype=float)
    ranks[order] = np.arange(1, n + 1)
    # phần tử bằng nhau nhận rank trung bình
    sx = x[order]
    i = 0
    while i < n:
        j = i
        while j + 1 < n and sx[j + 1] == sx[i]:
            j += 1
        if j > i:
            ranks[order[i:j + 1]] = (i + 1 + j + 1) / 2.0
        i = j + 1
    return ranks / n


def weighted_rank_agg(components: dict, weights: dict) -> np.ndarray:
    """Borda có trọng số trên percentile rank của từng thành phần."""
    total = np.zeros(len(next(iter(components.values()))))
    for name, vals in components.items():
        total += weights.get(name, 0.0) * rank_pct(vals)
    return total


class Mahalanobis:
    """Khoảng cách Mahalanobis với covariance co lại (shrinkage) — chống singular."""

    def __init__(self, shrink: float = 0.3):
        self.shrink = shrink
        self.mu = None
        self.inv = None

    def fit(self, X: np.ndarray) -> "Mahalanobis":
        X = np.asarray(X, dtype=float)
        self.mu = X.mean(axis=0)
        C = np.atleast_2d(np.cov(X.T))
        d = np.diag(C).copy()
        d[d <= 1e-9] = 1.0
        C = (1.0 - self.shrink) * C + self.shrink * np.diag(d)
        self.inv = np.linalg.pinv(C)
        return self

    def score(self, X: np.ndarray) -> np.ndarray:
        X = np.asarray(X, dtype=float)
        D = X - self.mu
        return np.sqrt(np.maximum(np.einsum("ij,jk,ik->i", D, self.inv, D), 0.0))


def wilson_ci(k: int, n: int, z: float = 1.96) -> tuple:
    """Khoảng tin Wilson cho tỉ lệ — dùng cho precision từng slice nhỏ."""
    if n == 0:
        return (0.0, 1.0)
    p = k / n
    d = 1.0 + z * z / n
    c = (p + z * z / (2 * n)) / d
    h = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / d
    return (max(0.0, c - h), min(1.0, c + h))


def average_precision(flags: Sequence[int]) -> float:
    """AP của một bảng xếp hạng nhị phân (1 = dương tính)."""
    npos = int(sum(flags))
    if npos == 0:
        return float("nan")
    hit, s = 0, 0.0
    for i, f in enumerate(flags, start=1):
        if f:
            hit += 1
            s += hit / i
    return s / npos


# ---------------------------------------------------------------------------
# IO
# ---------------------------------------------------------------------------

def save_json(obj, path: str) -> None:
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(obj, f, ensure_ascii=False, indent=2, default=float)


def save_csv(rows: List[dict], path: str) -> None:
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    if not rows:
        with open(path, "w", encoding="utf-8") as f:
            f.write("")
        return
    header = []
    for r in rows:
        for k in r:
            if k not in header:
                header.append(k)
    with open(path, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=header)
        w.writeheader()
        for r in rows:
            w.writerow(r)
