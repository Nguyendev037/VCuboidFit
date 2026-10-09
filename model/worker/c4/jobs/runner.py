"""Job runner: chạy các stage của một pipeline, mỗi stage một tiến trình con `c4.cli.*`.

Pipeline đọc từ `job.json` (`pipeline`): `camera` = index → dino → det → clip → merge (mặc định khi
job.json không nói gì), `lidar` = lidar_index → t0 → t1 (01-CONTRACTS §4). Stage `t1` suy luận
seed đã train qua Docker khi `VCF_T1_EXP` được đặt; stage này không chặn job (`OPTIONAL_STAGES`).

Một khoá `filelock` (`<workspace>/gpu.lock`) bao cả job: hai job cùng lúc thì job sau chờ
(`status.state = "queued"`). Tiến độ lấy từ `progress/<stage>.json` của stage con, ghi vào
`status.json` mỗi giây. Stage đã xong (có đủ output + dấu `progress/<stage>.done.json` do runner
ghi sau khi stage thoát 0) thì bỏ qua.
"""
import json
import os
import re
import subprocess
import sys
import threading
import time
from datetime import datetime
from pathlib import Path

from filelock import FileLock, Timeout

STAGES = ["index", "dino", "det", "clip", "merge"]
PIPELINES = dict(  # thứ tự stage bắt buộc của từng pipeline (camera giữ nguyên như trước)
    camera=STAGES,
    lidar=["lidar_index", "t0", "t1"])
OPTIONAL_STAGES = {"t1"}  # stage lỗi không làm job failed (01-CONTRACTS §C6)
MODULES = dict(index="build_index", dino="extract_dino", det="extract_det", clip="extract_clip",
               merge="merge_features", lidar_index="lidar_index", t0="lidar_t0", t1="lidar_t1")
OUTPUTS = dict(  # đường dẫn tương đối thư mục job; ghi nguyên tử nên có đủ = stage đã ghi xong
    index=["index/frames.parquet", "index/frames.parquet.manifest.json",
           "index/cam_poses.parquet", "index/cam_poses.parquet.manifest.json"],
    dino=["cache/dino_cls.npy", "cache/feat_dino.parquet"],
    det=["cache/detections.parquet", "cache/feat_det.parquet"],
    clip=["cache/clip_img.npy", "cache/feat_clip.parquet"],
    merge=["cache/features_cache.parquet", "cache/features_cache.parquet.manifest.json"],
    lidar_index=["lidar/index.parquet"],
    t0=["lidar/z0.npy", "lidar/filter.parquet"],
    t1=["t1/signals.parquet"])
POLL_S = 1.0
TERMINATE_WAIT_S = 10.0
WORKER_DIR = Path(__file__).resolve().parents[2]
DEFAULT_WORKSPACE = Path(__file__).resolve().parents[3] / "workspace"


def stage_command(stage: str, job_dir, data_root, profile: str) -> list[str]:
    return [sys.executable, "-m", f"c4.cli.{MODULES[stage]}", "--job-dir", str(job_dir),
            "--data-root", str(data_root), "--profile", profile, "--resume"]


def _now() -> str:
    return datetime.now().astimezone().isoformat(timespec="microseconds")


def _atomic_json(obj, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + ".tmp")
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


def _last_line(path: Path) -> str:
    try:
        lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
    except OSError:
        return ""
    return next((ln.strip() for ln in reversed(lines) if ln.strip()), "")


# Thông điệp của lidar_t1 / infer_t1 → câu cho người dùng (không lộ biến môi trường, đường dẫn).
_T1_REASONS = (
    (re.compile(r"VCF_T1_EXP chưa đặt"), "Lúc phân tích, máy chưa bật model Tầng 1."),
    (re.compile(r"^skip: thiếu "), "Model Tầng 1 trên máy chưa đủ file."),
    (re.compile(r"cần GPU"), "Máy không có GPU NVIDIA cho Tầng 1."),
    (re.compile(r"docker lỗi|docker: |Cannot connect to the Docker|dockerDesktopLinuxEngine",
                re.IGNORECASE),
     "Không chạy được Docker cho Tầng 1. Hãy bật Docker Desktop rồi chạy lại."),
    (re.compile(r"vi phạm contract|thiếu đầu vào"), "Dữ liệu Tầng 1 không khớp lần chạy này."),
)


def tier1_reason(log: Path, rc: int | None = None) -> str | None:
    """Lý do tiếng Việt cho stage `t1` skipped/failed, đọc từ `logs/t1.log` (plan 09 D3)."""
    try:
        lines = [ln.strip() for ln in log.read_text(encoding="utf-8", errors="replace").splitlines()
                 if ln.strip()]
    except OSError:
        lines = []
    for ln in reversed(lines[-40:]):  # docker in nhiều dòng sau thông điệp gốc ⇒ dò ngược
        for pat, text in _T1_REASONS:
            if pat.search(ln):
                return text
    tail = re.sub(r"^skip:\s*", "", lines[-1]) if lines else ""
    tail = re.sub(r"VCF_[A-Z0-9_]+", "cấu hình model Tầng 1", tail)
    tail = re.sub(r"([A-Za-z]:)?[\\/][^\s]+", "…", tail)[:160]  # bỏ đường dẫn
    if rc not in (None, 0):
        return f"Tầng 1 lỗi (mã {rc}): {tail}" if tail else f"Tầng 1 lỗi (mã {rc})."
    return tail or None


def _marker(job: Path, stage: str) -> Path:
    return job / "progress" / f"{stage}.done.json"


def _is_done(job: Path, stage: str) -> bool:
    return _marker(job, stage).is_file() and all((job / p).is_file() for p in OUTPUTS[stage])


def _failure_message(stage: str, rc: int, log: Path) -> str:
    tail = _last_line(log)
    if rc == 3:
        return (f"Hết VRAM ở stage {stage} dù đã giảm batch xuống 1. Hãy giảm kích thước trong "
                "profile (det.imgsz 640, dino.model dinov2_vits14) hoặc dùng GPU lớn hơn.")
    if rc == 4:
        return f"Thiếu file đầu vào ở stage {stage}: {tail}"
    if rc == 2:
        return f"Vi phạm contract ở stage {stage}: {tail}"
    return f"Stage {stage} thoát bất thường (mã {rc}): {tail}"


class _Status:
    """status.json = JobStatus (spec tổng §4.2) + startedAt/finishedAt/skipped trên từng stage."""

    def __init__(self, job: Path, pipeline: str = "camera"):
        self.pipeline = pipeline if pipeline in PIPELINES else "camera"
        self.stages = PIPELINES[self.pipeline]
        self.path = job / "status.json"
        self.d = dict(
            jobId=job.name, state="queued", pipeline=self.pipeline, stage=self.stages[0],
            done=0, total=1, etaSec=None,
            stages=[dict(name=s, state="queued", durationSec=0, peakVramMb=0, startedAt=None,
                         finishedAt=None, skipped=False) for s in self.stages],
            error=None)

    def stage(self, name: str) -> dict:
        return next(s for s in self.d["stages"] if s["name"] == name)

    def write(self) -> None:
        _atomic_json(self.d, self.path)

    def set(self, **kw) -> None:
        self.d.update(kw)
        self.write()

    def finish(self, state: str, error: dict | None = None) -> dict:
        self.set(state=state, error=error, etaSec=None)
        return self.d


def _terminate(proc: subprocess.Popen) -> None:
    proc.terminate()
    try:
        proc.wait(timeout=TERMINATE_WAIT_S)
    except subprocess.TimeoutExpired:
        proc.kill()
        proc.wait()


def _sync_progress(job: Path, st: _Status, stage: str, t_wall: float, t_mono: float) -> None:
    """Đọc progress/<stage>.json (bỏ file cũ của lần chạy trước) vào status rồi ghi status.json."""
    p = job / "progress" / f"{stage}.json"
    info = _read_json(p) if p.is_file() and p.stat().st_mtime >= t_wall - 1.0 else None
    s = st.stage(stage)
    s["durationSec"] = round(time.monotonic() - t_mono, 3)
    if info:
        done, total = int(info["done"]), int(info["total"])
        s["peakVramMb"] = int(info.get("peak_vram_mb", 0))
        eta = None
        if 0 < done < total:
            eta = round((time.monotonic() - t_mono) * (total - done) / done)
        elif total and done >= total:
            eta = 0
        st.d.update(done=done, total=total, etaSec=eta)
    st.write()


def _run_stage(job: Path, st: _Status, stage: str, cmd: list[str], env: dict,
               cancel: threading.Event) -> int | None:
    """Chạy một stage con. Trả mã thoát, hoặc None nếu bị huỷ."""
    s = st.stage(stage)
    log_path = job / "logs" / f"{stage}.log"
    log_path.parent.mkdir(parents=True, exist_ok=True)
    t_wall, t_mono = time.time(), time.monotonic()
    s.update(state="running", startedAt=_now(), finishedAt=None, durationSec=0, skipped=False,
             reason=None)
    st.set(stage=stage, done=0, total=1, etaSec=None)
    proc = None
    cancelled = False
    try:
        with open(log_path, "wb") as log:
            proc = subprocess.Popen(cmd, stdout=log, stderr=subprocess.STDOUT,
                                    stdin=subprocess.DEVNULL, env=env)
            while proc.poll() is None:
                _sync_progress(job, st, stage, t_wall, t_mono)
                if cancel.wait(POLL_S):
                    _terminate(proc)
                    cancelled = True
    finally:
        if proc is not None and proc.poll() is None:  # KeyboardInterrupt giữa chừng
            _terminate(proc)
    _sync_progress(job, st, stage, t_wall, t_mono)
    s["finishedAt"] = _now()
    return None if cancelled else proc.returncode


def _child_env(env: dict | None) -> dict:
    merged = {**os.environ, **(env or {})}
    merged.setdefault("PYTORCH_CUDA_ALLOC_CONF", "expandable_segments:True")
    merged.setdefault("PYTHONIOENCODING", "utf-8")  # log tiếng Việt không vỡ trên Windows
    merged["PYTHONPATH"] = os.pathsep.join(filter(None, [str(WORKER_DIR),
                                                         merged.get("PYTHONPATH")]))
    return merged


def _run_stages(job: Path, data_root: Path, profile: str, st: _Status, env: dict,
                cancel: threading.Event) -> dict:
    for stage in PIPELINES[st.pipeline]:
        s = st.stage(stage)
        if _is_done(job, stage):
            mark = _read_json(_marker(job, stage)) or {}
            # giữ thời gian thật của lần chạy trước (UI "Bước 2" hết hiện 0.0 s khi chạy lại t1)
            s.update(state="done", skipped=True, durationSec=float(mark.get("durationSec", 0)),
                     peakVramMb=int(mark.get("peakVramMb", 0)))
            st.set(stage=stage, done=1, total=1)
            continue
        if cancel.is_set():
            return st.finish("cancelled")
        rc = _run_stage(job, st, stage, stage_command(stage, job, data_root, profile), env, cancel)
        if rc is None:
            s["state"] = "cancelled"
            return st.finish("cancelled")
        if rc != 0 and stage in OPTIONAL_STAGES:
            s["reason"] = tier1_reason(job / "logs" / f"{stage}.log", rc)
            s["state"] = "failed"  # không finish, không ghi marker: job vẫn done, lần sau thử lại
            st.write()
            continue
        if rc != 0:
            s["state"] = "failed"
            msg = _failure_message(stage, rc, job / "logs" / f"{stage}.log")
            return st.finish("failed", dict(code=rc, message=msg))
        if stage in OPTIONAL_STAGES and not all((job / p).is_file() for p in OUTPUTS[stage]):
            # CLI thoát 0 nhưng không ra output = skip có lý do: KHÔNG im lặng, không ghi marker
            s["state"] = "skipped"
            s["reason"] = tier1_reason(job / "logs" / f"{stage}.log")
            st.write()
            continue
        s["state"] = "done"
        s.pop("reason", None)
        if not (job / "progress" / f"{stage}.json").is_file():
            st.d.update(done=1, total=1)  # index/merge không báo tiến độ: xong = 1/1
        _atomic_json(dict(durationSec=s["durationSec"], peakVramMb=s["peakVramMb"],
                          finishedAt=s["finishedAt"]), _marker(job, stage))
        st.write()
    return st.finish("done")


def run_job(job_dir, data_root, profile, cancel: threading.Event | None = None,
            env: dict | None = None) -> dict:
    """Chạy đủ các stage cho một job; trả JobStatus (cũng được ghi ở `<job>/status.json`).

    Pipeline lấy từ `job.json` (`pipeline`); thiếu/không hợp lệ ⇒ `camera` (job cũ vẫn chạy đúng).
    """
    job, data_root = Path(job_dir).resolve(), Path(data_root).resolve()
    cancel = cancel or threading.Event()
    child_env = _child_env(env)
    workspace = Path(child_env.get("C4_WORKSPACE_DIR") or DEFAULT_WORKSPACE)
    meta = _read_json(job / "job.json") or {}
    st = _Status(job, meta.get("pipeline") or "camera")
    st.write()
    workspace.mkdir(parents=True, exist_ok=True)
    lock = FileLock(str(workspace / "gpu.lock"))
    try:
        while True:  # job sau chờ khoá GPU ở trạng thái queued; huỷ được trong lúc chờ
            if cancel.is_set():
                return st.finish("cancelled")
            try:
                lock.acquire(timeout=POLL_S)
                break
            except Timeout:
                continue
        st.set(state="running")
        return _run_stages(job, data_root, profile, st, child_env, cancel)
    except KeyboardInterrupt:
        st.finish("cancelled")
        raise
    finally:
        if lock.is_locked:
            lock.release()
