"""python -m service.make_mocks --out DIR — bộ mock cho web, sinh từ job thật (model giả).

Ghi DIR/mocks/*.json và DIR/public/mock-media/<jobId>/... (URL đã viết lại thành /mock-media/...).
Công cụ dev: dùng bộ sinh nuScenes giả của `tests/fixtures`, chạy từ thư mục `worker/`.
"""
import argparse
import json
import os
import re
import shutil
import sys
import tempfile
import time
import uuid
import zipfile
from datetime import datetime
from pathlib import Path

import pandas as pd
from fastapi.testclient import TestClient

from service.main import create_app
from service.models import (
    Analysis,
    DatasetReport,
    FrameDetail,
    FramesPage,
    JobStatus,
    SelectionResult,
)
from service.settings import Settings

PRESETS = ["balanced", "rare_first", "hard_for_model", "safety_scenarios"]
SELECT_BASE = {"minLuma": 0, "minBlurVar": 0}  # ảnh giả màu phẳng: không để chất lượng loại hết
N_DETAILS = 5
MAX_BYTES = 15 * 1024 * 1024
MEDIA_URL = re.compile(r"/api/media/([0-9a-f]+)/(thumbs|lidar|images|bev)/([^\"]+)")
JOB_TIMEOUT_S = 900
LIDAR_MIN_POINTS = 50  # nuScenes giả: 300 điểm/frame < filter.min_points (2000) của lidar.yaml


def _dump(path: Path, obj) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(obj, ensure_ascii=False, indent=1), encoding="utf-8")


def _zip_data(data: Path, out: Path) -> None:
    out.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(out, "w", zipfile.ZIP_STORED) as z:
        for p in sorted(data.rglob("*")):
            if p.is_file():
                z.write(p, p.relative_to(data.parent).as_posix())


def _running_snapshot(done: dict) -> dict:
    """Ảnh chụp job đang chạy stage det: cùng hình dạng JobStatus thật."""
    stages = []
    for s in done["stages"]:
        state = {"index": "done", "dino": "done", "det": "running"}.get(s["name"], "queued")
        stages.append({**s, "state": state,
                       "durationSec": s["durationSec"] if state == "done" else 0})
    return {**done, "state": "running", "stage": "det", "done": 18, "total": 36,
            "etaSec": 40, "stages": stages, "error": None}


def build(out: Path, workspace: Path, uploads: Path | None = None) -> None:
    """`uploads`: thư mục zip thật (vcf-pack); bỏ trống ⇒ nuScenes giả 3 scene × 12 frame."""
    os.environ["C4_FAKE_MODELS"] = "1"
    settings = Settings(workspace=workspace / "ws", sevenzip="__khong_co_7z__")
    if uploads is not None:
        shutil.copytree(uploads, settings.uploads / "mock")
    else:
        from tests.fixtures.make_nuscenes import make_nuscenes  # nuScenes giả của hồ sơ 01

        data = make_nuscenes(workspace / "src", n_scenes=3, frames_per_scene=12,
                             night_scenes=(0,), drop_cams={"scene1": ["CAM_BACK"]})
        _zip_data(data, settings.uploads / "mock" / "all.zip")
    mocks = out / "mocks"
    with TestClient(create_app(settings)) as c:
        rep = c.post("/datasets", json={"uploadId": "mock"}).json()
        DatasetReport.model_validate(rep)
        _dump(mocks / "dataset-report.json", rep)
        # mock camera: ghi rõ pipeline để mock cũ không đổi khi dataset có LiDAR
        jid = c.post("/jobs", json={"datasetId": rep["datasetId"], "pipeline": "camera"}) \
            .json()["jobId"]
        t0 = time.monotonic()
        while (st := c.get(f"/jobs/{jid}").json())["state"] not in ("done", "failed"):
            if time.monotonic() - t0 > JOB_TIMEOUT_S:
                raise RuntimeError("job mock chạy quá lâu")
            time.sleep(0.5)
        if st["state"] != "done":
            raise RuntimeError(f"job mock thất bại: {st.get('error')}")
        _dump(mocks / "job-done.json", JobStatus.model_validate(st).model_dump(by_alias=True))
        _dump(mocks / "job-running.json",
              JobStatus.model_validate(_running_snapshot(st)).model_dump(by_alias=True))
        sids = {}
        for p in PRESETS:
            sel = c.post(f"/jobs/{jid}/select", json={**SELECT_BASE, "preset": p}).json()
            SelectionResult.model_validate(sel)
            sids[p] = sel["selectionId"]
            _dump(mocks / f"selection-{p}.json", sel)
        sid = sids["balanced"]
        page = c.get(f"/jobs/{jid}/selections/{sid}/frames", params={"budget": 0.10}).json()
        FramesPage.model_validate(page)
        _dump(mocks / "frames-page1.json", page)
        tokens = [i["sampleToken"] for i in page["items"]][:N_DETAILS]
        index = pd.read_parquet(settings.jobs / jid / "index" / "frames.parquet",
                                columns=["sample_token"])
        tokens += [t for t in index["sample_token"].drop_duplicates()
                   if t not in tokens][:N_DETAILS - len(tokens)]  # bù bằng frame chưa được chọn
        for tok in tokens:
            d = c.get(f"/jobs/{jid}/frames/{tok}", params={"sid": sid}).json()
            FrameDetail.model_validate(d)
            _dump(mocks / f"frame-detail-{tok}.json", d)
        an = c.get(f"/jobs/{jid}/selections/{sid}/analysis").json()
        Analysis.model_validate(an)
        _dump(mocks / "analysis.json", an)
        data_dir = settings.datasets / rep["datasetId"] / "data"
        lidar_jid = _lidar_job(settings, rep["datasetId"], data_dir, mocks)
        _dump(mocks / "params-schema.json", c.get(f"/jobs/{lidar_jid}/params-schema").json())
        lsel = c.post(f"/jobs/{lidar_jid}/select", json=SELECT_BASE).json()
        SelectionResult.model_validate(lsel)
        _dump(mocks / "selection-lidar.json", lsel)
        lsid = lsel["selectionId"]
        lp = c.get(f"/jobs/{lidar_jid}/selections/{lsid}/frames",
                   params={"budget": 0.10}).json()
        FramesPage.model_validate(lp)
        _dump(mocks / "frames-lidar-page1.json", lp)
        for tok in [i["sampleToken"] for i in lp["items"]][:N_DETAILS]:
            d = c.get(f"/jobs/{lidar_jid}/frames/{tok}", params={"sid": lsid}).json()
            FrameDetail.model_validate(d)
            _dump(mocks / f"lidar-frame-detail-{tok}.json", d)
        lan = c.get(f"/jobs/{lidar_jid}/selections/{lsid}/analysis").json()
        Analysis.model_validate(lan)
        _dump(mocks / "analysis-lidar.json", lan)
    _rewrite_media(out, settings.jobs / jid, data_dir, settings.jobs / lidar_jid)


def _lidar_job(settings: Settings, dataset_id: str, data_dir: Path, mocks: Path) -> str:
    """Job LiDAR cho mock: chạy thật `lidar_index` + `lidar_t0` in-process.

    Không qua hàng đợi GPU vì nuScenes giả chỉ có 300 điểm/frame < `filter.min_points` của
    lidar.yaml; hạ ngưỡng đó xuống `LIDAR_MIN_POINTS` chỉ trong tiến trình t0 của mock.
    """
    from unittest.mock import patch

    from c4.cli.lidar_index import main as lidar_index_main
    from c4.cli.lidar_t0 import main as lidar_t0_main
    from c4.lidar import load_lidar_config

    jid = uuid.uuid4().hex[:12]
    job = settings.jobs / jid
    job.mkdir(parents=True, exist_ok=True)
    _dump(job / "job.json", dict(jobId=jid, datasetId=dataset_id, pipeline="lidar",
                                 createdAt=datetime.now().isoformat(timespec="seconds"),
                                 state="done"))
    argv = ["--data-root", str(data_dir), "--job-dir", str(job)]
    if lidar_index_main(argv) != 0:
        raise RuntimeError("mock lidar: stage lidar_index thất bại")
    cfg = load_lidar_config()
    cfg["filter"]["min_points"] = LIDAR_MIN_POINTS
    with patch("c4.cli.lidar_t0.load_lidar_config", lambda: cfg):
        if lidar_t0_main(argv) != 0:
            raise RuntimeError("mock lidar: stage t0 thất bại")
    status = dict(jobId=jid, state="done", pipeline="lidar", stage="t0", done=1, total=1,
                  stages=[dict(name=n, state="done", durationSec=0, peakVramMb=0)
                          for n in ("lidar_index", "t0")], error=None)
    _dump(job / "status.json", status)
    _dump(mocks / "job-done-lidar.json",
          JobStatus.model_validate(status).model_dump(by_alias=True))
    return jid


def _rewrite_media(out: Path, job_dir: Path, data_dir: Path, lidar_job_dir: Path) -> None:
    """Chép đúng các file media mà mock nhắc tới và đổi URL sang /mock-media/.

    `bev/` thuộc job LiDAR (`lidar_t0`), `thumbs/`+`lidar/` thuộc job camera (`build_index`).
    """
    sources = {"thumbs": job_dir / "media" / "thumbs", "lidar": job_dir / "media" / "lidar",
               "bev": lidar_job_dir / "media" / "bev", "images": data_dir}
    for f in sorted((out / "mocks").glob("*.json")):
        text = f.read_text(encoding="utf-8")
        for jid, kind, rest in set(MEDIA_URL.findall(text)):
            dst = out / "public" / "mock-media" / jid / kind / rest
            dst.parent.mkdir(parents=True, exist_ok=True)
            src = rest[:-4] + ".bin" if kind == "lidar" and rest.endswith(".f16") else rest
            shutil.copyfile(sources[kind] / src, dst)  # URL .f16, file trên đĩa .bin
        f.write_text(MEDIA_URL.sub(r"/mock-media/\1/\2/\3", text), encoding="utf-8")


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--out", required=True, type=Path)
    ap.add_argument("--uploads", type=Path, default=None,
                    help="thư mục part zip thật (vcf_part_*.zip + manifest); mặc định: dữ liệu giả")
    args = ap.parse_args(argv)
    with tempfile.TemporaryDirectory() as tmp:
        build(args.out, Path(tmp), args.uploads)
    total = sum(p.stat().st_size for p in args.out.rglob("*") if p.is_file())
    if total > MAX_BYTES:
        print(f"Bộ mock {total} byte vượt trần {MAX_BYTES}", file=sys.stderr)
        return 2
    n = len(list((args.out / "mocks").glob("*.json")))
    print(f"mock: {n} json · {total} byte -> {args.out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
