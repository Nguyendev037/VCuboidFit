"""Xuất ảnh hiếm: ZIP ảnh gốc + BEV + meta của đúng lô B frame đã chọn (SPEC-P07 §3).

Chỉ đọc dữ liệu có sẵn của job (frames.parquet, media/bev, rare_*.parquet, context_frame);
KHÔNG sinh lại ảnh và KHÔNG giữ file tạm sau khi stream xong.
"""
import csv
import io
import json
import re
import tempfile
import zipfile
from datetime import datetime
from pathlib import Path
from typing import Iterator, Literal

import pandas as pd
from fastapi import APIRouter, Request
from fastapi.responses import StreamingResponse

from c4.contracts import CAMS, read_table
from service.engines import AXES, context_table, split_tags
from service.errors import ApiError
from service.sessions import require_job_owner
from service.frames import SelectionData, _budget, _check_budget, get_data

router = APIRouter()
MAX_FRAMES = 500
CHUNK = 1 << 20
INDEX_COLUMNS = ["rank", "sample_token", "scene_name", "timestamp", "engine", "pred_tags",
                 "reasons", "s_frame", "context_tags", "folder", "missing"]


def _records(df: pd.DataFrame) -> list[dict]:
    return json.loads(df.to_json(orient="records"))  # NaN -> null, numpy -> python


def _context_meta(ctx: pd.DataFrame | None, token: str) -> dict | None:
    """Cùng dạng `FrameDetail.context` (M6): perCam + sunElevDeg; None khi job không có tầng bối cảnh."""
    if ctx is None:
        return None
    rows = ctx[ctx["sample_token"] == token]
    if rows.empty:
        return None
    per_cam = {}
    for row in rows.to_dict("records"):
        per_cam[row["cam"]] = dict(
            tags=[row[f"tag_{a}"] for a in AXES if pd.notna(row[f"tag_{a}"]) and row[f"tag_{a}"]],
            probs={a: json.loads(row[f"p_{a}"]) if row[f"p_{a}"] else {} for a in AXES},
            cvFlags=split_tags(row["cv_flags"]), review=bool(row["review"]),
            reviewReasons=split_tags(row["review_reasons"]))
    sun = rows.loc[rows["cam"] == "CAM_FRONT", "sun_elev_deg"].dropna()
    if sun.empty:
        sun = rows["sun_elev_deg"].dropna()
    return dict(perCam=per_cam, sunElevDeg=float(sun.iloc[0]) if len(sun) else None)


def _safe_file(root: Path | None, rel: str) -> Path | None:
    """File nằm trong `root` (chặn `..`), hoặc None."""
    if root is None or not rel:
        return None
    path = (root / rel).resolve()
    try:
        path.relative_to(root.resolve())
    except ValueError:
        return None
    return path if path.is_file() else None


def _dataset_root(settings, job_dir: Path) -> Path | None:
    try:
        meta = json.loads((job_dir / "job.json").read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    dataset = meta.get("datasetId") or meta.get("dataset_id")
    if not isinstance(dataset, str) or not re.fullmatch(r"[A-Za-z0-9_-]+", dataset):
        return None
    return settings.datasets / dataset / "data"


def _rare_tables(job_dir: Path, result: dict):
    if result.get("engineVersion") != "rare_v24":
        return None, None
    artifact = job_dir / "engines" / "rare_v24" / result["selectionId"]
    return (read_table(artifact / "rare_frames.parquet", "rare_frames"),
            read_table(artifact / "rare_objects.parquet", "rare_objects"))


def _s_frame(data: SelectionData, token: str) -> float:
    row = data.fs.loc[token]
    for col in ("s", "S_hybrid"):
        if col in row.index:
            return float(row[col])
    return 0.0


def build_zip(settings, job_id: str, data: SelectionData, tokens: list[str], sid: str,
              budget: float, cams: str, lidar: bool):
    """ZIP trong `SpooledTemporaryFile` (tràn xuống đĩa khi > 64 MB), con trỏ đã về đầu file."""
    job_dir = settings.jobs / job_id
    engine = data.result.get("engineVersion", "c4_legacy")
    root = _dataset_root(settings, job_dir)
    wanted = ["CAM_FRONT"] if cams == "front" else list(CAMS)
    frames_path = job_dir / "index" / "frames.parquet"
    frames = (pd.read_parquet(frames_path, filters=[("sample_token", "in", tokens)])
              if frames_path.is_file() else pd.DataFrame(columns=["sample_token", "cam", "img_path"]))
    rare_frames, rare_objects = _rare_tables(job_dir, data.result)
    ctx = context_table(job_dir)
    if ctx is not None:
        ctx = ctx[ctx["sample_token"].isin(tokens)]
    spool = tempfile.SpooledTemporaryFile(max_size=64 << 20)  # noqa: SIM115 — đóng khi stream xong
    index_rows = []
    with zipfile.ZipFile(spool, "w", zipfile.ZIP_DEFLATED) as zf:
        for token in tokens:
            rank = int(data.rank.get(token, 0))
            scene = str(data.names.get(token, "")) or str(data.fs.loc[token].get("scene_token", ""))
            folder = f"{rank:03d}_{re.sub(r'[^A-Za-z0-9_-]', '_', scene)}_{re.sub(r'[^A-Za-z0-9_-]', '_', token[:8])}"
            missing = []
            cam_rows = frames[frames["sample_token"] == token].set_index("cam")
            for cam in wanted:
                src = _safe_file(root, str(cam_rows.loc[cam, "img_path"])) if cam in cam_rows.index else None
                if src is None:
                    missing.append(cam)
                    continue
                zf.write(src, f"{folder}/{cam}{src.suffix.lower() or '.jpg'}",
                         compress_type=zipfile.ZIP_STORED)  # JPEG đã nén sẵn
            if lidar:
                bev = job_dir / "media" / "bev" / f"{token}.png"
                if bev.is_file():
                    zf.write(bev, f"{folder}/lidar_bev.png", compress_type=zipfile.ZIP_STORED)
                else:
                    missing.append("lidar_bev")
            objects, pred_tags, gate = [], [], None
            if rare_frames is not None:
                row = rare_frames[rare_frames["sample_token"] == token]
                if len(row):
                    pred_tags = split_tags(row["pred_tags"].iloc[0])
                    gate = str(row["gate"].iloc[0])
                objects = _records(rare_objects[rare_objects["sample_token"] == token])
            context = _context_meta(ctx, token)
            reasons = [o["reasons"] for o in objects if o.get("reasons")] or \
                [str(data.reason.get(token, ""))]
            zf.writestr(f"{folder}/meta.json", json.dumps(dict(
                sampleToken=token, rank=rank, sceneName=scene, engine=engine,
                predTags=pred_tags, reasons=reasons, objects=objects, context=context, gate=gate,
            ), ensure_ascii=False, indent=2))
            ctx_tags = sorted({t for c in (context or {}).get("perCam", {}).values() for t in c["tags"]})
            index_rows.append([rank, token, scene, data.timestamp(token), engine,
                               "|".join(pred_tags), "|".join(reasons), f"{_s_frame(data, token):.6f}",
                               "|".join(ctx_tags), folder, "|".join(missing)])
        buf = io.StringIO(newline="")
        writer = csv.writer(buf)
        writer.writerow(INDEX_COLUMNS)
        writer.writerows(index_rows)
        zf.writestr("index.csv", "﻿" + buf.getvalue())
        zf.writestr("README.txt", _readme(job_id, sid, engine, data, budget, cams, lidar, len(tokens)))
    spool.seek(0)
    return spool


def _readme(job_id, sid, engine, data, budget, cams, lidar, n) -> str:
    params = data.result.get("params", {})
    return "\n".join([
        "VCuboidFIT - Xuat anh hiem (lo frame can gan nhan)",
        f"Job: {job_id} | Selection: {sid} | Engine: {engine} | Profile: {params.get('profile')}",
        f"Ngan sach: {budget * 100:g}% = {n} frame | Camera: {cams} | Anh LiDAR BEV: {lidar}",
        f"Thoi diem xuat: {datetime.now().isoformat(timespec='seconds')}",
        "",
        "Cau truc: index.csv (bang tom tat), moi thu muc <rank>_<scene>_<token8>/ gom anh camera goc,",
        "lidar_bev.png (neu bat) va meta.json (the du doan, ly do, ung vien, boi canh).",
        "The du doan KHONG phai nhan that: can nguoi gan nhan xac nhan. Cot `missing` cua index.csv",
        "liet ke anh khong tim thay tren may chu.",
        "",
        "Nguon du lieu: nuScenes (Motional). Giay phep CC BY-NC-SA 4.0, chi dung phi thuong mai,",
        "bat buoc ghi nguon nuScenes / Motional.",
        "",
    ])


def _stream(spool) -> Iterator[bytes]:
    try:
        while chunk := spool.read(CHUNK):
            yield chunk
    finally:
        spool.close()  # không giữ file tạm sau khi stream


@router.get("/jobs/{job_id}/selections/{sid}/export-images.zip")
def export_images(job_id: str, sid: str, request: Request, budget: float | None = None,
                  cams: Literal["all", "front"] = "all", lidar: bool = True):
    require_job_owner(request, job_id)
    _check_budget(budget)
    try:
        data = get_data(request, job_id, sid)
    except ApiError as e:
        if e.status == 404 and e.code == "not_found" and "kết quả chọn" in e.message:
            raise ApiError(404, "SELECTION_NOT_FOUND", e.message) from e
        raise
    use = _budget(data, budget)
    rows = data.hybrid[data.hybrid["rank"] <= data.budget_b(use)]
    tokens = [t for t in rows["sample_token"] if t in data.fs.index]
    if not tokens:
        raise ApiError(409, "EMPTY_SELECTION", "Selection không có frame nào để xuất.")
    if len(tokens) > MAX_FRAMES:
        raise ApiError(413, "EXPORT_TOO_LARGE",
                       f"Lô có {len(tokens)} frame, vượt giới hạn {MAX_FRAMES}. Hãy giảm ngân sách.")
    spool = build_zip(request.app.state.settings, job_id, data, tokens, sid, use, cams, lidar)
    return StreamingResponse(
        _stream(spool), media_type="application/zip",
        headers={"Content-Disposition": f'attachment; filename="vcf_{job_id}_{sid}_rare.zip"'})
