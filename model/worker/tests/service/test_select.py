import json
import threading

import pytest
from fastapi.testclient import TestClient

from service.main import create_app
from service.settings import Settings
from tests.fixtures.make_fixture import make_fixture, write_job_dir


@pytest.fixture
def settings(tmp_path):
    return Settings(workspace=tmp_path / "ws", sevenzip="__khong_co_7z__")


class CountingFactory:
    def __init__(self, dim):
        self.dim, self.built, self.encodes = dim, 0, 0

    def __call__(self):
        self.built += 1
        outer = self

        class Enc:
            def encode(self, texts):
                import numpy as np
                outer.encodes += 1
                T = np.zeros((len(texts), outer.dim), np.float32)
                for i in range(len(texts)):
                    T[i, i % outer.dim] = 1.0
                return T
        return Enc()


def make_job(settings, job_id="j1", state="done"):
    fx = make_fixture(n_scenes=20, frames_per_scene=20)
    job = write_job_dir(fx, settings.jobs / job_id)
    (job / "job.json").write_text(json.dumps(
        dict(jobId=job_id, datasetId="d", createdAt="2026-01-01T00:00:00", state=state)))
    (job / "status.json").write_text(json.dumps(
        dict(jobId=job_id, state=state, stage="merge", done=1, total=1)))
    return job, fx


@pytest.fixture
def app_ctx(settings):
    job, fx = make_job(settings)
    factory = CountingFactory(fx.C_img.shape[1])
    app = create_app(settings, runner=lambda *a, **k: {}, encoder_factory=factory)
    return app, factory, job


def test_select_returns_budget_and_preview_with_thumb_urls(app_ctx):
    app, _, _ = app_ctx
    with TestClient(app) as c:
        r = c.post("/jobs/j1/select", json={})
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["budgetB"] == 20 and body["poolSize"] == 400 and len(body["selectionId"]) == 12
    assert len(body["preview"]) == 12
    p0 = body["preview"][0]
    assert p0["thumbUrl"] == f"/api/media/j1/thumbs/{p0['sampleToken']}_{p0['bestCam']}.webp"
    assert {"rank", "sceneName", "frameIdx", "rNov", "rUnc", "rQry", "tags", "camsAvailable",
            "S", "qryBest", "reason"} <= set(p0)
    assert p0["sceneName"]
    assert body["metrics"]["hybrid"]["uplift"] > 1
    assert "coverageGain" in body["metrics"]["hybrid"] and "analysis" not in body


def test_select_params_flow_through(app_ctx):
    app, _, _ = app_ctx
    with TestClient(app) as c:
        r = c.post("/jobs/j1/select", json={
            "budget": 0.08, "preset": "rare_first", "cameras": ["CAM_FRONT"], "maxPerScene": 5})
    body = r.json()
    assert r.status_code == 200 and body["budgetB"] == 32
    assert body["params"]["cameras"] == ["CAM_FRONT"] and body["params"]["m"] == 5


def test_select_on_unfinished_job_is_409(settings):
    make_job(settings, "j2", state="running")
    # create_app xếp lại job `running` còn sót; runner trả về tức thì sẽ làm nó xong trước khi
    # request tới (cuộc đua). Giữ runner chờ tới khi test xong.
    gate = threading.Event()
    app = create_app(settings, runner=lambda *a, **k: gate.wait(5) and {})
    with TestClient(app) as c:
        r = c.post("/jobs/j2/select", json={})
        assert r.status_code == 409 and r.json()["error"]["code"] == "busy"
        assert c.post("/jobs/none/select", json={}).status_code == 404
        gate.set()


def test_select_bad_params_is_400(app_ctx):
    app, _, _ = app_ctx
    with TestClient(app) as c:
        r = c.post("/jobs/j1/select", json={"budget": 0.5})
        assert r.status_code == 400 and r.json()["error"]["code"] == "bad_request"


def test_custom_queries_typed_concurrently_build_encoder_once(app_ctx):
    app, factory, _ = app_ctx
    results, errors = [], []
    barrier = threading.Barrier(2)

    def go(text):
        try:
            with TestClient(app) as c:
                barrier.wait(10)
                results.append(c.post("/jobs/j1/select", json={"queries": [text]}))
        except Exception as e:  # noqa: BLE001
            errors.append(e)

    ts = [threading.Thread(target=go, args=(t,)) for t in ("xe máy dưới mưa", "đám đông")]
    [t.start() for t in ts]
    [t.join(120) for t in ts]
    assert not errors, errors
    assert [r.status_code for r in results] == [200, 200], [r.text for r in results]
    assert results[0].json()["selectionId"] != results[1].json()["selectionId"]
    assert factory.encodes == 2 and factory.built == 1  # hai query khác nhau, MỘT encoder


def test_same_custom_query_twice_gives_same_selection(app_ctx):
    app, factory, _ = app_ctx
    with TestClient(app) as c:
        a = c.post("/jobs/j1/select", json={"queries": ["xe máy"]}).json()
        b = c.post("/jobs/j1/select", json={"queries": ["xe máy"]}).json()
    assert a["selectionId"] == b["selectionId"] and factory.built == 1


def test_load_selection_rejects_path_tricks(settings, app_ctx):
    from service.errors import ApiError
    from service.selection import load_selection
    _, _, job = app_ctx
    (job / "out").mkdir(exist_ok=True)
    (job / "out" / "result.json").write_text("{}")  # bia: .. từ selections/ trỏ tới đây
    with pytest.raises(ApiError) as e:
        load_selection(settings, "j1", "..")
    assert e.value.status == 404


def test_default_queries_never_build_encoder(app_ctx):
    app, factory, _ = app_ctx
    with TestClient(app) as c:
        assert c.post("/jobs/j1/select", json={}).status_code == 200
    assert factory.built == 0


def test_get_stored_selection_and_bad_ids(app_ctx):
    app, _, _ = app_ctx
    with TestClient(app) as c:
        posted = c.post("/jobs/j1/select", json={}).json()
        got = c.get(f"/jobs/j1/selections/{posted['selectionId']}")
        assert got.status_code == 200 and got.json() == posted
        assert c.get("/jobs/j1/selections/000000000000").status_code == 404
        assert c.get("/jobs/j1/selections/..%2F..%2Fjob.json").status_code == 404
        assert c.get("/jobs/zzz/selections/000000000000").status_code == 404
