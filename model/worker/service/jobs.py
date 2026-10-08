"""Hàng đợi job: một thread nền chạy run_job lần lượt (một GPU), phục hồi sau restart, huỷ."""
import json
import os
import threading
import time
import uuid
from collections import deque
from datetime import datetime
from pathlib import Path
from typing import Literal

from fastapi import APIRouter, Request
from pydantic import BaseModel

from service.errors import ApiError
from service.models import DatasetReport, JobList, JobStatus, JobSummary
from service.settings import Settings

ACTIVE = ("queued", "running")


def _now() -> str:
    return datetime.now().isoformat(timespec="seconds")


def _write_json(path: Path, obj) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(f"{path.name}.{uuid.uuid4().hex[:6]}.tmp")
    tmp.write_text(json.dumps(obj, ensure_ascii=False), encoding="utf-8")
    for attempt in range(20):
        try:
            os.replace(tmp, path)
            return
        except PermissionError:  # Windows: người đọc đang mở file đích
            if attempt == 19:
                raise
            time.sleep(0.05)


def _read_json(path: Path):
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None


def _default_runner(*args, **kwargs):
    from c4.jobs.runner import run_job  # nhập muộn: service nhẹ khi không chạy job thật
    return run_job(*args, **kwargs)


class JobQueue:
    def __init__(self, settings: Settings, runner=None):
        self.settings = settings
        self._runner = runner or _default_runner
        self._queue: deque[str] = deque()
        self._cv = threading.Condition()
        self._cancels: dict[str, threading.Event] = {}
        self._stop = False
        self._thread: threading.Thread | None = None

    # ---- file ----
    def _dir(self, job_id: str) -> Path:
        return self.settings.jobs / job_id

    def _meta(self, job_id: str) -> dict | None:
        return _read_json(self._dir(job_id) / "job.json")

    def _set_meta(self, job_id: str, **kw) -> None:
        meta = self._meta(job_id) or {}
        meta.update(kw)
        _write_json(self._dir(job_id) / "job.json", meta)

    # ---- API ----
    def submit(self, dataset_id: str, pipeline: str = "camera") -> str:
        job_id = uuid.uuid4().hex[:12]
        _write_json(self._dir(job_id) / "job.json", dict(
            jobId=job_id, datasetId=dataset_id, pipeline=pipeline, createdAt=_now(),
            state="queued"))
        with self._cv:
            self._queue.append(job_id)
            self._cv.notify()
        return job_id

    def status(self, job_id: str) -> JobStatus:
        meta = self._meta(job_id)
        if meta is None:
            raise ApiError(404, "not_found", "Không tìm thấy job.")
        st = _read_json(self._dir(job_id) / "status.json")
        if st is not None:
            job = JobStatus.model_validate(st)
        else:
            job = JobStatus(job_id=job_id, state=meta["state"])
        if job.pipeline is None:  # runner cũ không ghi pipeline ⇒ lấy từ job.json
            job = job.model_copy(update={"pipeline": meta.get("pipeline") or "camera"})
        return job

    def cancel(self, job_id: str) -> JobStatus:
        if self._meta(job_id) is None:
            raise ApiError(404, "not_found", "Không tìm thấy job.")
        with self._cv:
            if job_id in self._queue:
                self._queue.remove(job_id)
                self._finish(job_id, dict(jobId=job_id, state="cancelled", stage="index",
                                          done=0, total=1))
            elif job_id in self._cancels:
                self._cancels[job_id].set()
        return self.status(job_id)

    def recover(self) -> None:
        """Job `queued`/`running` còn sót sau restart được xếp lại theo createdAt."""
        found = []
        for meta_file in self.settings.jobs.glob("*/job.json"):
            meta = _read_json(meta_file)
            if meta and meta.get("state") in ACTIVE and meta["jobId"] not in self._queue:
                found.append(meta)
        with self._cv:
            for meta in sorted(found, key=lambda m: m["createdAt"]):
                self._queue.append(meta["jobId"])
                self._set_meta(meta["jobId"], state="queued")
            self._cv.notify()

    def start(self) -> None:
        if self._thread is None:
            self._stop = False
            self._thread = threading.Thread(target=self._loop, name="job-worker", daemon=True)
            self._thread.start()

    def stop(self) -> None:
        with self._cv:
            self._stop = True
            for ev in self._cancels.values():
                ev.set()
            self._cv.notify_all()
        if self._thread is not None:
            self._thread.join(timeout=10)
            self._thread = None

    # ---- thread nền ----
    def _finish(self, job_id: str, status: dict) -> None:
        _write_json(self._dir(job_id) / "status.json", status)
        self._set_meta(job_id, state=status["state"])

    def _loop(self) -> None:
        while True:
            with self._cv:
                while not self._queue and not self._stop:
                    self._cv.wait()
                if self._stop:
                    return
                job_id = self._queue.popleft()
                cancel = self._cancels[job_id] = threading.Event()
            try:
                self._run(job_id, cancel)
            finally:
                with self._cv:
                    self._cancels.pop(job_id, None)

    def _run(self, job_id: str, cancel: threading.Event) -> None:
        meta = self._meta(job_id) or {}
        self._set_meta(job_id, state="running")
        data_root = self.settings.datasets / meta.get("datasetId", "") / "data"
        try:
            result = self._runner(self._dir(job_id), data_root, self.settings.profile, cancel,
                                  {"C4_WORKSPACE_DIR": str(self.settings.workspace)})
            state = result.get("state") if isinstance(result, dict) else None
            if state not in ("done", "failed", "cancelled"):
                raise RuntimeError(f"Runner kết thúc ở trạng thái lạ: {state}")
            self._set_meta(job_id, state=state)
        except Exception as e:  # noqa: BLE001 — mọi lỗi runner phải thành job `failed`, không chết thread
            self._finish(job_id, dict(
                jobId=job_id, state="failed", stage="index", done=0, total=1,
                error=dict(code="job_failed", message=f"Job lỗi: {e}")))


class CreateJobIn(BaseModel):
    datasetId: str  # noqa: N815 — tên trường của hợp đồng API
    pipeline: Literal["lidar", "camera"] | None = None


router = APIRouter()


@router.post("/jobs")
def post_job(body: CreateJobIn, request: Request):
    s: Settings = request.app.state.settings
    f = s.datasets / body.datasetId / "report.json"
    rep = _read_json(f)
    if rep is None:
        raise ApiError(404, "not_found", "Không tìm thấy bộ dữ liệu.")
    report = DatasetReport.model_validate(rep)
    if not report.ok:
        raise ApiError(400, "dataset_invalid",
                       "Bộ dữ liệu chưa hợp lệ: " + "; ".join(report.errors or ["không rõ lý do"]))
    # 01-CONTRACTS §4: mặc định lidar khi dataset có LiDAR, ngược lại camera
    pipeline = body.pipeline or ("lidar" if report.has_lidar else "camera")
    return {"jobId": request.app.state.queue.submit(body.datasetId, pipeline)}


def list_jobs(settings: Settings, limit: int = 50) -> list[JobSummary]:
    """Job gần nhất trước (createdAt), đọc từ job.json/status.json/report.json trên đĩa."""
    from service.selection import list_selections  # nhập muộn: tránh vòng import
    metas = []
    for meta_file in settings.jobs.glob("*/job.json"):
        meta = _read_json(meta_file)
        if isinstance(meta, dict) and meta.get("jobId"):
            metas.append(meta)
    metas.sort(key=lambda m: (m.get("createdAt", ""), m["jobId"]), reverse=True)
    items = []
    for meta in metas[:limit]:
        jid = meta["jobId"]
        state = meta.get("state", "queued")
        finished = None
        if state in ("done", "failed", "cancelled"):
            try:
                ts = (settings.jobs / jid / "status.json").stat().st_mtime
                finished = datetime.fromtimestamp(ts).isoformat(timespec="seconds")
            except OSError:
                pass
        rep = _read_json(settings.datasets / meta.get("datasetId", "") / "report.json") or {}
        sels = list_selections(settings, jid)
        items.append(JobSummary(
            job_id=jid, dataset_id=meta.get("datasetId", ""),
            pipeline=meta.get("pipeline") or "camera", state=state,
            created_at=meta.get("createdAt", ""), finished_at=finished,
            scenes=rep.get("scenes", 0), frames=rep.get("frames", 0),
            version=rep.get("version", ""),
            last_selection_id=sels[0].selection_id if sels else None))
    return items


@router.get("/jobs", response_model=JobList, response_model_by_alias=True)
def get_jobs(request: Request):
    return JobList(items=list_jobs(request.app.state.settings))


@router.get("/jobs/{job_id}", response_model=JobStatus, response_model_by_alias=True)
def get_job(job_id: str, request: Request):
    return request.app.state.queue.status(job_id)


@router.post("/jobs/{job_id}/cancel", response_model=JobStatus, response_model_by_alias=True)
def cancel_job(job_id: str, request: Request):
    return request.app.state.queue.cancel(job_id)
