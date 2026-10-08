"""Hàng đợi Tầng 1 từ xa (SPEC-P02): Colab kéo việc, đẩy signals.parquet về job.

Hàng đợi = file JSON trong workspace/remote/, khóa bằng threading.Lock + ghi nguyên tử.
Chỉ một worker, tải rất thấp, tạm thời — KHÔNG DB/Redis.
"""
import hmac
import json
import os
import re
import tarfile
import threading
import uuid
from datetime import datetime, timedelta
from pathlib import Path

from fastapi import APIRouter, Depends, Request
from fastapi.responses import JSONResponse, Response, StreamingResponse
from pydantic import ValidationError
from starlette.datastructures import UploadFile
from starlette.formparsers import MultiPartException, MultiPartParser

from service.errors import ApiError
from service.models import FailIn, HeartbeatIn, RemoteParams, RemoteTask
from service.settings import Settings

TASK_ID = re.compile(r"^t1_[0-9a-f]{12}$")
JOB_ID = re.compile(r"^[0-9a-f]{12}$")
MAX_ATTEMPTS = 3
FINAL = ("done", "failed", "cancelled")
CHUNK = 1 << 20
JSON_MAX = 64 * 1024  # body JSON của /remote/*
MULTIPART_SLACK = 1 << 20  # biên cho boundary/field của multipart


class ResultTooLarge(MultiPartException):
    pass


class ResultParser(MultiPartParser):
    """Chặn byte vượt ngân sách trước khi parser ghi tệp spool."""

    def __init__(self, headers, stream, file_limit: int):
        super().__init__(headers, stream, max_files=2, max_fields=1, max_part_size=JSON_MAX)
        self.file_limit = file_limit
        self.part_bytes = 0

    def on_part_begin(self) -> None:
        super().on_part_begin()
        self.part_bytes = 0

    def on_part_data(self, data: bytes, start: int, end: int) -> None:
        self.part_bytes += end - start
        if self._current_part.file is not None and self.part_bytes > self.file_limit:
            raise ResultTooLarge("Kết quả vượt giới hạn kích thước.")
        super().on_part_data(data, start, end)


async def bounded_stream(request: Request, limit: int):
    received = 0
    async for chunk in request.stream():
        received += len(chunk)
        if received > limit:
            raise ResultTooLarge("Body vượt giới hạn kích thước.")
        yield chunk


class TaskExists(ApiError):
    def __init__(self, task_id: str):
        super().__init__(409, "task_exists", "Job này đã có việc Tầng 1 từ xa đang chờ hoặc chạy.")
        self.task_id = task_id


def _write_json(path: Path, obj) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(f"{path.name}.{uuid.uuid4().hex[:6]}.tmp")
    tmp.write_text(json.dumps(obj, ensure_ascii=False), encoding="utf-8")
    os.replace(tmp, path)


def _public(rec: dict) -> dict:
    """RemoteTask = bản ghi trừ bundleSha256, camelCase."""
    return RemoteTask.model_validate(rec).model_dump(by_alias=True)


class RemoteQueue:
    def __init__(self, settings: Settings, clock=datetime.now):
        self.settings = settings
        self.clock = clock  # test thay để giả thời gian
        self._lock = threading.RLock()

    # ---- file ----
    def _now(self) -> datetime:
        return self.clock()

    def _iso(self, dt: datetime) -> str:
        return dt.isoformat(timespec="seconds")

    def _path(self, task_id: str) -> Path:
        if not TASK_ID.match(task_id):
            raise ApiError(404, "not_found", "Không tìm thấy việc.")
        return self.settings.remote / f"{task_id}.json"

    def _all(self) -> list[dict]:
        d = self.settings.remote
        out = []
        for f in (d.glob("t1_*.json") if d.is_dir() else []):
            try:
                out.append(json.loads(f.read_text(encoding="utf-8")))
            except (OSError, ValueError):
                continue
        return out

    def get(self, task_id: str) -> dict:
        f = self._path(task_id)
        try:
            return json.loads(f.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            raise ApiError(404, "not_found", "Không tìm thấy việc.") from None

    def _save(self, rec: dict) -> dict:
        _write_json(self._path(rec["taskId"]), rec)
        return rec

    # ---- web-side ----
    def create(self, job_id: str, params: dict) -> dict:
        if not JOB_ID.match(job_id):
            raise ApiError(404, "not_found", "Không tìm thấy job.")
        job = self.settings.jobs / job_id
        meta_f = job / "job.json"
        if not meta_f.is_file():
            raise ApiError(404, "not_found", "Không tìm thấy job.")
        if not (job / "lidar" / "index.parquet").is_file():
            raise ApiError(409, "job_not_ready", "Job chưa có chỉ mục LiDAR để chạy Tầng 1.")
        meta = json.loads(meta_f.read_text(encoding="utf-8"))
        with self._lock:
            self.reap()
            for r in self._all():
                if r["jobId"] == job_id and r["state"] in ("queued", "leased"):
                    raise TaskExists(r["taskId"])
            rec = dict(taskId=f"t1_{uuid.uuid4().hex[:12]}", jobId=job_id,
                       datasetId=meta.get("datasetId", ""), state="queued", params=params,
                       createdAt=self._iso(self._now()), leasedAt=None, leaseUntil=None,
                       attempts=0, error=None, bundleSha256=None, leaseId=None)
            return self._save(rec)

    def latest(self, job_id: str) -> dict | None:
        with self._lock:
            self.reap()
            mine = [r for r in self._all() if r["jobId"] == job_id]
        return max(mine, key=lambda r: r["createdAt"]) if mine else None

    def cancel(self, job_id: str) -> dict | None:
        """Huỷ task queued/leased của job. Không có task/đã kết thúc: bỏ qua, KHÔNG ném lỗi."""
        with self._lock:
            hit = None
            for r in self._all():
                if r["jobId"] == job_id and r["state"] in ("queued", "leased"):
                    r["state"] = "cancelled"
                    r["leaseUntil"] = None
                    self._save(r)
                    hit = r
            return hit

    # ---- Colab-side ----
    def reap(self) -> None:
        with self._lock:
            now = self._now()
            for r in self._all():
                if r["state"] == "leased" and r["leaseUntil"] \
                        and datetime.fromisoformat(r["leaseUntil"]) < now:
                    r.update(state="queued", leasedAt=None, leaseUntil=None, leaseId=None)
                    self._save(r)

    def claim(self) -> dict | None:
        with self._lock:
            self.reap()
            queued = sorted((r for r in self._all() if r["state"] == "queued"),
                            key=lambda r: r["createdAt"])
            if not queued:
                return None
            r = queued[0]
            now = self._now()
            r.update(state="leased", leasedAt=self._iso(now), attempts=r["attempts"] + 1,
                     leaseId=uuid.uuid4().hex,
                     leaseUntil=self._iso(now + timedelta(seconds=self.settings.remote_lease_sec)))
            return self._save(r)

    def leased(self, task_id: str, lease_id: str | None = None, check: bool = False) -> dict:
        """Task phải đang leased (sau reap) — ngược lại 409 not_leased.
        check=True: lease_id phải khớp lượt hiện tại — ngược lại 409 lease_mismatch."""
        with self._lock:
            self.reap()
            r = self.get(task_id)
            if r["state"] != "leased":
                raise ApiError(409, "not_leased", "Việc không còn được giữ (hết hạn hoặc đã huỷ).")
            if check:
                self._check_lease(r, lease_id)
            return r

    @staticmethod
    def _check_lease(r: dict, lease_id: str | None) -> None:
        if not lease_id or not hmac.compare_digest(lease_id.encode(),
                                                   (r.get("leaseId") or "").encode()):
            raise ApiError(409, "lease_mismatch", "Lease không khớp lượt nhận việc hiện tại.")

    def heartbeat(self, task_id: str, stage: str, progress: float, lease_id: str | None) -> dict:
        with self._lock:
            r = self.leased(task_id, lease_id, check=True)
            r["leaseUntil"] = self._iso(
                self._now() + timedelta(seconds=self.settings.remote_lease_sec))
            r["stage"], r["progress"] = stage, progress
            return self._save(r)

    def finish(self, task_id: str, signals_path: Path, manifest_path: Path | None,
               meta: dict, lease_id: str | None) -> dict:
        import pandas as pd

        from c4.contracts import read_table
        with self._lock:
            r = self.leased(task_id, lease_id, check=True)
            job = self.settings.jobs / r["jobId"]
            try:
                sig = read_table(str(signals_path), "t1_signals")
                idx = pd.read_parquet(job / "lidar" / "index.parquet", columns=["sample_token"])
            except Exception as e:  # noqa: BLE001 - parquet hỏng / sai schema
                raise ApiError(422, "bad_signals", f"Kết quả Tầng 1 không hợp lệ: {e}") from e
            missing = set(idx["sample_token"]) - set(sig["sample_token"])
            if missing:
                raise ApiError(422, "bad_signals",
                               f"Kết quả Tầng 1 thiếu {len(missing)} sample_token của chỉ mục.")
            t1 = job / "t1"
            t1.mkdir(parents=True, exist_ok=True)
            if manifest_path is not None:
                os.replace(manifest_path, t1 / "signals.parquet.manifest.json")
            os.replace(signals_path, t1 / "signals.parquet")  # sau cùng: tier_available mở khoá
            _write_json(t1 / "remote_meta.json", meta)
            r.update(state="done", leaseUntil=None, error=None, leaseId=None)
            return self._save(r)

    def fail(self, task_id: str, error: str, lease_id: str | None) -> dict:
        with self._lock:
            self.reap()
            r = self.get(task_id)
            if r["state"] != "leased":
                return r
            self._check_lease(r, lease_id)
            r["error"] = error[:2000]
            if r["attempts"] >= MAX_ATTEMPTS:
                r["state"] = "failed"
            else:
                r.update(state="queued", leasedAt=None)
            r["leaseUntil"] = None
            r["leaseId"] = None
            return self._save(r)


# ---- bundle ----
def _iter_files(root: Path):
    for dp, dns, fns in os.walk(root, followlinks=False):
        dns[:] = sorted(d for d in dns if not (Path(dp) / d).is_symlink())
        for fn in sorted(fns):
            p = Path(dp) / fn
            if p.is_file() and not p.is_symlink():
                yield p


def _tar_entry(src: Path, arcname: str):
    """Một file: header + nội dung + padding (tar thủ công, stream, không giữ file trong RAM)."""
    size = src.stat().st_size
    ti = tarfile.TarInfo(arcname)
    ti.size, ti.mode = size, 0o644
    yield ti.tobuf(tarfile.GNU_FORMAT)
    left = size
    with open(src, "rb") as f:
        while left > 0:
            buf = f.read(min(CHUNK, left))
            if not buf:
                buf = b"\0" * min(CHUNK, left)  # file bị cắt giữa chừng: giữ đúng độ dài header
            left -= len(buf)
            yield buf
    pad = -size % tarfile.BLOCKSIZE
    if pad:
        yield b"\0" * pad


def bundle_stream(index: Path, data: Path):
    yield from _tar_entry(index, "index.parquet")
    if data.is_dir():
        for p in _iter_files(data):
            yield from _tar_entry(p, "data/" + p.relative_to(data).as_posix())
    yield b"\0" * (tarfile.BLOCKSIZE * 2)


# ---- HTTP ----
router = APIRouter()


def _q(request: Request) -> RemoteQueue:
    return request.app.state.remote


def _enabled(request: Request) -> None:
    if not request.app.state.settings.remote_token:
        raise ApiError(404, "remote_disabled", "Worker chưa bật VCF_REMOTE_TOKEN.")


def require_token(request: Request) -> None:
    _enabled(request)
    expect = request.app.state.settings.remote_token.encode()
    auth = request.headers.get("authorization", "")
    got = auth[7:].encode() if auth.lower().startswith("bearer ") else b""
    if not hmac.compare_digest(got, expect):
        raise ApiError(401, "unauthorized", "Sai hoặc thiếu token.")


def body_guard(kind: str):
    """Kiểm Content-Length TRƯỚC khi parse body: 411 nếu thiếu/chunked, 413 nếu quá lớn."""
    def dep(request: Request) -> None:
        h = request.headers
        raw = h.get("content-length")
        if raw is None or h.get("transfer-encoding") or not raw.isdigit():
            raise ApiError(411, "length_required", "Thiếu hoặc sai Content-Length.")
        if kind == "result":
            limit = request.app.state.settings.remote_max_result_mb * 1024 * 1024 + MULTIPART_SLACK
        else:
            limit = JSON_MAX
        if int(raw) > limit:
            raise ApiError(413, "too_large", "Body vượt giới hạn kích thước.")
    return dep


def lease_header(request: Request) -> str | None:
    return request.headers.get("x-lease-id")


async def _json_body(request: Request, model):
    try:
        raw = b"".join([chunk async for chunk in bounded_stream(request, JSON_MAX)])
        return model.model_validate(json.loads(raw) if raw.strip() else {})
    except ResultTooLarge as e:
        raise ApiError(413, "too_large", e.message) from e
    except (ValidationError, ValueError):
        raise ApiError(422, "bad_request", "Tham số không hợp lệ.") from None


@router.post("/jobs/{job_id}/t1-remote", status_code=201)
async def create_task(job_id: str, request: Request):
    _enabled(request)
    params = await _json_body(request, RemoteParams)
    try:
        rec = _q(request).create(job_id, params.model_dump())
    except TaskExists as e:
        return JSONResponse({"error": {"code": e.code, "message": e.message,
                                       "taskId": e.task_id}}, status_code=409)
    return _public(rec)


@router.get("/jobs/{job_id}/t1-remote")
def get_task(job_id: str, request: Request):
    _enabled(request)
    rec = _q(request).latest(job_id)
    if rec is None:
        raise ApiError(404, "not_found", "Job chưa có việc Tầng 1 từ xa.")
    return _public(rec)


@router.delete("/jobs/{job_id}/t1-remote")
def cancel_task(job_id: str, request: Request):
    _enabled(request)
    q = _q(request)
    rec = q.latest(job_id)
    if rec is None:
        raise ApiError(404, "not_found", "Job chưa có việc Tầng 1 từ xa.")
    if rec["state"] in FINAL:
        raise ApiError(409, "task_finished", "Việc đã kết thúc, không huỷ được.")
    return _public(q.cancel(job_id) or rec)


@router.get("/remote/t1/next", dependencies=[Depends(require_token)])
def next_task(request: Request):
    rec = _q(request).claim()
    if rec is None:
        return Response(status_code=204)
    return {**_public(rec), "leaseId": rec["leaseId"]}  # chỉ claim trả leaseId


@router.get("/remote/t1/{task_id}/bundle", dependencies=[Depends(require_token)])
def bundle(task_id: str, request: Request):
    rec = _q(request).leased(task_id)
    s: Settings = request.app.state.settings
    ds = rec["datasetId"]
    if not re.match(r"^[A-Za-z0-9_-]+$", ds):
        raise ApiError(404, "not_found", "Không tìm thấy dữ liệu.")
    index = s.jobs / rec["jobId"] / "lidar" / "index.parquet"
    if not index.is_file() or index.is_symlink():
        raise ApiError(404, "not_found", "Không tìm thấy chỉ mục.")
    return StreamingResponse(bundle_stream(index, s.datasets / ds / "data"),
                             media_type="application/x-tar")


@router.post("/remote/t1/{task_id}/heartbeat",
             dependencies=[Depends(require_token), Depends(body_guard("json"))])
async def heartbeat(task_id: str, request: Request):
    body = await _json_body(request, HeartbeatIn)
    return _public(_q(request).heartbeat(task_id, body.stage, body.progress,
                                         lease_header(request)))


@router.post("/remote/t1/{task_id}/fail",
             dependencies=[Depends(require_token), Depends(body_guard("json"))])
async def fail(task_id: str, request: Request):
    body = await _json_body(request, FailIn)
    q = _q(request)
    q.get(task_id)  # 404 nếu không có
    return _public(q.fail(task_id, body.error, lease_header(request)))


@router.post("/remote/t1/{task_id}/result",
             dependencies=[Depends(require_token), Depends(body_guard("result"))])
async def result(task_id: str, request: Request):
    # Không khai báo File/Form: FastAPI sẽ parse (spool) multipart TRƯỚC dependency.
    # Token + Content-Length đã qua; tự parse form sau khi kiểm lease.
    q = _q(request)
    s: Settings = request.app.state.settings
    lease_id = lease_header(request)
    q.leased(task_id, lease_id, check=True)
    limit = s.remote_max_result_mb * 1024 * 1024
    try:
        form = await ResultParser(request.headers,
                                  bounded_stream(request, limit + MULTIPART_SLACK),
                                  limit).parse()
    except ResultTooLarge as e:
        raise ApiError(413, "too_large", e.message) from e
    except Exception:  # noqa: BLE001 - multipart hỏng
        raise ApiError(422, "bad_request", "Body multipart không hợp lệ.") from None
    try:
        signals, manifest = form.get("signals"), form.get("manifest")
        if not isinstance(signals, UploadFile):
            raise ApiError(422, "bad_signals", "Thiếu tệp signals.")
        if manifest is not None and not isinstance(manifest, UploadFile):
            raise ApiError(422, "bad_request", "manifest phải là tệp.")
        try:
            meta_obj = json.loads(form.get("meta") or "{}")
        except (ValueError, TypeError):
            raise ApiError(422, "bad_request", "meta không phải JSON.") from None
        tmp_dir = s.remote / "_tmp"
        tmp_dir.mkdir(parents=True, exist_ok=True)

        async def save(up: UploadFile, suffix: str) -> Path:
            p = tmp_dir / f"{task_id}.{uuid.uuid4().hex[:6]}{suffix}"
            total = 0
            with open(p, "wb") as f:
                while chunk := await up.read(CHUNK):
                    total += len(chunk)
                    if total > limit:
                        f.close()
                        p.unlink(missing_ok=True)
                        raise ApiError(413, "too_large", "Kết quả vượt giới hạn kích thước.")
                    f.write(chunk)
            return p

        sig_p = await save(signals, ".parquet")
        man_p = None
        try:
            if manifest is not None:
                man_p = await save(manifest, ".json")
            return _public(q.finish(task_id, sig_p, man_p, meta_obj, lease_id))
        finally:
            sig_p.unlink(missing_ok=True)
            if man_p:
                man_p.unlink(missing_ok=True)
    finally:
        await form.close()
