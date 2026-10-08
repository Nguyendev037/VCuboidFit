import json
import threading

import pytest
from fastapi.testclient import TestClient

from service.main import create_app
from service.settings import Settings

DONE, FAIL, RUN = "aaaaaaaaaaaa", "bbbbbbbbbbbb", "cccccccccccc"


def put(path, obj):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(obj), encoding="utf-8")


def fake_job(s, jid, created, state):
    put(s.jobs / jid / "job.json", dict(jobId=jid, datasetId="dsA", pipeline="lidar",
                                        createdAt=created, state=state))
    (s.jobs / jid / "out").mkdir(exist_ok=True)
    (s.jobs / jid / "out" / "x.bin").write_bytes(b"x")
    if state in ("done", "failed"):
        put(s.jobs / jid / "status.json", dict(jobId=jid, state=state, stage="merge",
                                               done=1, total=1))


@pytest.fixture
def settings(tmp_path):
    return Settings(workspace=tmp_path / "ws", sevenzip="__khong_co_7z__")


@pytest.fixture
def client(settings):
    put(settings.datasets / "dsA" / "report.json", dict(datasetId="dsA", ok=True))
    (settings.datasets / "dsA" / "data").mkdir(exist_ok=True)
    (settings.datasets / "dsA" / "data" / "keep.txt").write_text("k")
    fake_job(settings, DONE, "2026-01-01T00:00:00", "done")
    fake_job(settings, FAIL, "2026-01-02T00:00:00", "failed")
    fake_job(settings, RUN, "2026-01-03T00:00:00", "running")
    started, release = threading.Event(), threading.Event()

    def blocking_runner(*a, **k):
        started.set()
        release.wait(10)
        return {"state": "cancelled"}

    app = create_app(settings, runner=blocking_runner)
    with TestClient(app) as c:
        assert started.wait(10)  # recover() đã đưa job `running` vào runner và nó đang giữ
        yield c
        release.set()


def ids(c):
    return {i["jobId"] for i in c.get("/jobs").json()["items"]}


def test_delete_done_job_removes_dir_and_listing(client, settings):
    r = client.delete(f"/jobs/{DONE}")
    assert r.status_code == 200 and r.json() == {"deleted": [DONE]}
    assert not (settings.jobs / DONE).exists()
    assert DONE not in ids(client)


def test_delete_active_job_is_409_and_dir_kept(client, settings):
    r = client.delete(f"/jobs/{RUN}")
    assert r.status_code == 409 and r.json()["error"]["code"] == "job_active"
    assert (settings.jobs / RUN / "job.json").exists()


def test_delete_all_skips_active(client, settings):
    r = client.delete("/jobs")
    assert r.status_code == 200
    body = r.json()
    assert sorted(body["deleted"]) == sorted([DONE, FAIL])
    assert body["skipped"] == [{"jobId": RUN, "reason": "active"}]
    assert ids(client) == {RUN}


def test_bad_id_and_missing_are_404(client, settings):
    assert client.delete("/jobs/..").status_code in (404, 422)
    assert client.delete("/jobs/not-a-hex-id").status_code == 404
    assert client.delete("/jobs/dddddddddddd").status_code == 404
    assert settings.jobs.exists()


def test_datasets_untouched(client, settings):
    client.delete(f"/jobs/{DONE}")
    client.delete("/jobs")
    assert (settings.datasets / "dsA" / "report.json").exists()
    assert (settings.datasets / "dsA" / "data" / "keep.txt").exists()
