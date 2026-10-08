"""FastAPI app factory. Router nằm ở các module riêng; file này chỉ ráp."""
from contextlib import asynccontextmanager

from fastapi import FastAPI

from service import datasets, frames, jobs, selection
from service.errors import install_handlers
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
    install_handlers(app)
    app.include_router(datasets.router)
    app.include_router(jobs.router)
    app.include_router(selection.router)
    app.include_router(frames.router)

    @app.get("/health")
    def health():
        return {"ok": True, "gpu": _gpu_available(), "profile": settings.profile}

    return app
