"""Danh sách frame theo ngân sách, chi tiết frame, phân tích và xuất CSV của một selection."""
import math
import threading
from pathlib import Path
from typing import Literal

import numpy as np
import pandas as pd
from fastapi import APIRouter, Query, Request
from fastapi.responses import Response

from c4.config import load_queries
from c4.contracts import CAMS, read_table
from c4.mining.query import apply_queries
from c4.mining.score import apply_quality
from service.errors import ApiError
from service.models import (
    Analysis,
    Box2D,
    Box3D,
    CamDetail,
    CamPose,
    CamScore,
    FrameDetail,
    FramesPage,
    FrameSummary,
    LidarRef,
)
from service.selection import LazyEncoder, bev_url, load_selection, scene_names, thumb_url

router = APIRouter()
_CACHE: dict[tuple[str, str], "SelectionData"] = {}
_CACHE_LOCK = threading.Lock()
_CACHE_MAX = 8
IMG_W, IMG_H = 1600, 900
LIDAR_BYTES_PER_POINT = 8  # f16 x, y, z, intensity
LIDAR_CAM = "LIDAR_TOP"


class SelectionData:
    """Mọi bảng cần để dựng FrameSummary của một selection (bất biến vì sid là dấu vân tay).

    `pipeline` lấy từ result.json: camera đọc `frame_scores.csv` + `features_cache.parquet`,
    lidar đọc `scores.parquet` + `selected.csv` (01-CONTRACTS §1).
    """

    def __init__(self, job_dir: Path, result: dict):
        self.job_dir = job_dir
        self.result = result
        self.pipeline = result.get("pipeline", "camera")
        d = job_dir / "out" / "selections" / result["selectionId"]
        self.tags = result["analysis"]["tags"]
        self.timestamps: dict[str, int] = {}
        if self.pipeline == "lidar":
            self.fs = read_table(d / "scores.parquet", "lidar_scores").set_index(
                "sample_token", drop=False)
            sel = read_table(d / "selected.csv", "lidar_selected")
            self.hybrid = sel[sel["method"] == "hybrid"].sort_values("rank").reset_index(drop=True)
            self.rank = dict(zip(self.hybrid["sample_token"], self.hybrid["rank"]))
            self.reason = dict(zip(self.hybrid["sample_token"], self.hybrid["reason"]))
            index = read_table(job_dir / "lidar" / "index.parquet", "lidar_index")
            self.names = dict(zip(index["sample_token"], index["scene_name"]))
            self.timestamps = dict(zip(index["sample_token"], index["timestamp"]))
            self.cams_of: dict[str, list[str]] = {}
        else:
            fs = read_table(d / "frame_scores.csv", "frame_scores")
            self.fs = fs.set_index("sample_token", drop=False)
            sel = read_table(d / "selected.csv", "selected")
            hybrid = sel[sel["method"] == "hybrid"].sort_values("rank")
            self.hybrid = hybrid.reset_index(drop=True)
            self.rank = dict(zip(hybrid["sample_token"], hybrid["rank"]))
            self.reason = dict(zip(hybrid["sample_token"], hybrid["reason"]))
            feat = read_table(job_dir / "cache" / "features_cache.parquet", "features_cache")
            present = feat.groupby("sample_token")["cam"].agg(set)
            self.cams_of = {t: [c for c in CAMS if c in s] for t, s in present.items()}
            self.names = scene_names(job_dir)
        self.n = len(self.fs)

    def budget_b(self, budget: float) -> int:
        return math.ceil(budget * self.n)

    def timestamp(self, token: str) -> int:
        if self.pipeline == "lidar":
            return int(self.timestamps.get(token, 0))
        frames = _filtered(self.job_dir / "index" / "frames.parquet", token)
        return int(frames["timestamp"].iloc[0]) if not frames.empty else 0

    def summary(self, job_id: str, token: str) -> FrameSummary:
        f = self.fs.loc[token]
        if self.pipeline == "lidar":
            bev = bev_url(job_id, token)
            has_front = (self.job_dir / "media" / "thumbs" / f"{token}_CAM_FRONT.webp").is_file()
            return FrameSummary(
                rank=int(self.rank.get(token, 0)), sample_token=token,
                scene_name=self.names.get(token, str(f["scene_token"])),
                frame_idx=int(f["frame_idx"]), best_cam=LIDAR_CAM,
                thumb_url=thumb_url(job_id, token, "CAM_FRONT") if has_front else bev,
                S=float(f["s"]), r_nov=float(f["r_nov"]), r_unc=float(f["r_unc"]), r_qry=0.0,
                qry_best="", reason=str(self.reason.get(token, "")), tags=self.tags.get(token, []),
                cams_available=[], r_rar=float(f["r_rar"]), bev_url=bev)
        return FrameSummary(
            rank=int(self.rank.get(token, 0)), sample_token=token,
            scene_name=self.names.get(token, str(f["scene_token"])), frame_idx=int(f["frame_idx"]),
            best_cam=f["best_cam"], thumb_url=thumb_url(job_id, token, f["best_cam"]),
            S=float(f["S_hybrid"]), r_nov=float(f["r_nov"]), r_unc=float(f["r_unc"]),
            r_qry=float(f["r_qry"]), qry_best=str(f["qry_best"]),
            reason=str(self.reason.get(token, "")), tags=self.tags.get(token, []),
            cams_available=self.cams_of.get(token, []))


def get_data(request: Request, job_id: str, sid: str) -> SelectionData:
    s = request.app.state.settings
    request.app.state.queue.status(job_id)  # 404 nếu job không có
    key = (str(s.workspace), f"{job_id}/{sid}")
    with _CACHE_LOCK:
        if key in _CACHE:
            return _CACHE[key]
    data = SelectionData(s.jobs / job_id, load_selection(s, job_id, sid))
    with _CACHE_LOCK:
        if len(_CACHE) >= _CACHE_MAX:
            _CACHE.pop(next(iter(_CACHE)))
        _CACHE[key] = data
    return data


def _budget(data: SelectionData, budget: float | None) -> float:
    return data.result["params"]["budget"] if budget is None else budget


def _check_budget(budget: float | None) -> None:
    if budget is not None and not 0.01 <= budget <= 0.10:
        raise ApiError(400, "bad_request", "Ngân sách phải nằm trong khoảng 1%–10%.")


@router.get("/jobs/{job_id}/selections/{sid}/frames", response_model=FramesPage,
            response_model_by_alias=True)
def list_frames(job_id: str, sid: str, request: Request, budget: float | None = None,
                sort: Literal["rank", "score"] = "rank", tag: str | None = None,
                page: int = Query(1, ge=1), pageSize: int = Query(60, ge=1, le=200)):  # noqa: N803
    _check_budget(budget)
    data = get_data(request, job_id, sid)
    b = data.budget_b(_budget(data, budget))
    rows = data.hybrid[data.hybrid["rank"] <= b]
    if sort == "score":
        col = "s" if data.pipeline == "lidar" else "S"  # lidar: cột điểm là `s` (01-CONTRACTS §1)
        rows = rows.sort_values([col, "rank"], ascending=[False, True])
    tokens = list(rows["sample_token"])
    if tag:
        tokens = [t for t in tokens
                  if any(x == tag or x.startswith(tag) for x in data.tags.get(t, []))]
    start = (page - 1) * pageSize
    items = [data.summary(job_id, t) for t in tokens[start:start + pageSize]]
    return FramesPage(items=items, total=len(tokens), budget_b=b)


# ---------- điểm theo ảnh (chi tiết frame) ----------

def image_scores(settings, job_id: str, data: SelectionData, encoders) -> pd.DataFrame:
    """r_nov/r_unc/r_qry/s và q_ok cho TỪNG ảnh, cùng công thức `c4.mining.score.frame_scores`
    (test đối chiếu camera tốt nhất của frame với frame_scores)."""
    p = data.result["params"]
    job_dir = settings.jobs / job_id
    feat = read_table(job_dir / "cache" / "features_cache.parquet", "features_cache")
    queries = p["queries"]
    if [q["text"] for q in queries] != [q["text"] for q in load_queries()]:
        c_img = np.load(job_dir / "cache" / "clip_img.npy", mmap_mode="r")
        feat = apply_queries(feat, c_img, queries, LazyEncoder(encoders))
    feat = apply_quality(feat, p["min_luma"], p["min_blur_var"])
    eligible = feat["q_ok"] & feat["cam"].isin(p["cameras"])
    for src, dst in [("nov_knn", "r_nov"), ("unc", "r_unc"), ("qry_max", "r_qry")]:
        feat[dst] = feat[src].where(eligible).groupby(feat["split"]).rank(pct=True).fillna(0.0)
    feat["s"] = np.where(eligible, p["alpha"] * feat["r_nov"] + p["beta"] * feat["r_unc"]
                         + p["gamma"] * feat["r_qry"], 0.0)
    return feat.set_index(["sample_token", "cam"])


def _filtered(path: Path, token: str) -> pd.DataFrame:
    if not path.is_file():
        return pd.DataFrame()
    return pd.read_parquet(path, filters=[("sample_token", "==", token)])


def _boxes2d(boxes2d: pd.DataFrame, cam: str) -> list[Box2D]:
    if boxes2d.empty:
        return []
    return [Box2D(category=b.category, corners=[float(x) for x in b.corners],
                  visibility=str(b.visibility))
            for b in boxes2d[boxes2d["cam"] == cam].itertuples()]


def _cams_lidar(job_id: str, token: str, frames: pd.DataFrame, boxes2d: pd.DataFrame,
                data: SelectionData) -> list[CamDetail]:
    """Job lidar KHÔNG chấm điểm ảnh camera: `cams` chỉ để XEM (điểm lấy từ frame LiDAR)."""
    if frames.empty:  # runner lidar không sinh index/frames.parquet
        return []
    f = data.fs.loc[token]
    cams = []
    for cam in CAMS:
        row = frames[frames["cam"] == cam]
        if row.empty:
            continue
        cams.append(CamDetail(
            cam=cam, image_url=f"/api/media/{job_id}/images/{row['img_path'].iloc[0]}",
            width=IMG_W, height=IMG_H, boxes=_boxes2d(boxes2d, cam),
            score=CamScore(nov=float(f["r_nov"]), unc=float(f["r_unc"]), qry=0.0,
                           s=float(f["s"])),
            q_ok=True))
    return cams


@router.get("/jobs/{job_id}/frames/{token}", response_model=FrameDetail,
            response_model_by_alias=True)
def frame_detail(job_id: str, token: str, request: Request, sid: str):
    data = get_data(request, job_id, sid)
    if token not in data.fs.index:
        raise ApiError(404, "not_found", "Không tìm thấy frame.")
    s = request.app.state.settings
    job_dir = s.jobs / job_id
    summary = data.summary(job_id, token)
    frames = _filtered(job_dir / "index" / "frames.parquet", token)
    if frames.empty and data.pipeline == "camera":
        raise ApiError(404, "not_found", "Job chưa có chỉ mục ảnh (index/frames.parquet).")
    boxes2d = _filtered(job_dir / "gt" / "gt_boxes_2d.parquet", token)
    poses = _filtered(job_dir / "index" / "cam_poses.parquet", token)
    if data.pipeline == "camera":
        scores = image_scores(s, job_id, data, request.app.state.encoders)
        cams = []
        for cam in CAMS:
            row = frames[frames["cam"] == cam]
            if row.empty:
                continue
            sc = scores.loc[(token, cam)]
            cams.append(CamDetail(
                cam=cam, image_url=f"/api/media/{job_id}/images/{row['img_path'].iloc[0]}",
                width=IMG_W, height=IMG_H, boxes=_boxes2d(boxes2d, cam),
                score=CamScore(nov=float(sc["r_nov"]), unc=float(sc["r_unc"]),
                               qry=float(sc["r_qry"]), s=float(sc["s"])),
                q_ok=bool(sc["q_ok"])))
    else:
        cams = _cams_lidar(job_id, token, frames, boxes2d, data)
    lidar_file = job_dir / "media" / "lidar" / f"{token}.bin"
    # .f16 (không phải .bin): IDM và trình quản lý tải bắt URL .bin như file tải về
    lidar = LidarRef(url=f"/api/media/{job_id}/lidar/{token}.f16",
                     num_points=lidar_file.stat().st_size // LIDAR_BYTES_PER_POINT) \
        if lidar_file.is_file() else None
    b3 = _filtered(job_dir / "gt" / "boxes_3d.parquet", token)
    cam_poses = [CamPose(cam=p.cam, translation=[float(x) for x in p.translation],
                         rotation=[float(x) for x in p.rotation],
                         intrinsic=[float(x) for x in p.intrinsic])
                 for p in poses.itertuples() if p.cam in {c.cam for c in cams}]
    cam_poses.sort(key=lambda p: CAMS.index(p.cam))
    return FrameDetail(
        **summary.model_dump(), timestamp=data.timestamp(token), cams=cams, lidar=lidar,
        boxes3d=[Box3D(category=b.category, corners=[float(x) for x in b.corners])
                 for b in b3.itertuples()],
        cam_poses=cam_poses)


@router.get("/jobs/{job_id}/selections/{sid}/analysis", response_model=Analysis,
            response_model_by_alias=True)
def analysis(job_id: str, sid: str, request: Request):
    a = get_data(request, job_id, sid).result["analysis"]
    return Analysis(pool=a["pool"], selected=a["selected"], histogram=a["histogram"])


@router.get("/jobs/{job_id}/selections/{sid}/export.csv")
def export_csv(job_id: str, sid: str, request: Request, budget: float | None = None):
    _check_budget(budget)
    data = get_data(request, job_id, sid)
    use = _budget(data, budget)
    rows = data.hybrid[data.hybrid["rank"] <= data.budget_b(use)]
    body = rows.to_csv(index=False, float_format="%.6f")
    name = f"selected_{sid}_{use * 100:g}pct.csv"
    return Response(body, media_type="text/csv; charset=utf-8",
                    headers={"Content-Disposition": f'attachment; filename="{name}"'})
