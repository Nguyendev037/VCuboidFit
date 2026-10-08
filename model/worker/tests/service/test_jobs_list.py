import json
import os

import pytest
from fastapi.testclient import TestClient

from service.main import create_app
from service.settings import Settings


@pytest.fixture
def settings(tmp_path):
    return Settings(workspace=tmp_path / "ws", sevenzip="__khong_co_7z__")


def put(path, obj):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(obj), encoding="utf-8")


def fake_job(s, jid, created, state="done", ds="dsA", pipeline="lidar"):
    put(s.jobs / jid / "job.json", dict(jobId=jid, datasetId=ds, pipeline=pipeline,
                                        createdAt=created, state=state))
    if state in ("done", "failed"):
        put(s.jobs / jid / "status.json", dict(jobId=jid, state=state, stage="merge",
                                               done=1, total=1))


def fake_sel(s, jid, sid, mtime, params=None):
    f = s.jobs / jid / "out" / "selections" / sid / "result.json"
    put(f, dict(selectionId=sid, params=params or {"budget": 0.05}))
    os.utime(f, (mtime, mtime))


@pytest.fixture
def client(settings):
    put(settings.datasets / "dsA" / "report.json",
        dict(datasetId="dsA", ok=True, scenes=3, frames=120, version="v1.0-mini"))
    fake_job(settings, "job_old", "2026-01-01T00:00:00")
    fake_job(settings, "job_new", "2026-02-01T00:00:00", pipeline="camera")
    fake_job(settings, "job_run", "2026-03-01T00:00:00", state="running")
    fake_sel(settings, "job_new", "aaaaaaaaaaaa", 1_700_000_000)
    fake_sel(settings, "job_new", "bbbbbbbbbbbb", 1_700_000_500, {"budget": 0.1})
    fake_sel(settings, "job_new", "../evil", 1_700_009_999)
    app = create_app(settings, runner=lambda *a, **k: {})
    with TestClient(app) as c:
        yield c


def test_jobs_listed_newest_first_with_dataset_fields(client):
    r = client.get("/jobs")
    assert r.status_code == 200
    items = r.json()["items"]
    assert [i["jobId"] for i in items] == ["job_run", "job_new", "job_old"]
    new = items[1]
    assert new["datasetId"] == "dsA" and new["pipeline"] == "camera" and new["state"] == "done"
    assert new["scenes"] == 3 and new["frames"] == 120 and new["version"] == "v1.0-mini"
    assert new["lastSelectionId"] == "bbbbbbbbbbbb" and new["finishedAt"]
    assert items[0]["finishedAt"] is None and items[0]["lastSelectionId"] is None
    assert items[2]["lastSelectionId"] is None


def test_jobs_capped_at_50(settings):
    for i in range(55):
        fake_job(settings, f"j{i:02d}", f"2026-01-01T00:{i // 60:02d}:{i % 60:02d}")
    with TestClient(create_app(settings, runner=lambda *a, **k: {})) as c:
        items = c.get("/jobs").json()["items"]
    assert len(items) == 50 and items[0]["jobId"] == "j54"


def test_selections_listed_newest_first_and_404(client):
    r = client.get("/jobs/job_new/selections")
    assert r.status_code == 200
    items = r.json()["items"]
    assert [i["selectionId"] for i in items] == ["bbbbbbbbbbbb", "aaaaaaaaaaaa"]
    assert items[0]["params"] == {"budget": 0.1} and items[0]["createdAt"]
    assert client.get("/jobs/job_old/selections").json() == {"items": []}
    assert client.get("/jobs/zzz/selections").status_code == 404
