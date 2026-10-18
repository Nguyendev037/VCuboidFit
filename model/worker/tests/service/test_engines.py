"""M6: legacy compatibility, dispatch errors, and rare selection through the API."""
import copy
import json
import math

import pytest
from fastapi.testclient import TestClient

from c4.cli import lidar_index, lidar_t0
from c4.contracts import CONTEXT_FRAME, read_table, write_table
from c4.lidar import load_lidar_config
from service import engines
from service.main import create_app
from service.models import SelectParamsIn
from service.settings import Settings
from tests.fixtures.make_nuscenes import make_nuscenes
from tests.service.test_select import make_job


def test_rare_camera_cache_fallback_uses_lidar_only(tmp_path, monkeypatch):
    calls = []

    def fake_run(job, root, **kwargs):
        calls.append(kwargs["profile"])
        if kwargs["profile"] == "multisensor":
            raise FileNotFoundError("cache/context_frame.parquet, cache/cam_front.parquet")
        return {"fallback": True}

    monkeypatch.setattr(engines, "run_rare_v24", fake_run)
    result, warnings = engines._run_rare_with_fallback(
        tmp_path / "job", tmp_path / "root", "multisensor", 0.05)

    assert result == {"fallback": True}
    assert calls == ["multisensor", "lidar_only"]
    assert warnings == ["CAMERA_CACHE_MISSING"]


def test_rare_lidar_input_error_is_not_fallback(tmp_path, monkeypatch):
    def fake_run(job, root, **kwargs):
        raise FileNotFoundError("lidar/index.parquet")

    monkeypatch.setattr(engines, "run_rare_v24", fake_run)
    with pytest.raises(FileNotFoundError, match="lidar/index.parquet"):
        engines._run_rare_with_fallback(
            tmp_path / "job", tmp_path / "root", "multisensor", 0.05)


def test_rare_lidar_only_does_not_retry(tmp_path, monkeypatch):
    calls = []

    def fake_run(job, root, **kwargs):
        calls.append(kwargs["profile"])
        raise FileNotFoundError("cache/context_frame.parquet")

    monkeypatch.setattr(engines, "run_rare_v24", fake_run)
    with pytest.raises(FileNotFoundError, match="cache/context_frame.parquet"):
        engines._run_rare_with_fallback(
            tmp_path / "job", tmp_path / "root", "lidar_only", 0.05)
    assert calls == ["lidar_only"]


def test_default_route_preserves_legacy_fields(tmp_path, monkeypatch):
    monkeypatch.delenv("VCF_ENGINE_DEFAULT", raising=False)
    settings = Settings(workspace=tmp_path / "ws")
    job, _ = make_job(settings)
    app = create_app(settings, runner=lambda *a, **k: {})
    token = engines.APP.set(app)
    try:
        expected = engines.legacy_select(job, SelectParamsIn()).model_dump(by_alias=True)
        actual = engines.route("j1", SelectParamsIn()).model_dump(by_alias=True)
        assert actual == expected
        assert actual["engineVersion"] == "c4_legacy"
        assert actual["gateSummary"] is actual["tagSummary"] is actual["contextSummary"] is None
        assert actual["warningCodes"] == []
        monkeypatch.setenv("VCF_ENGINE_DEFAULT", "rare_v24")
        assert engines.route("j1", SelectParamsIn(engine_version="c4_legacy")).model_dump(
            by_alias=True) == expected
    finally:
        engines.APP.reset(token)


def test_unknown_engine_returns_422(tmp_path, monkeypatch):
    settings = Settings(workspace=tmp_path / "ws")
    make_job(settings)
    with TestClient(create_app(settings, runner=lambda *a, **k: {})) as client:
        response = client.post("/jobs/j1/select", json={"engineVersion": "unknown"})
        assert response.status_code == 422
        assert response.json()["error"]["code"] == "UNKNOWN_ENGINE"
        monkeypatch.setenv("VCF_ENGINE_DEFAULT", "invalid_default")
        assert client.post("/jobs/j1/select", json={}).status_code == 422


def test_rare_v24_fixture_and_context_api(tmp_path, monkeypatch):
    settings = Settings(workspace=tmp_path / "ws")
    blobs = {(s, i): [("human.pedestrian.adult", (8.0 + i, 2.0 * s, 0.0), 150)]
             for s in range(2) for i in range(6)}
    root = make_nuscenes(settings.datasets / "d", n_scenes=2, frames_per_scene=6, rare_frames=blobs)
    job = settings.jobs / "j1"
    cfg = copy.deepcopy(load_lidar_config())
    cfg["filter"]["min_points"] = 50
    monkeypatch.setattr(lidar_t0, "load_lidar_config", lambda: cfg)
    assert lidar_index.main(["--data-root", str(root), "--job-dir", str(job)]) == 0
    assert lidar_t0.main(["--data-root", str(root), "--job-dir", str(job)]) == 0
    (job / "job.json").write_text(json.dumps(dict(jobId="j1", datasetId="d", pipeline="lidar",
                                                state="done")), encoding="utf-8")
    # Small synthetic reference; production retains the engine's 50-VRU guard.
    real_run = engines.run_rare_v24
    monkeypatch.setattr(engines, "run_rare_v24", lambda *a, **kw: real_run(
        *a, **kw, scoring={"min_ref_vru": 0}))
    with TestClient(create_app(settings, runner=lambda *a, **k: {})) as client:
        response = client.post("/jobs/j1/select", json={"engineVersion": "rare_v24", "budget": 0.1})
        assert response.status_code == 200, response.text
        body = response.json()
        sid = body["selectionId"]
        assert body["engineVersion"] == "rare_v24" and body["budgetB"] > 0
        assert set(body["tagSummary"]) == {"R1", "R2", "R3", "H", "C", "I"}
        artifact = job / "engines" / "rare_v24" / sid
        frames = read_table(artifact / "rare_frames.parquet", "rare_frames")
        assert body["budgetB"] == math.ceil(0.1 * int((frames["gate"] == "valid").sum()))
        assert int(frames["selected"].sum()) == body["budgetB"]
        assert body["contextSummary"] is None and body["evaluationAvailable"] is False
        assert client.get(f"/jobs/j1/selections/{sid}").json() == body
        page = client.get(f"/jobs/j1/selections/{sid}/frames").json()
        assert page["total"] == body["budgetB"]
        sample = body["preview"][0]["sampleToken"]
        detail_url = f"/jobs/j1/frames/{sample}?sid={sid}"
        detail = client.get(detail_url)
        assert detail.status_code == 200, detail.text
        assert detail.json()["objects"] and detail.json()["context"] is None
        assert "explainCard" not in detail.json()
        assert client.get("/jobs/j1/review-queue?kind=context").json() == {"items": []}
        ctx = frames[["sample_token"]].iloc[:1].copy()
        ctx["sample_token"] = sample
        ctx = ctx.loc[ctx.index.repeat(2)].reset_index(drop=True)
        ctx["cam"] = ["CAM_FRONT", "CAM_BACK"]
        for column, dtype in CONTEXT_FRAME.items():
            if column not in ctx:
                ctx[column] = {"string": "", "Float32": None, "float32": 0.5, "bool": False}[dtype]
        for axis in engines.AXES:
            ctx[f"p_{axis}"] = json.dumps({"example": 1.0})
        ctx["tag_illum"], ctx["tag_glare"], ctx["tag_weather"] = "night", "headlight", "rain"
        ctx["review"], ctx["review_reasons"], ctx["cv_flags"] = True, "illum:LOW_MARGIN", "NIGHT_CV"
        (job / "cache").mkdir(exist_ok=True)
        write_table(ctx, job / "cache" / "context_frame.parquet", "context_frame")
        detail = client.get(detail_url).json()
        assert detail["context"]["sunElevDeg"] is None
        assert detail["context"]["perCam"]["CAM_FRONT"]["cvFlags"] == ["NIGHT_CV"]
        review = client.get("/jobs/j1/review-queue?kind=context&offset=1&limit=1").json()
        assert len(review["items"]) == 1 and review["items"][0]["reviewReasons"] == ["illum:LOW_MARGIN"]
        assert client.get("/jobs/j1/review-queue?limit=201").status_code == 400
        monkeypatch.setenv("VCF_ENGINE_DEFAULT", "rare_v24")
        changed = client.post("/jobs/j1/select", json={"budget": 0.1, "strategy": "diversity"})
        assert changed.status_code == 200, changed.text
        changed = changed.json()
        assert "STRATEGY_NOT_IMPLEMENTED" in changed["warningCodes"]
        assert changed["contextSummary"] == dict(night=1, glare=1, rain=1, review=1)
        manifest = json.loads((job / "engines" / "rare_v24" / changed["selectionId"] /
                               "config_used.json").read_text(encoding="utf-8"))
        assert manifest["strategy"] == "diversity"
