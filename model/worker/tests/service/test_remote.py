"""WP2: hàng đợi Tầng 1 từ xa (SPEC-P02 §7), TestClient, không GPU."""
import io
import json
import tarfile
from datetime import datetime, timedelta

import numpy as np
import pandas as pd
import pytest
from fastapi.testclient import TestClient

from c4.lidar.web_selection import available_tiers
from service.main import create_app
from service.settings import Settings

TOKEN = "s3cret-token"
AUTH = {"Authorization": f"Bearer {TOKEN}"}
JOB = "aaaaaaaaaaaa"
TOKENS = [f"tok{i}" for i in range(5)]


def _signals(tokens) -> bytes:
    df = pd.DataFrame(dict(sample_token=list(tokens), ent=np.zeros(len(tokens), "float32"),
                           inc=np.zeros(len(tokens), "float32"),
                           n_det=np.zeros(len(tokens), "int32"),
                           nov=np.zeros(len(tokens), "float32")))
    buf = io.BytesIO()
    df.to_parquet(buf, index=False)
    return buf.getvalue()


@pytest.fixture
def env(tmp_path):
    s = Settings(workspace=tmp_path / "ws", remote_token=TOKEN)
    job = s.jobs / JOB
    (job / "lidar").mkdir(parents=True)
    (job / "job.json").write_text(json.dumps(dict(jobId=JOB, datasetId="d1", state="done")))
    pd.DataFrame(dict(sample_token=TOKENS, split=["S", "P", "P", "P", "T"])).to_parquet(
        job / "lidar" / "index.parquet")
    (s.datasets / "d1" / "data" / "samples").mkdir(parents=True)
    (s.datasets / "d1" / "data" / "v1.0-mini").mkdir(parents=True)
    (s.datasets / "d1" / "data" / "v1.0-mini" / "sample_annotation.json").write_text(
        json.dumps([dict(token=f"a{i}", sample_token=t) for i, t in enumerate(TOKENS)]))
    (s.datasets / "d1" / "data" / "samples" / "x.bin").write_bytes(b"1234567")
    app = create_app(s)
    with TestClient(app) as c:
        yield c, s, app


def _create(c, **body):
    return c.post(f"/jobs/{JOB}/t1-remote", json=body)


def test_1_token(env):
    c, s, app = env
    assert c.get("/remote/t1/next").status_code == 401
    assert c.get("/remote/t1/next", headers={"Authorization": "Bearer sai"}).status_code == 401
    assert c.get("/remote/t1/next", headers=AUTH).status_code == 204
    app.state.settings.remote_token = ""  # tắt
    r = c.get("/remote/t1/next", headers=AUTH)
    assert r.status_code == 404 and r.json()["error"]["code"] == "remote_disabled"
    assert _create(c).status_code == 404


def test_2_lifecycle(env):
    c, s, _ = env
    r = _create(c, epochs=5)
    assert r.status_code == 201, r.text
    task = r.json()
    assert task["state"] == "queued" and task["params"] == {"epochs": 5, "sweeps": 1, "batch": 4}
    assert "bundleSha256" not in task
    t = c.get("/remote/t1/next", headers=AUTH).json()
    assert t["taskId"] == task["taskId"] and t["state"] == "leased" and t["attempts"] == 1
    hb = c.post(f"/remote/t1/{t['taskId']}/heartbeat", headers=AUTH,
                json={"stage": "train", "progress": 0.5})
    assert hb.status_code == 200, hb.text
    assert available_tiers(s.jobs / JOB) == [0]
    r = c.post(f"/remote/t1/{t['taskId']}/result", headers=AUTH,
               files={"signals": ("signals.parquet", _signals(TOKENS))},
               data={"meta": json.dumps({"trainSec": 1.0, "inferSec": 2.0, "gpu": "T4"})})
    assert r.status_code == 200, r.text
    assert r.json()["state"] == "done"
    assert available_tiers(s.jobs / JOB) == [0, 1]
    assert json.loads((s.jobs / JOB / "t1" / "remote_meta.json").read_text())["gpu"] == "T4"
    assert c.get(f"/jobs/{JOB}/t1-remote").json()["state"] == "done"


def test_3_result_missing_tokens(env):
    c, s, _ = env
    _create(c)
    t = c.get("/remote/t1/next", headers=AUTH).json()
    r = c.post(f"/remote/t1/{t['taskId']}/result", headers=AUTH,
               files={"signals": ("s.parquet", _signals(TOKENS[:2]))})
    assert r.status_code == 422 and r.json()["error"]["code"] == "bad_signals"
    assert not (s.jobs / JOB / "t1" / "signals.parquet").exists()
    assert c.get(f"/jobs/{JOB}/t1-remote").json()["state"] == "leased"


def test_4_lease_expiry(env):
    c, s, app = env
    _create(c)
    t1 = c.get("/remote/t1/next", headers=AUTH).json()
    app.state.remote.clock = lambda: datetime.now() + timedelta(seconds=s.remote_lease_sec + 60)
    t2 = c.get("/remote/t1/next", headers=AUTH).json()
    assert t2["taskId"] == t1["taskId"] and t2["attempts"] == 2


def test_5_fail_three_times(env):
    c, _, _ = env
    _create(c)
    states = []
    for _ in range(3):
        t = c.get("/remote/t1/next", headers=AUTH).json()
        r = c.post(f"/remote/t1/{t['taskId']}/fail", headers=AUTH, json={"error": "boom"})
        states.append(r.json()["state"])
    assert states == ["queued", "queued", "failed"]
    assert c.get("/remote/t1/next", headers=AUTH).status_code == 204


def test_6_bad_task_id(env):
    c, _, _ = env
    r = c.get("/remote/t1/..%2F..%2Fx/bundle", headers=AUTH)
    assert r.status_code in (404, 422)
    assert c.post("/remote/t1/t1_zzzzzzzzzzzz/fail", headers=AUTH,
                  json={"error": "x"}).status_code == 404


def test_8_task_exists_and_not_ready_and_cancel(env):
    c, s, app = env
    a = _create(c).json()
    r = _create(c)
    assert r.status_code == 409
    assert r.json()["error"]["code"] == "task_exists" and r.json()["error"]["taskId"] == a["taskId"]
    d = c.delete(f"/jobs/{JOB}/t1-remote")
    assert d.status_code == 200 and d.json()["state"] == "cancelled"
    assert c.delete(f"/jobs/{JOB}/t1-remote").status_code == 409
    assert c.post(f"/jobs/{JOB}/t1-remote", json={"epochs": 999}).status_code == 422
    # job chưa có index
    (s.jobs / "bbbbbbbbbbbb").mkdir()
    (s.jobs / "bbbbbbbbbbbb" / "job.json").write_text("{}")
    r = c.post("/jobs/bbbbbbbbbbbb/t1-remote", json={})
    assert r.status_code == 409 and r.json()["error"]["code"] == "job_not_ready"
    assert c.post("/jobs/cccccccccccc/t1-remote", json={}).status_code == 404
    # cancel không ném lỗi khi không có task
    assert app.state.remote.cancel("cccccccccccc") is None


def test_9_bundle(env):
    c, s, _ = env
    _create(c)
    t = c.get("/remote/t1/next", headers=AUTH).json()
    r = c.get(f"/remote/t1/{t['taskId']}/bundle", headers=AUTH)
    assert r.status_code == 200 and r.headers["content-type"] == "application/x-tar"
    with tarfile.open(fileobj=io.BytesIO(r.content)) as tf:
        names = tf.getnames()
        assert "index.parquet" in names and "data/samples/x.bin" in names
        assert tf.extractfile("data/samples/x.bin").read() == b"1234567"
        # nhãn của pool (P) không rời máy: chỉ còn nhãn S và T
        ann = json.loads(tf.extractfile("data/v1.0-mini/sample_annotation.json").read())
        assert sorted(a["sample_token"] for a in ann) == ["tok0", "tok4"]
    # chưa lease thì 409
    other = c.post(f"/remote/t1/{t['taskId']}/fail", headers=AUTH, json={"error": "x"}).json()
    assert other["state"] == "queued"
    assert c.get(f"/remote/t1/{t['taskId']}/bundle", headers=AUTH).status_code == 409
