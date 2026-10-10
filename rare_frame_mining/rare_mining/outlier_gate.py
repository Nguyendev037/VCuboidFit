"""Cổng lọc NGOẠI LAI — chạy TRƯỚC khi chọn frame (Phương án chốt 10/10, bước 2).

Nguyên tắc: **hiếm = ít gặp nhưng có thật và nhất quán; ngoại lai = lỗi dữ liệu hoặc không
giải thích được.** Cả hai đều "lạ", nên không tách được bằng một điểm OOD duy nhất. Cổng dùng
4 phép thử, KHÔNG dùng nhãn:

  1. validity  — dữ liệu hợp lệ (luật): đủ điểm, không NaN/inf, cường độ không âm, không quá
                 nhiều điểm dưới mặt đường, timestamp tăng đều, có ego pose.
  2. temporal  — nhất quán theo thời gian: vật giống VRU phải xuất hiện lại ở keyframe liền kề
                 (điểm "ma" chỉ xuất hiện 1 lần).
  3. geometry  — hợp lý hình học/ngữ nghĩa: vật giống VRU không lơ lửng; box model gán lớp VRU
                 phải có kích thước khả dĩ.
  4. knn       — còn "hàng xóm" trong data tham chiếu (V, khác scene): hiếm = xa nhưng vẫn có
                 hàng xóm; ngoại lai = cô lập, vượt phân vị cực trị của chính V.

Phân nhóm:
  - outlier  (Ngoại lai, loại): trượt phép 1, hoặc trượt ≥ 2 phép.
  - suspect  (Nghi ngờ, người duyệt): trượt đúng 1 phép trong 2–4, hoặc knn sát ngưỡng.
  - valid    (Hợp lệ → được chấm điểm hiếm và chọn).

Giới hạn đã biết (ghi trong tài liệu): phép temporal chỉ bù tịnh tiến ego (dataset không cho
yaw ego ở đây) nên có thể báo nhầm khi xe rẽ gấp; vì vậy trượt riêng phép này chỉ là "Nghi ngờ".
"""
import math
from typing import Dict, List, Optional

import numpy as np

GATE_TIER = {"valid": 0, "suspect": 1, "outlier": 2}


# ---------------------------------------------------------------------------
# Thống kê thô cho phép thử 1 — tính trong M1 từ point cloud CHƯA cắt ROI
# ---------------------------------------------------------------------------
def raw_point_stats(points: np.ndarray) -> dict:
    n = int(points.shape[0])
    if n == 0:
        return {"n_raw": 0, "nonfinite_frac": 0.0, "int_min": 0.0, "frac_below_ground": 0.0}
    finite = np.isfinite(points).all(axis=1)
    p = points[finite]
    st = {"n_raw": n, "nonfinite_frac": float(1.0 - finite.mean()),
          "int_min": float(p[:, 3].min()) if (p.shape[1] >= 4 and p.shape[0]) else 0.0,
          "frac_below_ground": 0.0}
    if p.shape[0] >= 50:
        z = p[:, 2]
        r = np.hypot(p[:, 0], p[:, 1])
        near = z[(r > 2.0) & (r < 20.0)]
        if near.size >= 50:
            ground = float(np.percentile(near, 40))       # mặt đường gần xe (bền khi ≤ 40% điểm bị lệch)
            st["frac_below_ground"] = float((z < ground - 1.0).mean())
    return st


def _vru_like(c: dict) -> bool:
    return c.get("s_vru_raw", 0.0) >= 0.5 and c.get("n_points", 0) >= 5


# ---------------------------------------------------------------------------
# 4 phép thử
# ---------------------------------------------------------------------------
def _test_validity(f: dict, gcfg, median_n: float, median_dt: float, prev_t: Optional[float]) -> List[str]:
    a = f["aux"]
    why = []
    n = a.get("n_raw", a.get("n_total", 0))
    if n < max(gcfg.min_points_abs, gcfg.min_points_rel * median_n):
        why.append(f"ít điểm ({n})")
    if a.get("nonfinite_frac", 0.0) > 0:
        why.append("có NaN/inf")
    if a.get("int_min", 0.0) < 0:
        why.append("cường độ âm")
    if a.get("frac_below_ground", 0.0) > gcfg.max_below_ground:
        why.append(f"{100 * a['frac_below_ground']:.0f}% điểm dưới mặt đường")
    ego = f.get("ego")
    if ego is None or not all(np.isfinite(ego)):
        why.append("thiếu ego pose")
    if prev_t is not None and median_dt > 0:
        dt = f["t"] - prev_t
        if dt <= 0 or dt > gcfg.max_dt_factor * median_dt:
            why.append(f"timestamp lệch (Δt={dt:.2f}s)")
    return why


def _to_global(pose, xy) -> np.ndarray:
    yaw, tx, ty = pose
    c, s = math.cos(yaw), math.sin(yaw)
    x, y = xy[..., 0], xy[..., 1]
    return np.stack([c * x - s * y + tx, s * x + c * y + ty], -1)


_PACK = 1 << 21


def occupancy_cells(xy: np.ndarray, pose, cell: float) -> np.ndarray:
    """Ô lưới BEV (hệ toàn cục) có điểm foreground → mảng khoá int64 đã sort (≈ vài nghìn/frame)."""
    g = np.floor(_to_global(pose, np.asarray(xy, float)) / cell).astype(np.int64)
    return np.unique((g[:, 0] + _PACK // 2) * _PACK + (g[:, 1] + _PACK // 2))


def _cells_hit(keys: np.ndarray, gxy: np.ndarray, radius: float, cell: float) -> np.ndarray:
    """Với mỗi điểm toàn cục trong gxy: trong bán kính `radius` có ô nào thuộc `keys` không."""
    k = int(math.ceil(radius / cell))
    off = np.array([(i, j) for i in range(-k, k + 1) for j in range(-k, k + 1)
                    if (i * i + j * j) * cell * cell <= radius * radius], np.int64)
    base = np.floor(gxy / cell).astype(np.int64)
    q = base[:, None, :] + off[None, :, :]
    qk = (q[..., 0] + _PACK // 2) * _PACK + (q[..., 1] + _PACK // 2)
    pos = np.clip(np.searchsorted(keys, qk), 0, len(keys) - 1)
    return (keys[pos] == qk).any(1)


def _supported_mask(f: dict, own: List[dict], nf: dict, nb_cands: List[dict], gcfg) -> np.ndarray:
    """Vật nào trong `own` còn "có mặt" ở keyframe `nf`.
    Có sensor_pose + lưới điểm foreground của `nf` → đối chiếu theo ĐIỂM trong hệ toàn cục, bán kính
    r0 + v_max·|Δt| (cụm điểm thật vẫn còn điểm ở đó dù clustering tách/gộp khác đi; điểm "ma"
    thì không). Thiếu → đối chiếu theo ứng viên, bán kính r0 + độ dịch ego."""
    if not own:
        return np.zeros(0, bool)
    a = np.array([[float(c["center"][0]), float(c["center"][1])] for c in own])
    cells = nf.get("aux", {}).get("fg_cells")
    if f.get("pose") is not None and nf.get("pose") is not None and cells is not None and len(cells):
        lim = gcfg.temporal_radius_m + gcfg.temporal_max_speed * abs(f["t"] - nf["t"])
        return _cells_hit(cells, _to_global(f["pose"], a), lim, gcfg.cell_m)
    if not nb_cands:
        return np.zeros(len(own), bool)
    b = np.array([[float(o["center"][0]), float(o["center"][1])] for o in nb_cands])
    lim = gcfg.temporal_radius_m + math.hypot(f["ego"][0] - nf["ego"][0], f["ego"][1] - nf["ego"][1])
    d2 = ((a[:, None, :] - b[None, :, :]) ** 2).sum(-1)
    return d2.min(1) <= lim * lim


def _temporal_counts(f: dict, own: List[dict], neighbors: List[tuple], gcfg):
    """→ (số vật giống VRU, số vật không có mặt lại) hoặc None nếu không áp dụng được."""
    if not neighbors:
        return None
    vru = [c for c in own if _vru_like(c)]
    if len(vru) < gcfg.temporal_min_objs:
        return None
    ok = np.zeros(len(vru), bool)
    for nf, nc in neighbors:
        ok |= _supported_mask(f, vru, nf, nc, gcfg)
    return len(vru), int(len(vru) - ok.sum())


def _test_temporal(f: dict, own: List[dict], neighbors: List[tuple], gcfg,
                   thr: float = float("inf")) -> Optional[str]:
    """neighbors: list (frame_dict, cands) của keyframe liền trước/sau cùng scene.
    Trượt khi ≥ temporal_min_unsupported vật không có mặt lại VÀ (tỉ lệ có mặt lại thấp HOẶC
    số vật không có mặt lại vượt phân vị `thr` của V)."""
    cnt = _temporal_counts(f, own, neighbors, gcfg)
    if cnt is None:
        return None
    n, n_unsup = cnt
    frac = (n - n_unsup) / n
    f["gate_temporal_support"] = round(frac, 3)
    if n_unsup >= gcfg.temporal_min_unsupported and (frac < gcfg.temporal_min_support or n_unsup > thr):
        return (f"{n_unsup} vật giống VRU không xuất hiện lại ở frame liền kề "
                f"(chỉ {100 * frac:.0f}% có mặt lại; ngưỡng V {thr:g})")
    return None


def _geometry_bad(own: List[dict], gcfg) -> int:
    bad = 0
    for c in own:
        if _vru_like(c):
            bottom = c.get("bottom_ag", c.get("height", 0.0) - c.get("H", 0.0) / 2.0)
            if bottom > gcfg.max_float_m:
                bad += 1
                continue
        if c.get("class_name") in ("pedestrian", "bicycle", "motorcycle"):
            if not (gcfg.vru_h_range[0] <= c.get("H", 1.0) <= gcfg.vru_h_range[1]) \
                    or c.get("L", 0.0) > gcfg.vru_max_len:
                bad += 1
    return bad


def _test_geometry(own: List[dict], gcfg, thr: float = 0.0) -> Optional[str]:
    """Trượt khi số vật sai hình học ≥ geometry_min_bad VÀ vượt ngưỡng `thr` (phân vị V)."""
    bad = _geometry_bad(own, gcfg)
    if bad >= gcfg.geometry_min_bad and bad > thr:
        return (f"{bad} vật giống VRU sai hình học (lơ lửng / kích thước không khả dĩ), "
                f"ngưỡng V {thr:g}")
    return None


class KnnSupport:
    """k-NN trên vector thống kê frame (ood_vec) đã chuẩn hoá theo V; loại hàng xóm cùng scene."""

    def __init__(self, k: int = 5):
        self.k = k
        self.X = None

    def fit(self, V: List[dict], q_out: float, q_near: float) -> "KnnSupport":
        X = np.stack([f["ood_vec"] for f in V]).astype(float)
        self.mu, self.sd = X.mean(0), X.std(0) + 1e-6
        self.X = (X - self.mu) / self.sd
        self.scenes = np.array([f["scene"] for f in V])
        d = np.array([self.dist(f) for f in V])
        d = d[np.isfinite(d)]
        if d.size:
            self.thr_out = float(np.quantile(d, q_out))
            self.thr_near = float(np.quantile(d, q_near))
        else:
            self.thr_out = self.thr_near = float("inf")
        return self

    def dist(self, f: dict) -> float:
        x = (np.asarray(f["ood_vec"], float) - self.mu) / self.sd
        mask = self.scenes != f["scene"]
        if mask.sum() == 0:
            return float("nan")
        d = np.sort(np.linalg.norm(self.X[mask] - x, axis=1))
        return float(d[: self.k].mean())


# ---------------------------------------------------------------------------
# API chính
# ---------------------------------------------------------------------------
class GateState:
    """Tham chiếu dùng chung (fit KHÔNG nhãn trên pool + V): trung vị số điểm, Δt, k-NN."""

    def __init__(self, gcfg):
        self.gcfg = gcfg
        self.median_n = 0.0
        self.median_dt = 0.0
        self.geom_thr = 0.0
        self.temporal_thr = float("inf")
        self.knn: Optional[KnnSupport] = None


def classify_one(f: dict, own: List[dict], neighbors: List[tuple], st: GateState,
                 fail1: List[str]) -> tuple:
    """Áp phép 2–4 (phép 1 đã tính sẵn ở `fail1`) → (gate, lý do)."""
    gcfg = st.gcfg
    fails = []
    t2 = _test_temporal(f, own, neighbors, gcfg, st.temporal_thr)
    if t2:
        fails.append("temporal: " + t2)
    t3 = _test_geometry(own, gcfg, st.geom_thr)
    if t3:
        fails.append("geometry: " + t3)
    near = False
    if st.knn is not None:
        d = st.knn.dist(f)
        f["gate_knn_dist"] = round(d, 3) if np.isfinite(d) else None
        if np.isfinite(d) and d > st.knn.thr_out:
            fails.append(f"knn: cô lập (d={d:.2f} > p{100 * gcfg.knn_q_out:g} của V)")
        elif np.isfinite(d) and d > st.knn.thr_near:
            near = True
    if fail1:
        return "outlier", " | ".join(["validity: " + ", ".join(fail1)] + fails)
    if len(fails) >= 2:
        return "outlier", " | ".join(fails)
    if len(fails) == 1:
        return "suspect", fails[0]
    if near:
        return "suspect", "knn: sát ngưỡng cô lập"
    return "valid", ""


def _set_gate(f: dict, gate: str, why: str, gcfg) -> None:
    f["gate"], f["gate_fail"] = gate, why
    tier = GATE_TIER[gate]
    if gate == "suspect" and gcfg.suspect_policy == "include":
        tier = 0
    f["gate_tier"] = tier


def apply_gate(frame_dicts: List[dict], cands_by_fid: Dict[str, List[dict]], gcfg):
    """Gắn f['gate'] ∈ {valid, suspect, outlier}, f['gate_fail'] (lý do), f['gate_tier'].
    Trả về (summary, state). Tham chiếu k-NN fit trên frame V đã qua phép 1 (không dùng nhãn)."""
    st = GateState(gcfg)
    if not gcfg.enabled:
        for f in frame_dicts:
            _set_gate(f, "valid", "", gcfg)
        return {"enabled": False}, st

    ns = [f["aux"].get("n_raw", f["aux"].get("n_total", 0)) for f in frame_dicts]
    st.median_n = float(np.median(ns)) if ns else 0.0
    by_scene: Dict[str, List[dict]] = {}
    for f in frame_dicts:
        by_scene.setdefault(f["scene"], []).append(f)
    dts = []
    for fs in by_scene.values():
        fs.sort(key=lambda x: x["t"])
        dts += [b["t"] - a["t"] for a, b in zip(fs, fs[1:]) if b["t"] > a["t"]]
    st.median_dt = float(np.median(dts)) if dts else 0.0

    fail1 = {}
    for fs in by_scene.values():
        prev = None
        for f in fs:
            fail1[f["fid"]] = _test_validity(f, gcfg, st.median_n, st.median_dt, prev)
            prev = f["t"]

    V_clean = [f for f in frame_dicts if f["split"] == "V" and not fail1[f["fid"]]]
    if len({f["scene"] for f in V_clean}) >= 2:
        st.knn = KnnSupport(gcfg.knn_k).fit(V_clean, gcfg.knn_q_out, gcfg.knn_q_near)
    if V_clean:
        st.geom_thr = float(np.quantile(
            [_geometry_bad(cands_by_fid.get(f["fid"], []), gcfg) for f in V_clean], gcfg.geometry_q))

    def nbs_of(fs, i):
        return [(fs[j], cands_by_fid.get(fs[j]["fid"], []))
                for j in (i - 1, i + 1) if 0 <= j < len(fs) and not fail1[fs[j]["fid"]]]

    un_V = []
    for fs in by_scene.values():
        for i, f in enumerate(fs):
            if f["split"] == "V" and not fail1[f["fid"]]:
                cnt = _temporal_counts(f, cands_by_fid.get(f["fid"], []), nbs_of(fs, i), gcfg)
                if cnt is not None:
                    un_V.append(cnt[1])
    if un_V:
        st.temporal_thr = float(np.quantile(un_V, gcfg.temporal_q))

    for fs in by_scene.values():
        for i, f in enumerate(fs):
            nbs = nbs_of(fs, i)
            f["gate_neighbors"] = [fs[j]["fid"] for j in (i - 1, i + 1) if 0 <= j < len(fs)]
            gate, why = classify_one(f, cands_by_fid.get(f["fid"], []), nbs, st, fail1[f["fid"]])
            _set_gate(f, gate, why, gcfg)

    counts = {}
    for sp in ("V", "T", "PILOT"):
        fs = [f for f in frame_dicts if f["split"] == sp]
        counts[sp] = {g: sum(1 for f in fs if f["gate"] == g) for g in GATE_TIER}
    T = [f for f in frame_dicts if f["split"] == "T"]
    share_knn_T = float(np.mean([("knn: cô lập" in f["gate_fail"]) for f in T])) if T else 0.0
    return {
        "enabled": True, "counts": counts,
        "knn_thr_out": None if st.knn is None else st.knn.thr_out,
        "knn_thr_near": None if st.knn is None else st.knn.thr_near,
        "median_points": st.median_n, "median_dt": st.median_dt, "geometry_thr": st.geom_thr,
        "temporal_thr": st.temporal_thr,
        # Rất nhiều frame T cùng "cô lập" so với V → lệch domain (cảm biến/địa bàn khác),
        # KHÔNG phải hiếm: cần tham chiếu mới, đừng gán nhãn cả loạt là ngoại lai.
        "domain_shift_warning": bool(share_knn_T > gcfg.domain_shift_frac),
        "share_isolated_T": round(share_knn_T, 3),
    }, st


def validity_for(f: dict, st: GateState, prev_t: Optional[float]) -> List[str]:
    return _test_validity(f, st.gcfg, st.median_n, st.median_dt, prev_t)


# ---------------------------------------------------------------------------
# Kiểm chứng: cố ý tạo lỗi trên V, đo bao nhiêu frame lỗi lọt vào nhóm "valid"
# ---------------------------------------------------------------------------
def corrupt_points(points: np.ndarray, kind: str, rng: np.random.Generator) -> np.ndarray:
    p = points.copy()
    if kind == "sparse":            # mất phần lớn điểm (lỗi truyền/đầu đọc)
        keep = rng.random(len(p)) < 0.08
        return p[keep]
    if kind == "nan":               # lỗi ghi file
        idx = rng.choice(len(p), size=max(1, len(p) // 100), replace=False)
        p[idx, :3] = np.nan
        return p
    if kind == "below":             # calib sai: một mảng điểm rơi dưới mặt đường
        idx = rng.choice(len(p), size=len(p) // 5, replace=False)
        p[idx, 2] -= 3.0
        return p
    if kind == "ghost":             # điểm "ma": vài cụm giống người chỉ có trong 1 frame
        ground = float(np.percentile(p[:, 2], 10))
        blobs = []
        for _ in range(4):
            r, a = rng.uniform(6, 20), rng.uniform(-math.pi, math.pi)
            cx, cy = r * math.cos(a), r * math.sin(a)
            m = 60
            b = np.stack([cx + rng.normal(0, 0.15, m), cy + rng.normal(0, 0.15, m),
                          ground + rng.uniform(0.1, 1.7, m)], 1)
            if p.shape[1] >= 4:
                b = np.concatenate([b, np.full((m, p.shape[1] - 3), float(np.median(p[:, 3])))], 1)
            blobs.append(b)
        return np.concatenate([p] + blobs).astype(p.dtype)
    raise ValueError(kind)


CORRUPTIONS = ("sparse", "nan", "below", "ghost")
