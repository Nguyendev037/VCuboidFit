"""Dataset: giải nén upload, gộp data/, kiểm theo spec §1.4, route POST/GET /datasets."""
import hashlib
import json
import re
import shutil
import time
import uuid
from datetime import datetime
from pathlib import Path

from fastapi import APIRouter, Request
from pydantic import BaseModel

from c4.contracts import CAMS, ContractError
from c4.data.index import build_frames
from c4.data.nusc import NuscTables
from service.archives import (
    MANIFEST,
    DatasetError,
    extract,
    find_data_dirs,
    group_archives,
    merge_into,
)
from service.errors import ApiError
from service.models import DatasetReport
from service.settings import Settings


def check_manifest(upload_dir: Path) -> list[str]:
    """Part thiếu / lệch SHA-256 so với vcf_manifest.json (không có manifest ⇒ không lỗi)."""
    mf = Path(upload_dir) / MANIFEST
    if not mf.is_file():
        return []
    try:
        parts = json.loads(mf.read_text(encoding="utf-8"))["parts"]
    except (ValueError, KeyError, TypeError):
        return [f"File {MANIFEST} không đọc được"]
    errors = []
    for p in parts:
        f = Path(upload_dir) / p["name"]
        if not f.is_file():
            errors.append(f"Thiếu part {p['name']}")
        elif hashlib.sha256(f.read_bytes()).hexdigest() != p["sha256"]:
            errors.append(f"Part {p['name']} bị hỏng (SHA-256 không khớp)")
    return errors


def validate_dataset(data_root: Path, dataset_id: str = "") -> DatasetReport:
    data_root = Path(data_root)
    bad = DatasetReport(dataset_id=dataset_id, ok=False)
    try:
        t = NuscTables.load(data_root)
    except FileNotFoundError as e:
        bad.errors = [f"Dữ liệu nuScenes không đầy đủ: {e}"]
        return bad
    except ContractError as e:
        bad.errors = [f"Dữ liệu nuScenes không hợp lệ: {e}"]
        return bad
    frames = build_frames(t, data_root)
    by_cam = {c: int((frames["cam"] == c).sum()) for c in CAMS}
    rep = DatasetReport(
        dataset_id=dataset_id, ok=True, scenes=int(frames["scene_token"].nunique()),
        frames=int(frames["sample_token"].nunique()), images_by_cam=by_cam,
        has_annotations=t.has_annotations, version=t.version_dir.name)
    chan = {k: t.sensor[c["sensor_token"]]["channel"] for k, c in t.calibrated_sensor.items()}
    rep.has_lidar = any(
        chan[sd["calibrated_sensor_token"]] == "LIDAR_TOP" and sd["is_key_frame"]
        and (data_root / sd["filename"]).is_file() for sd in t.sample_data.values())
    if len(frames) == 0:
        rep.ok = False
        rep.errors.append("Không có ảnh camera (CAM_*) nào trên đĩa: cần ít nhất một camera.")
    if not rep.has_annotations:
        rep.warnings.append("Không có nhãn (sample_annotation.json): bỏ qua phần GT hiếm.")
    if not rep.has_lidar:
        rep.warnings.append("Không có LiDAR_TOP: khung xem 3D sẽ không có point cloud.")
    return rep


def _save(settings: Settings, rep: DatasetReport) -> None:
    d = settings.datasets / rep.dataset_id
    d.mkdir(parents=True, exist_ok=True)
    (d / "report.json").write_text(rep.model_dump_json(by_alias=True), encoding="utf-8")


class _Progress:
    """Ghi `uploads/<id>/progress.json` (01-CONTRACTS §4); lỗi ghi file không làm hỏng xét tệp."""

    def __init__(self, up: Path, upload_id: str):
        self.path, self.upload_id, self.t0 = up / "progress.json", upload_id, time.monotonic()

    def write(self, phase: str, done: float, total: float, unit: str) -> None:
        elapsed = time.monotonic() - self.t0
        eta = elapsed * (total - done) / done if done > 0 and phase not in ("done", "error") else None
        if phase == "done":
            eta = 0.0
        doc = dict(uploadId=self.upload_id, phase=phase, done=done, total=total, unit=unit,
                   elapsedSec=round(elapsed, 2), etaSec=None if eta is None else round(max(eta, 0.0), 1),
                   updatedAt=datetime.now().isoformat(timespec="seconds"))
        try:
            tmp = self.path.with_suffix(".tmp")
            tmp.write_text(json.dumps(doc), encoding="utf-8")
            tmp.replace(self.path)
        except OSError:
            pass


def create_dataset(settings: Settings, upload_id: str) -> DatasetReport:
    up = settings.uploads / upload_id
    if not up.is_dir():
        raise ApiError(404, "not_found", "Không tìm thấy phiên tải lên.")
    ds_id = uuid.uuid4().hex[:12]
    ds = settings.datasets / ds_id
    raw, data = ds / "raw", ds / "data"
    rep = DatasetReport(dataset_id=ds_id, ok=False)
    errors = check_manifest(up)
    prog = _Progress(up, upload_id)
    prog.write("extract", 0, 1, "bytes")
    try:
        archives = group_archives(sorted(p for p in up.iterdir() if p.is_file()))
        if not errors and not archives:
            errors.append("Không có file nén (.zip/.rar/.7z) nào trong phiên tải lên.")
        if not errors:
            srcs = []
            total = sum(a.stat().st_size for a in archives) or 1
            done = 0
            prog.write("extract", 0, total, "bytes")
            for i, a in enumerate(archives):
                extract(a, raw / str(i), settings.sevenzip)
                srcs += find_data_dirs(raw / str(i))
                done += a.stat().st_size
                prog.write("extract", done, total, "bytes")
            if not srcs:
                errors.append(
                    "Không tìm thấy thư mục data/ chứa v1.0-*/ hoặc samples/ trong file nén.")
            else:
                prog.write("merge", 0, 1, "steps")
                merge_into(srcs, data)
                prog.write("merge", 1, 1, "steps")
    except DatasetError as e:
        errors.append(str(e))
    finally:
        shutil.rmtree(raw, ignore_errors=True)
    if errors:
        rep.errors = errors
    else:
        prog.write("validate", 0, 1, "steps")
        rep = validate_dataset(data, ds_id)
    _save(settings, rep)
    prog.write("done" if rep.ok else "error", 1, 1, "steps")
    return rep


class CreateDatasetIn(BaseModel):
    uploadId: str  # noqa: N815 — tên trường của hợp đồng API


router = APIRouter()


@router.post("/datasets", response_model=DatasetReport, response_model_by_alias=True)
def post_dataset(body: CreateDatasetIn, request: Request):
    return create_dataset(request.app.state.settings, body.uploadId)


@router.get("/datasets/progress/{upload_id}")
def get_progress(upload_id: str, request: Request):
    """Tiến độ xét tệp (SPEC-P05); 404 khi chưa có `progress.json` hoặc id không hợp lệ."""
    f = request.app.state.settings.uploads / upload_id / "progress.json"
    if not re.fullmatch(r"[A-Za-z0-9_-]+", upload_id) or not f.is_file():
        raise ApiError(404, "not_found", "Chưa có tiến độ xét tệp.")
    return json.loads(f.read_text(encoding="utf-8"))


@router.get("/datasets/{dataset_id}", response_model=DatasetReport, response_model_by_alias=True)
def get_dataset(dataset_id: str, request: Request):
    f = request.app.state.settings.datasets / dataset_id / "report.json"
    if not f.is_file():
        raise ApiError(404, "not_found", "Không tìm thấy bộ dữ liệu.")
    return DatasetReport.model_validate_json(f.read_text(encoding="utf-8"))
