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

from fastapi import APIRouter, Depends, File, Form, Request, UploadFile
from fastapi.responses import JSONResponse, Response, StreamingResponse
from pydantic import ValidationError

from service.errors import ApiError
from service.models import FailIn, HeartbeatIn, RemoteParams, RemoteTask
from service.settings import Settings

TASK_ID = re.compile(r"^t1_[0-9a-f]{12}$")
JOB_ID = re.compile(r"^[0-9a-f]{12}$")
MAX_ATTEMPTS = 3
FINAL = ("done", "failed", "cancelled")
CHUNK = 1 << 20


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
            raise ApiError(404, "not_found", "Không tìm thấy việc.")

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
                       attempts=0, error=None, bundleSha256=None)
            return self._save(rec)

    def latest(self, job_id: str) -> dict | None:
        with self._lock:
            self.reap()
            mine = [r for r in self._all() if r["jobId"] == job_id]
        return max(mine, key=lambda r: r["createdAt"]) if mine else None

    def cancel(self, job_id: str) -> dict | None:
        """Huỷ task queued/leased của job. Không có task/đã kết thúc: không làm gì, KHÔNG ném lỗi."""
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
                    r.update(state="queued", leasedAt=None, leaseUntil=None)
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
                     leaseUntil=self._iso(now + timedelta(seconds=self.settings.remote_lease_sec)))
            return self._save(r)

    def leased(self, task_id: str) -> dict:
        """Task phải đang leased (sau reap) — ngược lại 409 not_leased."""
        with self._lock:
            self.reap()
            r = self.get(task_id)
            if r["state"] != "leased":
                raise ApiError(409, "not_leased", "Việc không còn được giữ (hết hạn hoặc đã huỷ).")
            return r

    def heartbeat(self, task_id: str, stage: str, progress: float) -> dict:
        with self._lock:
            r = self.leased(task_id)
            r["leaseUntil"] = self._iso(
                self._now() + timedelta(seconds=self.settings.remote_lease_sec))
            r["stage"], r["progress"] = stage, progress
            return self._save(r)

    def finish(self, task_id: str, signals_path: Path, manifest_path: Path | None,
               meta: dict) -> dict:
        import pandas as pd
        from c4.contracts import read_table
        with self._lock:
            r = self.leased(task_id)
            job = self.settings.jobs / r["jobId"]
            try:
                sig = read_table(str(signals_path), "t1_signals")
                idx = pd.read_parquet(job / "lidar" / "index.parquet", columns=["sample_token"])
            except Exception as e:  # noqa: BLE001 - parquet hỏng / sai schema
                raise ApiError(422, "bad_signals", f"Kết quả Tầng 1 không hợp lệ: {e}")
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
            r.update(state="done", leaseUntil=None, error=None)
            return self._save(r)

    def fail(self, task_id: str, error: str) -> dict:
        with self._lock:
            r = self.get(task_id)
            if r["state"] != "leased":
                return r
            r["error"] = error[:2000]
            if r["attempts"] >= MAX_ATTEMPTS:
                r["state"] = "failed"
            else:
                r.update(state="queued", leasedAt=None)
            r["leaseUntil"] = None
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


def _tar_bytes(arcname: str, payload: bytes):
    ti = tarfile.TarInfo(arcname)
    ti.size, ti.mode = len(payload), 0o644
    yield ti.tobuf(tarfile.GNU_FORMAT)
    yield payload
    pad = -len(payload) % tarfile.BLOCKSIZE
    if pad:
        yield b"\0" * pad


def _label_tokens(index: Path) -> set[str]:
    """Frame được phép mang nhãn khỏi máy: seed S (để train) và T (chấm model seed)."""
    import pandas as pd

    df = pd.read_parquet(index, columns=["sample_token", "split"])
    return set(df.loc[df["split"].isin(["S", "T"]), "sample_token"])


def bundle_stream(index: Path, data: Path, label_tokens: set[str] | None = None):
    """label_tokens ≠ None ⇒ `sample_annotation.json` chỉ giữ nhãn của các frame đó: nhãn của pool
    không rời máy (vùng nhãn seed chỉ gồm S)."""
    yield from _tar_entry(index, "index.parquet")
    if data.is_dir():
        for p in _iter_files(data):
            arc = "data/" + p.relative_to(data).as_posix()
            if label_tokens is not None and p.name == "sample_annotation.json":
                rows = json.loads(p.read_text(encoding="utf-8"))
                kept = [a for a in rows if a.get("sample_token") in label_tokens]
                yield from _tar_bytes(arc, json.dumps(kept).encode("utf-8"))
            else:
                yield from _tar_entry(p, arc)
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


async def _json_body(request: Request, model):
    try:
        raw = await request.body()
        return model.model_validate(json.loads(raw) if raw.strip() else {})
    except (ValidationError, ValueError):
        raise ApiError(422, "bad_request", "Tham số không hợp lệ.")


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
    return Response(status_code=204) if rec is None else _public(rec)


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
    return StreamingResponse(bundle_stream(index, s.datasets / ds / "data",
                                           _label_tokens(index)),
                             media_type="application/x-tar")


@router.post("/remote/t1/{task_id}/heartbeat", dependencies=[Depends(require_token)])
async def heartbeat(task_id: str, request: Request):
    body = await _json_body(request, HeartbeatIn)
    return _public(_q(request).heartbeat(task_id, body.stage, body.progress))


@router.post("/remote/t1/{task_id}/fail", dependencies=[Depends(require_token)])
async def fail(task_id: str, request: Request):
    body = await _json_body(request, FailIn)
    q = _q(request)
    q.get(task_id)  # 404 nếu không có
    return _public(q.fail(task_id, body.error))


@router.post("/remote/t1/{task_id}/result", dependencies=[Depends(require_token)])
async def result(task_id: str, request: Request, signals: UploadFile | None = File(None),
                 manifest: UploadFile | None = File(None), meta: str = Form("{}")):
    q = _q(request)
    s: Settings = request.app.state.settings
    q.leased(task_id)
    if signals is None:
        raise ApiError(422, "bad_signals", "Thiếu tệp signals.")
    try:
        meta_obj = json.loads(meta)
    except ValueError:
        raise ApiError(422, "bad_request", "meta không phải JSON.")
    limit = s.remote_max_result_mb * 1024 * 1024
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
        return _public(q.finish(task_id, sig_p, man_p, meta_obj))
    finally:
        sig_p.unlink(missing_ok=True)
        if man_p:
            man_p.unlink(missing_ok=True)
