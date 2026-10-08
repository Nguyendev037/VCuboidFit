import json
import threading
import time
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from service.datasets import _save, validate_dataset
from service.jobs import JobQueue
from service.main import create_app
from service.settings import Settings
from tests.fixtures.make_nuscenes import make_nuscenes


@pytest.fixture
def settings(tmp_path):
    return Settings(workspace=tmp_path / "ws", sevenzip="__khong_co_7z__")


def make_dataset(settings, ds_id="dsA", ok=True, **kw):
    data = make_nuscenes(settings.datasets / ds_id, **kw)
    rep = validate_dataset(data, ds_id)
    if not ok:
        rep.ok = False
        rep.errors = ["Dữ liệu hỏng"]
    _save(settings, rep)
    return ds_id


def wait_state(q, job_id, states, timeout=60.0):
    t0 = time.monotonic()
    while time.monotonic() - t0 < timeout:
        st = q.status(job_id)
        if st.state in states:
            return st
        time.sleep(0.05)
    raise AssertionError(f"timeout, state={q.status(job_id).state}")


def fake_runner(order=None, delay=0.0):
    def run(job_dir, data_root, profile, cancel=None, env=None):
        job = Path(job_dir)
        if order is not None:
            order.append(job.name)
        end = time.monotonic() + delay
        while time.monotonic() < end:
            if cancel is not None and cancel.is_set():
                st = dict(jobId=job.name, state="cancelled", stage="index", done=0, total=1)
                (job / "status.json").write_text(json.dumps(st))
                return st
            time.sleep(0.02)
        st = dict(jobId=job.name, state="done", stage="merge", done=1, total=1, stages=[])
        (job / "status.json").write_text(json.dumps(st))
        return st
    return run


# ---------- JobQueue với runner giả (nhanh) ----------

def test_submit_writes_job_json_and_runs_to_done(settings):
    ds = make_dataset(settings)
    q = JobQueue(settings, runner=fake_runner())
    jid = q.submit(ds)
    meta = json.loads((settings.jobs / jid / "job.json").read_text(encoding="utf-8"))
    assert meta["jobId"] == jid and meta["datasetId"] == ds and meta["state"] == "queued"
    assert q.status(jid).state == "queued"
    q.start()
    try:
        assert wait_state(q, jid, {"done"}).state == "done"
        assert json.loads((settings.jobs / jid / "job.json").read_text())["state"] == "done"
    finally:
        q.stop()


def test_two_submits_run_one_after_the_other(settings):
    ds = make_dataset(settings)
    order, active, peak = [], [0], [0]
    base = fake_runner(order, delay=0.2)

    def run(*a, **k):
        active[0] += 1
        peak[0] = max(peak[0], active[0])
        try:
            return base(*a, **k)
        finally:
            active[0] -= 1

    q = JobQueue(settings, runner=run)
    j1, j2 = q.submit(ds), q.submit(ds)
    q.start()
    try:
        wait_state(q, j2, {"done"})
    finally:
        q.stop()
    assert order == [j1, j2] and peak[0] == 1


def test_cancel_queued_job(settings):
    ds = make_dataset(settings)
    q = JobQueue(settings, runner=fake_runner())  # chưa start ⇒ job đứng yên ở queued
    jid = q.submit(ds)
    assert q.cancel(jid).state == "cancelled"
    q.start()
    try:
        time.sleep(0.3)
        assert q.status(jid).state == "cancelled"
    finally:
        q.stop()


def test_cancel_running_job(settings):
    ds = make_dataset(settings)
    started = threading.Event()
    inner = fake_runner(delay=30)

    def run(job_dir, data_root, profile, cancel=None, env=None):
        started.set()
        return inner(job_dir, data_root, profile, cancel, env)

    q = JobQueue(settings, runner=run)
    jid = q.submit(ds)
    q.start()
    try:
        assert started.wait(10)
        q.cancel(jid)
        assert wait_state(q, jid, {"cancelled"}, timeout=10).state == "cancelled"
    finally:
        q.stop()


def test_failed_job_keeps_error_code(settings):
    ds = make_dataset(settings)

    def run(job_dir, *a, **k):
        st = dict(jobId=Path(job_dir).name, state="failed", stage="det", done=0, total=1,
                  error=dict(code=3, message="Hết VRAM ở stage det"))
        (Path(job_dir) / "status.json").write_text(json.dumps(st))
        return st

    q = JobQueue(settings, runner=run)
    jid = q.submit(ds)
    q.start()
    try:
        st = wait_state(q, jid, {"failed"})
    finally:
        q.stop()
    assert st.error.code == 3 and "VRAM" in st.error.message


def test_runner_exception_marks_failed(settings):
    ds = make_dataset(settings)

    def run(*a, **k):
        raise RuntimeError("boom")

    q = JobQueue(settings, runner=run)
    jid = q.submit(ds)
    q.start()
    try:
        st = wait_state(q, jid, {"failed"})
    finally:
        q.stop()
    assert st.error is not None and "boom" in st.error.message


def test_recover_requeues_running_job_after_restart(settings):
    ds = make_dataset(settings)
    q1 = JobQueue(settings, runner=fake_runner())
    jid = q1.submit(ds)
    meta = settings.jobs / jid / "job.json"
    d = json.loads(meta.read_text())
    d["state"] = "running"  # worker chết giữa chừng
    meta.write_text(json.dumps(d))
    done_before = settings.jobs / "old"
    done_before.mkdir()
    (done_before / "job.json").write_text(json.dumps(
        dict(jobId="old", datasetId=ds, createdAt="2020-01-01T00:00:00", state="done")))
    order = []
    q2 = JobQueue(settings, runner=fake_runner(order))
    q2.recover()
    q2.start()
    try:
        assert wait_state(q2, jid, {"done"}).state == "done"
    finally:
        q2.stop()
    assert order == [jid]  # job "old" đã done không chạy lại


def test_recover_orders_by_created_at(settings):
    ds = make_dataset(settings)
    for jid, ts in [("b", "2026-01-02T00:00:00"), ("a", "2026-01-01T00:00:00")]:
        d = settings.jobs / jid
        d.mkdir(parents=True)
        (d / "job.json").write_text(json.dumps(
            dict(jobId=jid, datasetId=ds, createdAt=ts, state="queued")))
    order = []
    q = JobQueue(settings, runner=fake_runner(order))
    q.recover()
    q.start()
    try:
        wait_state(q, "b", {"done"})
    finally:
        q.stop()
    assert order == ["a", "b"]


# ---------- routes ----------

def test_routes_submit_poll_cancel(settings):
    ds = make_dataset(settings)
    app = create_app(settings, runner=fake_runner(delay=0.1))
    with TestClient(app) as c:
        jid = c.post("/jobs", json={"datasetId": ds, "pipeline": "camera"}).json()["jobId"]
        t0 = time.monotonic()
        while c.get(f"/jobs/{jid}").json()["state"] != "done":
            assert time.monotonic() - t0 < 30
            time.sleep(0.05)
        body = c.get(f"/jobs/{jid}").json()
        assert body["jobId"] == jid and body["stage"] == "merge"
        assert c.post(f"/jobs/{jid}/cancel").json()["state"] == "done"  # job xong: giữ nguyên


def test_post_jobs_pipeline_defaults_to_lidar_when_dataset_has_lidar(settings):
    ds = make_dataset(settings)  # make_nuscenes có LIDAR_TOP
    with TestClient(create_app(settings, runner=fake_runner(delay=0.05))) as c:
        jid = c.post("/jobs", json={"datasetId": ds}).json()["jobId"]
        assert c.get(f"/jobs/{jid}").json()["pipeline"] == "lidar"
        assert json.loads((settings.jobs / jid / "job.json").read_text())["pipeline"] == "lidar"
        jid2 = c.post("/jobs", json={"datasetId": ds, "pipeline": "camera"}).json()["jobId"]
        assert c.get(f"/jobs/{jid2}").json()["pipeline"] == "camera"


def test_post_jobs_pipeline_defaults_to_camera_without_lidar(settings):
    ds = make_dataset(settings, "nol", with_lidar=False)
    with TestClient(create_app(settings, runner=fake_runner(delay=0.05))) as c:
        jid = c.post("/jobs", json={"datasetId": ds}).json()["jobId"]
        assert c.get(f"/jobs/{jid}").json()["pipeline"] == "camera"


def test_route_invalid_dataset_is_400(settings):
    bad = make_dataset(settings, "bad", ok=False)
    with TestClient(create_app(settings, runner=fake_runner())) as c:
        r = c.post("/jobs", json={"datasetId": bad})
        assert r.status_code == 400 and r.json()["error"]["code"] == "dataset_invalid"
        assert "Dữ liệu hỏng" in r.json()["error"]["message"]
        r = c.post("/jobs", json={"datasetId": "khong-co"})
        assert r.status_code == 404 and r.json()["error"]["code"] == "not_found"
        assert c.get("/jobs/zzz").status_code == 404


# ---------- tích hợp: run_job thật, model giả ----------

def test_real_run_job_with_fake_models(settings, monkeypatch):
    monkeypatch.setenv("C4_FAKE_MODELS", "1")
    ds = make_dataset(settings, n_scenes=1, frames_per_scene=3)
    q = JobQueue(settings)
    jid = q.submit(ds)
    q.start()
    try:
        st = wait_state(q, jid, {"done", "failed"}, timeout=240)
    finally:
        q.stop()
    assert st.state == "done", st.error
    assert (settings.jobs / jid / "cache" / "features_cache.parquet").is_file()
