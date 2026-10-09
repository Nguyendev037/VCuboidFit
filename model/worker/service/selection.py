"""Chọn 5%: POST /jobs/{id}/select và đọc lại kết quả đã lưu."""
import json
import re
import threading
from datetime import datetime
from pathlib import Path

import pandas as pd
from fastapi import APIRouter, Request

from c4.config import load_config
from c4.contracts import ContractError
from c4.lidar.pipeline import run_selection_lidar
from c4.lidar.pipeline import schema as lidar_params_schema
from c4.pipeline import run_selection
from service.errors import ApiError
from service.models import (
    FrameSummary,
    SelectionInfo,
    SelectionList,
    SelectionResult,
    SelectParamsIn,
)
from service.settings import Settings

SID = re.compile(r"^[0-9a-f]{12}$")


def default_encoder_factory():
    from c4.extract.clip import OpenClipTextEncoder  # model giả khi C4_FAKE_MODELS=1
    return OpenClipTextEncoder()


class EncoderHolder:
    """Tạo text encoder đúng MỘT lần mỗi process, chỉ khi có query mới thật sự cần."""

    def __init__(self, factory=None):
        self._factory = factory or default_encoder_factory
        self._enc = None
        self._lock = threading.Lock()

    def get(self):
        with self._lock:
            if self._enc is None:
                self._enc = self._factory()
            return self._enc


class LazyEncoder:
    def __init__(self, holder: EncoderHolder):
        self._holder = holder

    def encode(self, texts):
        return self._holder.get().encode(texts)


class JobLocks:
    def __init__(self):
        self._guard = threading.Lock()
        self._locks: dict[str, threading.Lock] = {}

    def of(self, job_id: str) -> threading.Lock:
        with self._guard:
            return self._locks.setdefault(job_id, threading.Lock())


def scene_names(job_dir: Path) -> dict[str, str]:
    f = job_dir / "index" / "frames.parquet"
    if not f.is_file():
        return {}
    df = pd.read_parquet(f, columns=["sample_token", "scene_name"]).drop_duplicates("sample_token")
    return dict(zip(df["sample_token"], df["scene_name"]))


def thumb_url(job_id: str, token: str, cam: str) -> str:
    return f"/api/media/{job_id}/thumbs/{token}_{cam}.webp"


def bev_url(job_id: str, token: str) -> str:
    return f"/api/media/{job_id}/bev/{token}.png"


def frame_summary(job_id: str, job_dir: Path, row: dict, names: dict[str, str],
                  pipeline: str = "camera") -> FrameSummary:
    tok = row["sampleToken"]
    name = names.get(tok) or row.get("sceneName") or row.get("sceneToken", "")
    if pipeline == "lidar":
        # không có thumbnail LIDAR_TOP: CAM_FRONT nếu job có, ngược lại chính ảnh BEV
        bev = bev_url(job_id, tok)
        has_front = (job_dir / "media" / "thumbs" / f"{tok}_CAM_FRONT.webp").is_file()
        thumb = thumb_url(job_id, tok, "CAM_FRONT") if has_front else bev
    else:
        bev = ""
        thumb = thumb_url(job_id, tok, row["bestCam"])
    return FrameSummary(
        rank=row["rank"], sample_token=tok, scene_name=name,
        frame_idx=row["frameIdx"], best_cam=row["bestCam"], thumb_url=thumb, S=row["S"],
        r_nov=row["rNov"], r_unc=row["rUnc"], r_qry=row["rQry"], qry_best=row.get("qryBest", ""),
        reason=row.get("reason", ""), tags=row.get("tags", []),
        cams_available=row.get("camsAvailable", []), r_rar=row.get("rRar", 0.0), bev_url=bev)


def to_selection_result(job_id: str, job_dir: Path, result: dict) -> SelectionResult:
    names = scene_names(job_dir)
    pipeline = result.get("pipeline", "camera")
    return SelectionResult(
        selection_id=result["selectionId"], params=result["params"], pool_size=result["poolSize"],
        budget_b=result["budgetB"], warnings=result["warnings"], metrics=result["metrics"],
        preview=[frame_summary(job_id, job_dir, p, names, pipeline)
                 for p in result["preview"]],
        pipeline=pipeline, tier_available=result.get("tierAvailable", []))


def load_selection(settings: Settings, job_id: str, sid: str) -> dict:
    """result.json đã lưu; id lạ hoặc không đúng dạng ⇒ 404 (chặn đường dẫn lạ)."""
    f = settings.jobs / job_id / "out" / "selections" / sid / "result.json"
    if not SID.match(sid) or not f.is_file():
        raise ApiError(404, "not_found", "Không tìm thấy kết quả chọn.")
    return json.loads(f.read_text(encoding="utf-8"))


def list_selections(settings: Settings, job_id: str) -> list[SelectionInfo]:
    """Selection đã lưu của job, mới nhất trước (theo mtime result.json)."""
    root = settings.jobs / job_id / "out" / "selections"
    found = []
    for f in root.glob("*/result.json") if root.is_dir() else []:
        if not SID.match(f.parent.name):
            continue
        try:
            mtime = f.stat().st_mtime
            params = json.loads(f.read_text(encoding="utf-8")).get("params", {})
        except (OSError, ValueError):
            continue
        found.append((mtime, f.parent.name, params))
    found.sort(key=lambda t: (t[0], t[1]), reverse=True)
    return [SelectionInfo(selection_id=sid, params=params if isinstance(params, dict) else {},
                          created_at=datetime.fromtimestamp(m).isoformat(timespec="seconds"))
            for m, sid, params in found]


def t1_only_running(st) -> bool:
    """Plan 09 D4: t1 không chặn job. Khi chỉ còn stage `t1` đang chạy (t0 đã xong), vẫn chọn được
    theo Tầng 0; Tầng 1 tự bị từ chối vì job chưa có signals."""
    return (st.pipeline == "lidar" and st.state in ("queued", "running") and st.stage == "t1"
            and any(x.name == "t0" and x.state == "done" for x in st.stages))


router = APIRouter()


@router.post("/jobs/{job_id}/select", response_model=SelectionResult, response_model_by_alias=True)
def select(job_id: str, params: SelectParamsIn, request: Request):
    app = request.app
    st = app.state.queue.status(job_id)  # 404 nếu job không có
    if st.state != "done" and not t1_only_running(st):
        raise ApiError(409, "busy", "Job chưa xong, hãy đợi hoàn tất rồi chọn lại.")
    job_dir = app.state.settings.jobs / job_id
    try:
        with app.state.job_locks.of(job_id):
            if st.pipeline == "lidar":
                result = run_selection_lidar(job_dir, params.to_lidar_params())
            else:
                result = run_selection(job_dir, params.to_select_params(), cfg=load_config(),
                                       encoder=LazyEncoder(app.state.encoders))
    except ValueError as e:
        if st.pipeline == "lidar":
            # 01-CONTRACTS §5: thiếu t1/ khi tier=1 ⇒ tier_unavailable; tham số sai ⇒ bad_params
            code = "tier_unavailable" if str(e).startswith("tier_unavailable") else "bad_params"
            raise ApiError(422, code, str(e)) from e
        raise ApiError(400, "bad_request", str(e)) from e
    except FileNotFoundError as e:
        raise ApiError(500, "missing_input", f"Thiếu file đầu vào của job: {e}") from e
    except ContractError as e:
        raise ApiError(500, "contract", f"Dữ liệu job vi phạm contract: {e}") from e
    return to_selection_result(job_id, job_dir, result)


@router.get("/jobs/{job_id}/params-schema")
def params_schema(job_id: str, request: Request):
    """01-CONTRACTS §4: lược đồ cho panel ẩn của web; web KHÔNG hard-code miền giá trị."""
    st = request.app.state.queue.status(job_id)  # 404 nếu job không có
    if st.pipeline != "lidar":
        raise ApiError(404, "not_lidar", "Job này không phải pipeline LiDAR.")
    return lidar_params_schema(request.app.state.settings.jobs / job_id)


@router.get("/jobs/{job_id}/selections/{sid}", response_model=SelectionResult,
            response_model_by_alias=True)
def get_selection(job_id: str, sid: str, request: Request):
    request.app.state.queue.status(job_id)
    s: Settings = request.app.state.settings
    return to_selection_result(job_id, s.jobs / job_id, load_selection(s, job_id, sid))


@router.get("/jobs/{job_id}/selections", response_model=SelectionList,
            response_model_by_alias=True)
def get_selections(job_id: str, request: Request):
    request.app.state.queue.status(job_id)  # 404 nếu job không có
    return SelectionList(items=list_selections(request.app.state.settings, job_id))
