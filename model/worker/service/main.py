"""FastAPI app factory. Router nằm ở các module riêng; file này chỉ ráp."""
import json
from contextlib import asynccontextmanager
from datetime import datetime

from fastapi import FastAPI, Request

from service import datasets, frames, gpu_warm, jobs, remote, selection, sessions
from service.errors import ApiError, install_handlers
from service.settings import Settings


def _gpu_available() -> bool:
    try:
        import torch
        return bool(torch.cuda.is_available())
    except ImportError:
        return False


def create_app(settings: Settings | None = None, runner=None, encoder_factory=None) -> FastAPI:
    """`runner`/`encoder_factory` thay run_job và text encoder (chỉ để test)."""
    settings = settings or Settings()
    queue = jobs.JobQueue(settings, runner)

    @asynccontextmanager
    async def lifespan(_app):
        queue.recover()
        queue.start()
        yield
        queue.stop()

    app = FastAPI(title="VCuboidFIT worker", lifespan=lifespan)
    app.state.settings = settings
    app.state.queue = queue
    app.state.encoders = selection.EncoderHolder(encoder_factory)
    app.state.job_locks = selection.JobLocks()
    app.state.remote = remote.RemoteQueue(settings)
    app.state.gpu_warm = gpu_warm.GpuWarmer(settings, app.state.remote)
    @app.middleware("http")
    async def session_middleware(request, call_next):
        request.state.session_id = sessions.session_from(request)
        if request.state.session_id:
            sessions.touch(settings, request.state.session_id)
        return await call_next(request)
    install_handlers(app)
    app.include_router(datasets.router)
    app.include_router(jobs.router)
    app.include_router(selection.router)
    app.include_router(frames.router)
    app.include_router(remote.router)
    app.include_router(gpu_warm.router)
    app.include_router(__import__("service.export_images", fromlist=["router"]).router)

    @app.get("/health")
    def health():
        last_seen = getattr(app.state.remote, "last_seen", None)
        return {"ok": True, "gpu": _gpu_available(), "profile": settings.profile,
                "remoteAgent": {"lastSeen": last_seen}}

    @app.get("/sessions/current")
    def current_session(request: Request):
        sid = getattr(request.state, "session_id", None)
        if not sid:
            raise ApiError(404, "not_found", "Không tìm thấy phiên.")
        path = settings.workspace / "sessions" / f"{sid}.json"
        doc = json.loads(path.read_text(encoding="utf-8"))
        usage = sum(p.stat().st_size for p in settings.workspace.rglob("*") if p.is_file())
        return {**doc, "usageBytes": usage, "expiresAt": sessions._iso(
            datetime.fromisoformat(doc["lastSeen"]).timestamp() + settings.session_ttl_h * 3600)}

    @app.delete("/sessions/current")
    def delete_current(request: Request):
        sid = getattr(request.state, "session_id", None)
        if not sid:
            raise ApiError(404, "not_found", "Không tìm thấy phiên.")
        return {"deleted": sessions.delete_session(settings, queue, sid)}

    return app
