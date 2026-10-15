"""Session ownership and cleanup for the optional cloud workspace mode."""
import json
import re
import shutil
import time
from datetime import datetime, timezone
from pathlib import Path

from fastapi import Request

from service.errors import ApiError

SID_RE = re.compile(r"^[0-9a-f]{32}$")


def session_from(request: Request) -> str | None:
    settings = request.app.state.settings
    sid = request.headers.get("x-vcf-session")
    return sid if settings.sessions and sid and SID_RE.fullmatch(sid) else None


def _sessions_dir(settings) -> Path:
    return settings.workspace / "sessions"


def _session_file(settings, sid: str) -> Path:
    return _sessions_dir(settings) / f"{sid}.json"


def _now() -> float:
    return time.time()


def _iso(ts: float) -> str:
    return datetime.fromtimestamp(ts, timezone.utc).isoformat(timespec="seconds")


def require_owner(settings, sid: str | None, owner: str | None) -> None:
    if settings.sessions and (sid is None or owner != sid):
        raise ApiError(404, "not_found", "Không tìm thấy tài nguyên.")


def touch(settings, sid: str) -> None:
    if not settings.sessions or not SID_RE.fullmatch(sid):
        return
    path = _session_file(settings, sid)
    path.parent.mkdir(parents=True, exist_ok=True)
    now = _now()
    try:
        current = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        current = {"sessionId": sid, "createdAt": _iso(now)}
    try:
        previous = datetime.fromisoformat(current.get("lastSeen", current["createdAt"])).timestamp()
    except (KeyError, ValueError):
        previous = 0
    if "lastSeen" in current and now - previous < 60:
        return
    current.update(sessionId=sid, lastSeen=_iso(now))
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(current), encoding="utf-8")
    tmp.replace(path)


def owner_for_job(settings, job_id: str) -> str | None:
    try:
        meta = json.loads((settings.jobs / job_id / "job.json").read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    return meta.get("sessionId")


def owner_for_dataset(settings, dataset_id: str) -> str | None:
    try:
        report = json.loads((settings.datasets / dataset_id / "report.json").read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    return report.get("sessionId")


def require_job_owner(request: Request, job_id: str) -> str | None:
    sid = getattr(request.state, "session_id", None)
    require_owner(request.app.state.settings, sid, owner_for_job(request.app.state.settings, job_id))
    return sid


def expired(settings, now: float) -> list[str]:
    cutoff = now - settings.session_ttl_h * 3600
    out = []
    for path in _sessions_dir(settings).glob("*.json"):
        try:
            doc = json.loads(path.read_text(encoding="utf-8"))
            last = datetime.fromisoformat(doc["lastSeen"]).timestamp()
            if last < cutoff and SID_RE.fullmatch(doc.get("sessionId", path.stem)):
                out.append(doc.get("sessionId", path.stem))
        except (OSError, ValueError, KeyError):
            continue
    return out


def delete_session(settings, queue, sid: str) -> dict:
    require_owner(settings, sid, sid)
    deleted = {"uploads": 0, "datasets": 0, "jobs": 0}
    for root, key in ((settings.uploads, "uploads"), (settings.datasets, "datasets"), (settings.jobs, "jobs")):
        for child in list(root.iterdir()) if root.is_dir() else []:
            meta_name = "job.json" if key == "jobs" else "report.json"
            try:
                doc = json.loads((child / meta_name).read_text(encoding="utf-8"))
            except (OSError, ValueError):
                continue
            if doc.get("sessionId") != sid:
                continue
            if key == "jobs":
                queue.cancel(child.name)
                deadline = time.monotonic() + 30
                while time.monotonic() < deadline:
                    try:
                        meta = json.loads((child / "job.json").read_text(encoding="utf-8"))
                    except (OSError, ValueError):
                        meta = {}
                    if meta.get("state") not in ("queued", "running"):
                        break
                    time.sleep(0.1)
                try:
                    queue.delete(child.name)
                except ApiError as exc:
                    if exc.status == 409:
                        raise ApiError(409, "session_busy", "Job đang huỷ dở.") from exc
                    raise
            else:
                shutil.rmtree(child, ignore_errors=True)
            deleted[key] += 1
    if settings.remote.is_dir():
        for task_file in list(settings.remote.glob("t1_*.json")):
            try:
                task = json.loads(task_file.read_text(encoding="utf-8"))
            except (OSError, ValueError):
                continue
            if task.get("sessionId") == sid:
                task_file.unlink(missing_ok=True)
    _session_file(settings, sid).unlink(missing_ok=True)
    return deleted


def purge_orphans(settings, now: float) -> dict:
    cutoff = now - settings.session_ttl_h * 3600
    removed = 0
    for root, meta_name in ((settings.uploads, None), (settings.datasets, "report.json"), (settings.jobs, "job.json")):
        for child in list(root.iterdir()) if root.is_dir() else []:
            if child.is_symlink():
                continue
            try:
                doc = json.loads((child / meta_name).read_text(encoding="utf-8")) if meta_name else {}
                stale = child.stat().st_mtime < cutoff
            except (OSError, ValueError):
                continue
            if stale and (not doc.get("sessionId") or not _session_file(settings, doc["sessionId"]).exists()):
                shutil.rmtree(child, ignore_errors=True)
                removed += 1
    return {"orphans": removed}
