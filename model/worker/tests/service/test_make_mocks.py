import json
import re
import subprocess
import sys
from pathlib import Path

import pytest

from service import make_mocks
from service.models import (
    Analysis,
    DatasetReport,
    FrameDetail,
    FramesPage,
    JobStatus,
    SelectionResult,
)

WORKER = Path(__file__).resolve().parents[2]
PRESETS = ["balanced", "rare_first", "hard_for_model", "safety_scenarios"]
MAX_BYTES = 15 * 1024 * 1024


@pytest.fixture(scope="module")
def out(tmp_path_factory):
    d = tmp_path_factory.mktemp("mocks")
    assert make_mocks.main(["--out", str(d)]) == 0
    return d


def load(out, name):
    return json.loads((out / "mocks" / name).read_text(encoding="utf-8"))


def test_every_listed_file_exists(out):
    names = {p.name for p in (out / "mocks").glob("*.json")}
    expected = {"dataset-report.json", "job-running.json", "job-done.json", "frames-page1.json",
                "analysis.json", *(f"selection-{p}.json" for p in PRESETS)}
    assert expected <= names
    assert len([n for n in names if n.startswith("frame-detail-")]) == 5


def test_each_json_validates_against_its_model(out):
    assert DatasetReport.model_validate(load(out, "dataset-report.json")).ok
    assert JobStatus.model_validate(load(out, "job-running.json")).state == "running"
    assert JobStatus.model_validate(load(out, "job-done.json")).state == "done"
    for p in PRESETS:
        sel = SelectionResult.model_validate(load(out, f"selection-{p}.json"))
        assert sel.preview and sel.budget_b >= 1
    assert FramesPage.model_validate(load(out, "frames-page1.json")).items
    assert Analysis.model_validate(load(out, "analysis.json")).pool["frames"] == 36
    for f in (out / "mocks").glob("frame-detail-*.json"):
        d = FrameDetail.model_validate_json(f.read_text(encoding="utf-8"))
        assert d.cams and d.lidar is not None and d.boxes3d


def test_scenario_shape_one_night_scene_and_one_missing_camera(out):
    rep = load(out, "dataset-report.json")
    assert rep["scenes"] == 3 and rep["frames"] == 36 and rep["hasLidar"]
    by_cam = rep["imagesByCam"]
    assert by_cam["CAM_FRONT"] == 36 and by_cam["CAM_BACK"] == 24  # một scene mất CAM_BACK


def test_media_urls_rewritten_and_files_exist(out):
    text = "".join(p.read_text(encoding="utf-8") for p in (out / "mocks").glob("*.json"))
    assert "/api/media/" not in text
    urls = set(re.findall(r'"(/mock-media/[^"]+)"', text))
    assert urls
    for u in urls:
        f = out / "public" / u.lstrip("/")
        assert f.is_file() and f.stat().st_size > 0, u


def test_total_size_within_budget(out):
    total = sum(p.stat().st_size for p in out.rglob("*") if p.is_file())
    assert 0 < total <= MAX_BYTES


def test_export_openapi_lists_all_endpoints():
    p = subprocess.run([sys.executable, "-m", "service.export_openapi"], cwd=WORKER,
                       capture_output=True, check=False)
    assert p.returncode == 0, p.stderr.decode("utf-8", "replace")
    spec = json.loads(p.stdout.decode("utf-8"))
    ops = {(m.upper(), path) for path, item in spec["paths"].items() for m in item}
    assert len(ops) == 15, sorted(ops)
    assert ("GET", "/jobs") in ops and ("GET", "/jobs/{job_id}/selections") in ops
    assert ("POST", "/jobs/{job_id}/select") in ops and ("GET", "/health") in ops
    assert ("GET", "/jobs/{job_id}/params-schema") in ops
    props = spec["components"]["schemas"]["SelectParamsIn"]["properties"]
    assert "maxPerScene" in props and props["budget"]["maximum"] == 0.1
    assert {"tier", "k", "lam", "quotaOff"} <= set(props)
    frame = spec["components"]["schemas"]["FrameSummary"]["properties"]
    assert {"rRar", "bevUrl"} <= set(frame)
    sel = spec["components"]["schemas"]["SelectionResult"]["properties"]
    assert {"pipeline", "tierAvailable"} <= set(sel)


def test_lidar_mocks_exist_and_validate(out):
    schema = load(out, "params-schema.json")
    assert schema["tierAvailable"] == [0]
    assert {"tier", "k", "lam", "maxPerScene", "quotaOff", "alpha", "beta", "gamma"} == {
        f["key"] for f in schema["fields"]}
    sel = SelectionResult.model_validate(load(out, "selection-lidar.json"))
    assert sel.pipeline == "lidar" and sel.tier_available == [0]
    assert sel.preview and sel.preview[0].bev_url.endswith(".png") and sel.preview[0].r_rar >= 0
    assert JobStatus.model_validate(load(out, "job-done-lidar.json")).pipeline == "lidar"
    page = FramesPage.model_validate(load(out, "frames-lidar-page1.json"))
    assert page.items and all(i.bev_url.endswith(".png") for i in page.items)
    assert Analysis.model_validate(load(out, "analysis-lidar.json")).pool["hasLidar"] is True
    details = list((out / "mocks").glob("lidar-frame-detail-*.json"))
    assert details
    for f in details:
        d = FrameDetail.model_validate_json(f.read_text(encoding="utf-8"))
        # lidar_index xuất media hiển thị (c8f56a1): có ảnh camera + hộp 3D khi dataset có
        assert d.bev_url.endswith(".png") and d.cams and d.boxes3d and d.lidar is not None
