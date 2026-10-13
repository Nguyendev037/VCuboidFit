"""M2a · ứng viên vật thể cho engine `rare_v24` (planning/11 SPEC-P05 §3): Tầng 0 cụm DBSCAN, Tầng 1 PointPillars,
merge BEV-IoU, tracker liên frame trong từng scene. Phía CHỌN: KHÔNG đọc nhãn (SPEC-P05 §9)."""
import math
from collections import defaultdict
from pathlib import Path

import numpy as np
import pandas as pd
import yaml
from scipy.optimize import linear_sum_assignment

from c4.config import CONFIG_DIR
from c4.contracts import SPEC, read_table, validate
from c4.lidar.descriptor import ground_plane
from c4.lidar.extract import load_filter
from c4.lidar.pcd import load_pcd, preprocess
from c4.lidar.uncertainty import load_preds
from c4.rare.config import RareDefV24

MAX_DBSCAN_PTS = 100_000
_COLS = list(SPEC["rare_objects"][0])


class ClassMapError(ValueError):
    """class_map_pred_v24.yaml thiếu trường bắt buộc (CLI exit 3)."""


def load_class_map(path: Path | None = None) -> dict:
    p = Path(path) if path else CONFIG_DIR / "class_map_pred_v24.yaml"
    d = yaml.safe_load(p.read_text(encoding="utf-8")) or {}
    for k in ("pp_to_group", "cluster_heuristic"):
        if not isinstance(d.get(k), dict) or not d[k]:
            raise ClassMapError(f"{p.name}: thiếu trường '{k}'")
    for g, r in d["cluster_heuristic"].items():
        if not {"max_l", "max_w", "min_h", "max_h"} <= set(r):
            raise ClassMapError(f"{p.name}: cluster_heuristic.{g} thiếu max_l/max_w/min_h/max_h")
    return d


def _heuristic_class(l: float, w: float, h: float, heuristic: dict) -> str:
    big, small = max(l, w), min(l, w)
    for name, r in heuristic.items():
        if big <= r["max_l"] and small <= r["max_w"] and r["min_h"] <= h <= r["max_h"]:
            return name
    return "other"


def _to_global(cx, cy, pose: dict) -> tuple[float, float]:
    c, s = math.cos(pose["ego_yaw"]), math.sin(pose["ego_yaw"])
    return pose["ego_x"] + c * cx - s * cy, pose["ego_y"] + s * cx + c * cy


def _lidar2ego(calib: dict | None) -> tuple[np.ndarray, np.ndarray, float]:
    """Hiệu chuẩn LIDAR_TOP keyframe -> ego {R (3×3), t (3)} (`c4.rare.calib`). None => đồng nhất (giữ hệ cảm biến)."""
    if calib is None:
        return np.eye(3), np.zeros(3), 0.0
    R = np.asarray(calib["R"], np.float64).reshape(3, 3)
    return R, np.asarray(calib["t"], np.float64).reshape(3), math.atan2(R[1, 0], R[0, 0])


def cluster_candidates(pcd_path, cfg: dict, ego_pose: dict, heuristic: dict | None = None,
                       lidar_calib: dict | None = None) -> list[dict]:
    """DBSCAN trên điểm không-mặt-đất (hệ cảm biến LIDAR_TOP); tâm/yaw box đưa về HỆ EGO bằng `lidar_calib`
    (SPEC-P05 §3.1; H14: thiếu bước này box lệch -90° quanh z + ~1,84 m, crop camera sai 100%).

    `ego_pose` = {ego_x, ego_y, ego_yaw}. `pts` = số điểm thô (chưa voxel) trong box cụm, trên mặt đất.
    Không lọc theo kích thước ở đây (lọc VRU ở object_score). Frame > 100k điểm voxel: cắt ngẫu nhiên (seed 0)."""
    from sklearn.cluster import DBSCAN

    heuristic = heuristic if heuristic is not None else load_class_map()["cluster_heuristic"]
    R, t, dyaw = _lidar2ego(lidar_calib)
    raw = load_pcd(pcd_path)
    p, v = preprocess(raw, cfg)
    b = cfg["blocks"]
    plane = ground_plane(v, cfg)
    if plane is None:
        pts, p_ng = v, p
    else:
        thr = b["ransac"]["thr_m"]
        pts = v[v[:, :3] @ plane[:3] + plane[3] > thr]
        p_ng = p[p[:, :3] @ plane[:3] + plane[3] > thr]
    if len(pts) > MAX_DBSCAN_PTS:
        pts = pts[np.random.default_rng(0).choice(len(pts), MAX_DBSCAN_PTS, replace=False)]
    if len(pts) < b["dbscan"]["min_samples"]:
        return []
    lab = DBSCAN(eps=b["dbscan"]["eps_m"], min_samples=b["dbscan"]["min_samples"],
                 algorithm="kd_tree").fit_predict(pts[:, :3])
    out = []
    for k in range(int(lab.max()) + 1 if lab.size else 0):
        q = pts[lab == k, :3]
        lo, hi = q.min(0), q.max(0)
        l, w, h = (hi - lo).tolist()
        cx, cy, cz = (R @ ((lo + hi) / 2) + t).tolist()
        yaw = dyaw
        if len(q) >= 5:
            _, vec = np.linalg.eigh(np.cov(q[:, :2].T))
            yaw = float(math.atan2(vec[1, -1], vec[0, -1])) + dyaw
        inside = ((p_ng[:, 0] >= lo[0]) & (p_ng[:, 0] <= hi[0]) & (p_ng[:, 1] >= lo[1])
                  & (p_ng[:, 1] <= hi[1]) & (p_ng[:, 2] >= lo[2]) & (p_ng[:, 2] <= hi[2]))
        gx, gy = _to_global(cx, cy, ego_pose)
        out.append(dict(object_id=f"c{k:03d}", source="cluster", cls_pred=_heuristic_class(l, w, h, heuristic),
                        cx=cx, cy=cy, cz=cz, l=l, w=w, h=h, yaw=yaw, pts=max(int(inside.sum()), len(q)),
                        dist_m=math.hypot(cx, cy), gx=gx, gy=gy, track_id="", speed_mps=None,
                        missed_by_model=False))
    return out


def pp_candidates(preds: dict, class_map: dict) -> list[dict]:
    """Một phần tử preds_orig.pkl {sample_token, boxes (n,7), labels, scores} -> ứng viên (SPEC-P05 §3.2).
    boxes = (cx, cy, cz, l, w, h, yaw) hệ ego. `pts`=0 (điền khi merge với cụm).
    NHÁNH CHƯA CHẠY THẬT (không có checkpoint): chỉ kiểm bằng test tổng hợp."""
    names = class_map.get("pp_class_names")
    if not names:
        raise ClassMapError("class_map_pred_v24.yaml: thiếu 'pp_class_names' (cần cho nhánh PointPillars)")
    base = int(class_map.get("pp_label_base", 1))
    boxes, labels, scores = (np.asarray(preds[k]) for k in ("boxes", "labels", "scores"))
    out = []
    for i in range(len(scores)):
        li = int(labels[i]) - base
        name = names[li] if 0 <= li < len(names) else "unknown"
        cx, cy, cz, l, w, h, yaw = (float(x) for x in boxes[i, :7])
        out.append(dict(object_id=f"p{i:03d}", source="pointpillars",
                        cls_pred=class_map["pp_to_group"].get(name, "other"), cx=cx, cy=cy, cz=cz, l=l, w=w, h=h,
                        yaw=yaw, pts=0, dist_m=math.hypot(cx, cy), pp_score=float(scores[i]), track_id="",
                        speed_mps=None, missed_by_model=False))
    return out


def _bev_iou(a: dict, b: dict) -> float:
    ix = min(a["cx"] + a["l"] / 2, b["cx"] + b["l"] / 2) - max(a["cx"] - a["l"] / 2, b["cx"] - b["l"] / 2)
    iy = min(a["cy"] + a["w"] / 2, b["cy"] + b["w"] / 2) - max(a["cy"] - a["w"] / 2, b["cy"] - b["w"] / 2)
    if ix <= 0 or iy <= 0:
        return 0.0
    inter = ix * iy
    return inter / max(a["l"] * a["w"] + b["l"] * b["w"] - inter, 1e-9)


def merge_candidates(t0: list[dict], t1: list[dict], iou_thr: float = 0.3,
                     tier1_available: bool | None = None) -> list[dict]:
    """Khớp tham lam theo BEV-IoU giảm dần (SPEC-P05 §3.4). `tier1_available` mặc định = `bool(t1)`:
    cụm không khớp PP ⇒ `missed_by_model` chỉ khi Tầng 1 khả dụng. object_id đánh lại `o{i:03d}` theo dist_m tăng."""
    avail = bool(t1) if tier1_available is None else tier1_available
    pairs = sorted(((_bev_iou(c, p), i, j) for i, c in enumerate(t0) for j, p in enumerate(t1)),
                   key=lambda x: (-x[0], x[1], x[2]))
    used0, used1, merged = set(), set(), []
    for iou, i, j in pairs:
        if iou < iou_thr:
            break
        if i in used0 or j in used1:
            continue
        used0.add(i)
        used1.add(j)
        m = dict(t1[j])
        m.update(source="merged", pts=t0[i]["pts"], missed_by_model=False)
        merged.append(m)
    for i, c in enumerate(t0):
        if i not in used0:
            merged.append(dict(c, source="cluster", missed_by_model=avail))
    for j, p in enumerate(t1):
        if j not in used1:
            merged.append(dict(p, source="pointpillars", pts=0, missed_by_model=False))
    merged.sort(key=lambda o: o["dist_m"])
    for n, o in enumerate(merged):
        o["object_id"] = f"o{n:03d}"
    return merged


def track(objs_by_frame: dict[str, list[dict]], ego_poses: dict[str, tuple[float, float, float]],
          timestamps: dict[str, int], d_max: float = 1.5, v_max: float = 3.0,
          scene_of: dict[str, str] | None = None) -> None:
    """Gán `track_id` + `speed_mps` IN-PLACE (SPEC-P05 §3.5). Hungarian trên khoảng cách BEV hệ toàn cục giữa hai
    frame liền kề TRONG CÙNG scene (`scene_of`: token -> scene; None = một scene); ghép khi cost <= d_max + v_max*dt.
    Box đầu của track nhận speed của liên kết đầu; track 1 box -> None. Chỉ dùng ego_pose."""
    by_scene = defaultdict(list)
    for tok in objs_by_frame:
        by_scene[scene_of[tok] if scene_of else ""].append(tok)
    for scene, toks in by_scene.items():
        toks.sort(key=lambda t: timestamps[t])
        seq, prev = 0, None
        for tok in toks:
            objs = objs_by_frame[tok]
            ex, ey, eyaw = ego_poses[tok]
            pose = dict(ego_x=ex, ego_y=ey, ego_yaw=eyaw)
            g = np.array([_to_global(o["cx"], o["cy"], pose) for o in objs]).reshape(-1, 2)
            linked = {}
            if prev is not None and len(objs) and len(prev[0]):
                dt = (timestamps[tok] - prev[2]) / 1e6
                if dt > 0:
                    cost = np.hypot(g[:, None, 0] - prev[1][None, :, 0], g[:, None, 1] - prev[1][None, :, 1])
                    for a, b in zip(*linear_sum_assignment(cost)):
                        if cost[a, b] <= d_max + v_max * dt:
                            linked[int(a)] = (int(b), float(cost[a, b]) / dt)
            for a, o in enumerate(objs):
                if a in linked:
                    b, spd = linked[a]
                    po = prev[0][b]
                    o["track_id"], o["speed_mps"] = po["track_id"], spd
                    if po["speed_mps"] is None:
                        po["speed_mps"] = spd
                else:
                    o["track_id"], o["speed_mps"] = f"{str(scene)[:8]}_{seq}", None
                    seq += 1
            prev = (objs, g, timestamps[tok])


def _cluster_job(path, cfg, pose, heuristic, calib=None):
    return cluster_candidates(path, cfg, pose, heuristic, calib)


def build_candidates(job_dir, data_root, cfg: dict, rare_cfg: RareDefV24, class_map: dict,
                     scoring: dict | None = None, lidar_calib: dict[str, dict] | None = None) -> pd.DataFrame:
    """-> rare_objects (chưa chấm: score_* = 0, s_obj = 0) cho MỌI frame keep=True của index (SPEC-P05 §3.6).

    Tầng 1 chỉ dùng khi có `<job>/t1/preds_orig.pkl`; thiếu => cluster_only (không lỗi). Ego pose/timestamp lấy từ
    `lidar_index` (đủ cho tracker, không cần nạp bảng nuScenes nên không chạm annotation)."""
    from joblib import Parallel, delayed

    job, root = Path(job_dir), Path(data_root)
    sc = scoring or {}
    index = read_table(job / "lidar" / "index.parquet", "lidar_index")
    keep = load_filter(job / "lidar", index)
    pp_path = job / "t1" / "preds_orig.pkl"
    preds = load_preds(pp_path, index["sample_token"]) if pp_path.is_file() else None
    toks = index["sample_token"].tolist()
    poses = {t: dict(ego_x=float(r.ego_x), ego_y=float(r.ego_y), ego_yaw=float(r.ego_yaw))
             for t, r in zip(toks, index.itertuples())}
    todo = [i for i in range(len(index)) if keep[i]]
    heur = class_map["cluster_heuristic"]
    cal = lidar_calib or {}
    if len(todo) > 8:
        t0s = Parallel(n_jobs=-1, backend="loky")(
            delayed(_cluster_job)(root / index["lidar_path"].iloc[i], cfg, poses[toks[i]], heur, cal.get(toks[i]))
            for i in todo)
    else:
        t0s = [_cluster_job(root / index["lidar_path"].iloc[i], cfg, poses[toks[i]], heur, cal.get(toks[i]))
               for i in todo]
    objs_by_frame = {}
    for i, t0 in zip(todo, t0s):
        t1 = pp_candidates(preds[i], class_map) if preds is not None else []
        objs_by_frame[toks[i]] = merge_candidates(t0, t1, sc.get("iou_thr", 0.3), tier1_available=preds is not None)
    track(objs_by_frame, {t: (p["ego_x"], p["ego_y"], p["ego_yaw"]) for t, p in poses.items()},
          dict(zip(toks, index["timestamp"].astype(np.int64))), sc.get("d_max", 1.5), sc.get("v_max", 3.0),
          scene_of=dict(zip(toks, index["scene_token"])))
    rows = [dict(sample_token=tok, **{k: o.get(k) for k in _COLS if k != "sample_token"})
            for tok, objs in objs_by_frame.items() for o in objs]
    df = pd.DataFrame(rows, columns=_COLS)
    for c in ("score_shape", "score_slice", "score_vru", "score_unc", "s_obj"):
        df[c] = 0.0
    df["concept_top"] = ""
    df["reasons"] = ""
    df["track_id"] = df["track_id"].fillna("")
    for c in ("speed_mps", "r_sem", "concept_score"):
        df[c] = pd.to_numeric(df[c], errors="coerce")
    df["missed_by_model"] = df["missed_by_model"].fillna(False).astype(bool)
    return validate(df, "rare_objects")
