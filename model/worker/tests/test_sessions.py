import json
import os
import time
from datetime import datetime, timezone

import pytest
from fastapi.testclient import TestClient

from service.main import create_app
from service.sessions import delete_session, expired, purge_orphans
from service.settings import Settings

SID_A = "a" * 32
SID_B = "b" * 32


def _write(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value), encoding="utf-8")


@pytest.fixture
def app(tmp_path):
    settings = Settings(workspace=tmp_path / "workspace", sessions=True, session_ttl_h=24)
    for directory in (settings.uploads, settings.datasets, settings.jobs, settings.remote):
        directory.mkdir(parents=True)
    return create_app(settings, runner=lambda *_args, **_kwargs: {"state": "done"})


def _job(settings, job_id, sid, state="done"):
    _write(settings.jobs / job_id / "job.json", {
        "jobId": job_id, "datasetId": "dataset-" + job_id,
        "state": state, "sessionId": sid,
    })


def test_sessions_disabled_keeps_legacy_job_listing(tmp_path):
    settings = Settings(workspace=tmp_path / "workspace", sessions=False)
    _job(settings, "legacy", SID_A)
    with TestClient(create_app(settings, runner=lambda *_a, **_k: {"state": "done"})) as client:
        assert client.get("/jobs").status_code == 200
        assert client.get("/jobs").json()["items"][0]["jobId"] == "legacy"


def test_jobs_are_isolated_between_sessions(app):
    settings = app.state.settings
    _job(settings, "job-a", SID_A)
    _job(settings, "job-b", SID_B)
    with TestClient(app) as client:
        headers_a = {"X-VCF-Session": SID_A}
        headers_b = {"X-VCF-Session": SID_B}
        assert [x["jobId"] for x in client.get("/jobs", headers=headers_a).json()["items"]] == ["job-a"]
        assert client.get("/jobs/job-a", headers=headers_b).status_code == 404
        assert client.get("/jobs/job-a", headers=headers_a).status_code == 200


def test_delete_current_removes_only_session_resources_and_remote_task(app):
    settings = app.state.settings
    _write(settings.workspace / "sessions" / f"{SID_A}.json", {
        "sessionId": SID_A, "createdAt": "2026-01-01T00:00:00+00:00",
        "lastSeen": "2026-01-01T00:00:00+00:00",
    })
    _write(settings.uploads / "upload-a" / "session.json", {"sessionId": SID_A})
    _write(settings.datasets / "dataset-a" / "report.json", {"sessionId": SID_A})
    _job(settings, "job-a", SID_A)
    _job(settings, "job-b", SID_B)
    _write(settings.remote / "t1_a.json", {"taskId": "t1_a", "sessionId": SID_A})
    _write(settings.remote / "t1_b.json", {"taskId": "t1_b", "sessionId": SID_B})
    with TestClient(app) as client:
        response = client.delete("/sessions/current", headers={"X-VCF-Session": SID_A})
    assert response.status_code == 200
    assert not (settings.uploads / "upload-a").exists()
    assert not (settings.datasets / "dataset-a").exists()
    assert not (settings.jobs / "job-a").exists()
    assert (settings.jobs / "job-b").exists()
    assert not (settings.remote / "t1_a.json").exists()
    assert (settings.remote / "t1_b.json").exists()


def test_delete_session_cancels_running_job_before_delete(tmp_path):
    settings = Settings(workspace=tmp_path / "workspace", sessions=True)
    _job(settings, "job-a", SID_A, state="running")

    class Queue:
        def __init__(self):
            self.cancelled = []
            self.deleted = []

        def cancel(self, job_id):
            self.cancelled.append(job_id)
            _write(settings.jobs / job_id / "job.json", {
                "jobId": job_id, "state": "cancelled", "sessionId": SID_A,
            })

        def delete(self, job_id):
            self.deleted.append(job_id)
            (settings.jobs / job_id / "job.json").unlink()
            (settings.jobs / job_id).rmdir()

    queue = Queue()
    result = delete_session(settings, queue, SID_A)
    assert result["jobs"] == 1
    assert queue.cancelled == ["job-a"] and queue.deleted == ["job-a"]


def test_expired_sessions_and_orphans_are_purged(tmp_path):
    settings = Settings(workspace=tmp_path / "workspace", sessions=True, session_ttl_h=1)
    old = time.time() - 7200
    _write(settings.workspace / "sessions" / f"{SID_A}.json", {
        "sessionId": SID_A, "lastSeen": datetime.fromtimestamp(old, timezone.utc).isoformat(),
    })
    (settings.uploads / "old").mkdir(parents=True)
    os.utime(settings.uploads / "old", (old, old))
    assert expired(settings, time.time()) == [SID_A]
    assert purge_orphans(settings, time.time())["orphans"] == 1


def test_sweep_entrypoint_is_idempotent(tmp_path, monkeypatch, capsys):
    from service import sweep

    settings = Settings(workspace=tmp_path / "workspace", sessions=True)
    for directory in (settings.uploads, settings.datasets, settings.jobs, settings.remote,
                      settings.workspace / "sessions"):
        directory.mkdir(parents=True)
    monkeypatch.setattr(sweep, "Settings", lambda: settings)
    assert sweep.main() == 0
    assert sweep.main() == 0
    assert json.loads(capsys.readouterr().out.splitlines()[-1])["sessions"] == 0


def test_cleanup_does_not_follow_symlink(tmp_path):
    settings = Settings(workspace=tmp_path / "workspace", sessions=True, session_ttl_h=1)
    settings.uploads.mkdir(parents=True)
    outside = tmp_path / "outside"
    outside.mkdir()
    link = settings.uploads / "link"
    try:
        link.symlink_to(outside, target_is_directory=True)
    except OSError as exc:
        pytest.fail(f"symlink test requires link support: {exc}")
    purge_orphans(settings, time.time() + 7200)
    assert outside.exists()


def test_invalid_session_header_is_treated_as_missing(app):
    _job(app.state.settings, "job-a", SID_A)
    with TestClient(app) as client:
        response = client.get("/jobs", headers={"X-VCF-Session": "not-a-session"})
    assert response.status_code == 200
    assert response.json()["items"] == []


def test_health_reports_remote_agent_and_session_task_cleanup(app):
    settings = app.state.settings
    settings.remote_token = "remote-test-token"
    with TestClient(app) as client:
        response = client.get("/health", headers={"X-VCF-Session": SID_A})
        assert response.json()["remoteAgent"]["lastSeen"] is None
        assert client.get("/remote/t1/next", headers={"Authorization": "Bearer remote-test-token"}).status_code == 204
        assert client.get("/health").json()["remoteAgent"]["lastSeen"] is not None
        _write(settings.remote / "t1_a.json", {"taskId": "t1_a", "sessionId": SID_A})
        assert client.delete("/sessions/current", headers={"X-VCF-Session": SID_A}).status_code == 200
    assert not (settings.remote / "t1_a.json").exists()
