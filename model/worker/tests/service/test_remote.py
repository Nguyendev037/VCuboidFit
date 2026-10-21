"""WP2: hàng đợi Tầng 1 từ xa (SPEC-P02 §7), TestClient, không GPU."""
import io
import json
import sys
import tarfile
from datetime import datetime, timedelta

import numpy as np
import pandas as pd
import pytest
from fastapi.testclient import TestClient

from c4.lidar.pipeline import tier_available
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
    pd.DataFrame(dict(sample_token=TOKENS)).to_parquet(job / "lidar" / "index.parquet")
    (s.datasets / "d1" / "data" / "samples").mkdir(parents=True)
    (s.datasets / "d1" / "data" / "samples" / "x.bin").write_bytes(b"1234567")
    app = create_app(s)
    with TestClient(app) as c:
        yield c, s, app


def _lease(t) -> dict:
    return {**AUTH, "X-Lease-Id": t["leaseId"]}


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
    hb = c.post(f"/remote/t1/{t['taskId']}/heartbeat", headers=_lease(t),
                json={"stage": "train", "progress": 0.5})
    assert hb.status_code == 200, hb.text
    assert tier_available(s.jobs / JOB) == [0]
    r = c.post(f"/remote/t1/{t['taskId']}/result", headers=_lease(t),
               files={"signals": ("signals.parquet", _signals(TOKENS))},
               data={"meta": json.dumps({"trainSec": 1.0, "inferSec": 2.0, "gpu": "T4"})})
    assert r.status_code == 200, r.text
    assert r.json()["state"] == "done"
    assert tier_available(s.jobs / JOB) == [0, 1]
    assert json.loads((s.jobs / JOB / "t1" / "remote_meta.json").read_text())["gpu"] == "T4"
    assert c.get(f"/jobs/{JOB}/t1-remote").json()["state"] == "done"


def test_3_result_missing_tokens(env):
    c, s, _ = env
    _create(c)
    t = c.get("/remote/t1/next", headers=AUTH).json()
    r = c.post(f"/remote/t1/{t['taskId']}/result", headers=_lease(t),
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
        r = c.post(f"/remote/t1/{t['taskId']}/fail", headers=_lease(t), json={"error": "boom"})
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
    # chưa lease thì 409
    other = c.post(f"/remote/t1/{t['taskId']}/fail", headers=_lease(t), json={"error": "x"}).json()
    assert other["state"] == "queued"
    assert c.get(f"/remote/t1/{t['taskId']}/bundle", headers=AUTH).status_code == 409


def test_10_upload_rejected_before_body_parse(env, monkeypatch):
    """Token + Content-Length kiểm TRƯỚC khi parse/spool multipart."""
    from starlette.requests import Request
    c, s, _ = env
    _create(c)
    t = c.get("/remote/t1/next", headers=AUTH).json()
    url = f"/remote/t1/{t['taskId']}/result"

    async def boom(self, *a, **k):
        raise AssertionError("body đã bị parse trước khi kiểm token/giới hạn")
    monkeypatch.setattr(Request, "form", boom)
    monkeypatch.setattr(Request, "stream", boom)
    big = {"Content-Length": str((s.remote_max_result_mb + 10) * 1024 * 1024),
           "Content-Type": "multipart/form-data; boundary=x"}
    # không token: 401 dù khai báo body khổng lồ
    r = c.post(url, headers=big, content=b"x")
    assert r.status_code == 401, r.text
    # có token + vượt giới hạn: 413 too_large
    r = c.post(url, headers={**_lease(t), **big}, content=b"x")
    assert r.status_code == 413 and r.json()["error"]["code"] == "too_large"
    # thiếu Content-Length (chunked): 411
    r = c.post(url, headers={**_lease(t), "Content-Type": "multipart/form-data; boundary=x"},
               content=iter([b"abc", b"def"]))
    assert r.status_code == 411 and r.json()["error"]["code"] == "length_required"
    # JSON route cũng bị chặn body lớn
    r = c.post(f"/remote/t1/{t['taskId']}/fail",
               headers={**_lease(t), "Content-Length": str(10_000_000),
                        "Content-Type": "application/json"}, content=b"{}")
    assert r.status_code == 413


def test_11_lease_id_isolates_attempts(env):
    c, s, app = env
    _create(c)
    old = c.get("/remote/t1/next", headers=AUTH).json()
    assert old["leaseId"]
    tid = old["taskId"]
    hb = {"stage": "train", "progress": 0.1}
    # thiếu / sai lease: 409 lease_mismatch
    for h in (AUTH, {**AUTH, "X-Lease-Id": "sai"}):
        r = c.post(f"/remote/t1/{tid}/heartbeat", headers=h, json=hb)
        assert r.status_code == 409 and r.json()["error"]["code"] == "lease_mismatch"
    app.state.remote.clock = lambda: datetime.now() + timedelta(seconds=s.remote_lease_sec + 60)
    new = c.get("/remote/t1/next", headers=AUTH).json()
    assert new["taskId"] == tid and new["leaseId"] != old["leaseId"]
    assert c.get(f"/jobs/{JOB}/t1-remote").json().get("leaseId") is None  # không lộ ra web
    # lease cũ không gia hạn / fail / nộp kết quả được lượt mới
    assert c.post(f"/remote/t1/{tid}/heartbeat", headers=_lease(old), json=hb).status_code == 409
    r = c.post(f"/remote/t1/{tid}/fail", headers=_lease(old), json={"error": "x"})
    assert r.status_code == 409 and r.json()["error"]["code"] == "lease_mismatch"
    r = c.post(f"/remote/t1/{tid}/result", headers=_lease(old),
               files={"signals": ("s.parquet", _signals(TOKENS))})
    assert r.status_code == 409 and r.json()["error"]["code"] == "lease_mismatch"
    assert c.get(f"/jobs/{JOB}/t1-remote").json()["state"] == "leased"
    # lease mới vẫn dùng được
    assert c.post(f"/remote/t1/{tid}/heartbeat", headers=_lease(new), json=hb).status_code == 200
    r = c.post(f"/remote/t1/{tid}/result", headers=_lease(new),
               files={"signals": ("s.parquet", _signals(TOKENS))})
    assert r.status_code == 200 and r.json()["state"] == "done"


def _load_agent():
    import importlib.util
    import sys
    import types
    from pathlib import Path
    try:
        import requests  # noqa: F401
    except ImportError:  # venv worker không cài requests (chỉ Colab cần): giả tối thiểu
        fake = types.ModuleType("requests")
        fake.ConnectionError = type("ConnectionError", (OSError,), {})
        fake.Timeout = type("Timeout", (OSError,), {})
        fake.Response = object
        fake.Session = type("Session", (), {"__init__": lambda self: setattr(self, "headers", {})})
        sys.modules["requests"] = fake
    p = Path(__file__).resolve().parents[3] / "scripts" / "colab_agent.py"
    spec = importlib.util.spec_from_file_location("colab_agent_t", p)
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


def test_13_result_limit_before_spooling(env, monkeypatch):
    from starlette.datastructures import UploadFile

    c, s, _ = env
    s.remote_max_result_mb = 1
    _create(c)
    task = c.get("/remote/t1/next", headers=AUTH).json()
    writes = []
    original = UploadFile.write

    async def record(self, data):
        writes.append(len(data))
        await original(self, data)

    monkeypatch.setattr(UploadFile, "write", record)
    # Fits the envelope slack but exceeds the per-file budget.
    r = c.post(f"/remote/t1/{task['taskId']}/result", headers=_lease(task),
               files={"signals": ("s.parquet", b"x" * (1536 * 1024))})
    assert r.status_code == 413 and r.json()["error"]["code"] == "too_large"
    assert sum(writes) <= 1024 * 1024
    assert c.get(f"/jobs/{JOB}/t1-remote").json()["state"] == "leased"


def test_14_result_actual_bytes_override_declared_length(env):
    c, s, _ = env
    s.remote_max_result_mb = 1
    _create(c)
    task = c.get("/remote/t1/next", headers=AUTH).json()
    r = c.post(f"/remote/t1/{task['taskId']}/result",
               headers={**_lease(task), "Content-Length": "10"},
               files={"signals": ("s.parquet", b"x" * (3 * 1024 * 1024))})
    assert r.status_code == 413 and r.json()["error"]["code"] == "too_large"


def test_12_agent_retry_resends_full_file_and_lease(tmp_path):
    agent = _load_agent()
    requests = sys.modules["requests"]
    f = tmp_path / "s.bin"
    f.write_bytes(b"0123456789" * 100)
    seen = []

    class Resp:
        status_code = 200

    class Sess:
        headers = {}

        def request(self, method, url, **kw):
            fh = kw["files"]["signals"][1]
            seen.append((fh.read(), kw.get("headers")))
            if len(seen) == 1:
                raise requests.ConnectionError("rớt giữa chừng")
            return Resp()

    c = agent.Client("http://x", "tok", sleep=lambda _s: None)
    c.s = Sess()
    with open(f, "rb") as fh:
        c.call("POST", "/remote/t1/t1_aaaaaaaaaaaa/result", files={"signals": ("s", fh)},
               lease="L1")
    assert [len(b) for b, _ in seen] == [1000, 1000]
    assert all(h == {"X-Lease-Id": "L1"} for _, h in seen)


def _seed_exp(s, data=b"W" * 1000, sweeps=10):
    t1 = s.workspace / "experiments" / "e80" / "t1"
    (t1 / "ckpt").mkdir(parents=True)
    (t1 / "ckpt" / "seed_latest.pth").write_bytes(data)
    (t1 / "train_config.yaml").write_text(f"sweeps: {sweeps}\nepochs: 80\n")
    return data


def test_15_seed_checkpoint_attached_and_served(env):
    import hashlib
    c, s, app = env
    data = _seed_exp(s)
    _create(c, sweeps=1, epochs=20)
    t = c.get("/remote/t1/next", headers=AUTH).json()
    assert t["seed"] == {"bytes": len(data), "sha256": hashlib.sha256(data).hexdigest(),
                         "sweeps": 10}
    assert t["params"]["sweeps"] == 10  # suy luận phải cùng sweeps với lúc train trọng số
    assert "path" not in json.dumps(t)  # không lộ đường dẫn trên máy worker
    assert c.get(f"/remote/t1/{t['taskId']}/seed").status_code == 401
    r = c.get(f"/remote/t1/{t['taskId']}/seed", headers=AUTH)
    assert r.status_code == 200 and r.content == data


def test_16_no_seed_when_disabled_or_missing(env):
    c, s, app = env
    _create(c, sweeps=1)
    t = c.get("/remote/t1/next", headers=AUTH).json()  # chưa có thí nghiệm nào
    assert "seed" not in t and t["params"]["sweeps"] == 1
    assert c.get(f"/remote/t1/{t['taskId']}/seed", headers=AUTH).status_code == 404
    c.delete(f"/jobs/{JOB}/t1-remote")
    _seed_exp(s)
    app.state.settings.t1_exp = "none"  # tắt hẳn
    _create(c, sweeps=1)
    t2 = c.get("/remote/t1/next", headers=AUTH).json()
    assert "seed" not in t2


def test_17_agent_fetch_seed_checks_sha_and_caches(tmp_path):
    import hashlib
    agent = _load_agent()
    data = b"weights" * 100
    calls = []

    class Raw(io.BytesIO):
        pass

    class Resp:
        def __init__(self, body):
            self.raw = Raw(body)

        def close(self):
            pass

    class C:
        body = data

        def call(self, method, path, **kw):
            calls.append(path)
            return Resp(self.body)

    task = {"taskId": "t1_aaaaaaaaaaaa", "seed": {"bytes": len(data), "sha256":
            hashlib.sha256(data).hexdigest(), "sweeps": 10}}
    c = C()
    p = agent.fetch_seed(c, task, tmp_path)
    assert p.read_bytes() == data and calls == ["/remote/t1/t1_aaaaaaaaaaaa/seed"]
    assert agent.fetch_seed(c, task, tmp_path) == p and len(calls) == 1  # cache theo sha256
    assert agent.fetch_seed(c, {"taskId": "x"}, tmp_path, use_default=False) is None
    p.unlink()
    c.body = b"hong"
    with pytest.raises(agent.TaskRejected):
        agent.fetch_seed(c, task, tmp_path)


def test_18_agent_default_seed_from_github(tmp_path, monkeypatch):
    import hashlib
    agent = _load_agent()
    data = b"github-weights" * 50

    class Resp:
        raw = io.BytesIO(data)

        def raise_for_status(self):
            pass

        def close(self):
            pass

    urls = []
    monkeypatch.setattr(agent.requests, "get", lambda url, **kw: urls.append(url) or Resp(),
                        raising=False)
    monkeypatch.setattr(agent, "DEFAULT_SEED", {**agent.DEFAULT_SEED, "bytes": len(data),
                        "sha256": hashlib.sha256(data).hexdigest()})
    p = agent.fetch_seed(None, {"taskId": "t1_aaaaaaaaaaaa"}, tmp_path)  # worker không gửi
    assert p.read_bytes() == data and urls == [agent.DEFAULT_SEED["url"]]
    assert "media.githubusercontent.com" in urls[0] and urls[0].endswith(".pth")



def _camera_tar(names=None, kind=None):
    from service.remote import CAMERA_FILES
    buf = io.BytesIO()
    with tarfile.open(fileobj=buf, mode="w") as tf:
        for name in CAMERA_FILES if names is None else names:
            member = tarfile.TarInfo(name)
            if kind is not None:
                member.type, member.linkname = kind, "outside"
            else:
                member.size = 3
            tf.addfile(member, io.BytesIO(b"cam") if kind is None else None)
    return buf.getvalue()


def _post_camera(c, task, archive, signals=None):
    return c.post(f"/remote/t1/{task['taskId']}/result", headers=_lease(task),
                  files={"signals": ("s.parquet", _signals(TOKENS) if signals is None else signals),
                         "camera": ("camera.tar", archive)})


def test_camera_round_trip(env):
    from service.remote import CAMERA_FILES
    c, s, _ = env
    _create(c)
    task = c.get("/remote/t1/next", headers=AUTH).json()
    assert task["acceptsCamera"] is True
    response = _post_camera(c, task, _camera_tar())
    assert response.status_code == 200, response.text
    assert all((s.jobs / JOB / name).read_bytes() == b"cam" for name in CAMERA_FILES)
    assert len(list((s.jobs / JOB / "cache").iterdir())) == 7


@pytest.mark.parametrize("name,kind", [
    ("cache/unknown", None), ("cache/../escape", None),
    ("../escape", None), ("/cache/concepts_text.json", None),
    ("cache/concepts_text.json", tarfile.SYMTYPE),
    ("cache/concepts_text.json", tarfile.LNKTYPE),
    ("cache/concepts_text.json", tarfile.DIRTYPE),
])
def test_camera_bad_member_does_not_write(env, name, kind):
    c, s, _ = env
    _create(c)
    task = c.get("/remote/t1/next", headers=AUTH).json()
    response = _post_camera(c, task, _camera_tar([name], kind))
    assert response.status_code == 422 and response.json()["error"]["code"] == "bad_camera"
    assert not (s.jobs / JOB / "t1").exists()
    assert not (s.jobs / JOB / "cache").exists()


@pytest.mark.parametrize("variant", ["duplicate", "missing", "corrupt", "late_bad"])
def test_camera_invalid_archive_preserves_existing_cache(env, variant):
    from service.remote import CAMERA_FILES
    c, s, _ = env
    cache = s.jobs / JOB / "cache"
    cache.mkdir()
    sentinel = cache / "concepts_text.json"
    sentinel.write_bytes(b"original")
    names = list(CAMERA_FILES)
    if variant == "duplicate":
        names.append(names[0])
    elif variant == "missing":
        names.pop()
    elif variant == "late_bad":
        names.append("cache/evil")
    archive = b"broken" if variant == "corrupt" else _camera_tar(names)
    _create(c)
    task = c.get("/remote/t1/next", headers=AUTH).json()
    response = _post_camera(c, task, archive)
    assert response.status_code == 422 and response.json()["error"]["code"] == "bad_camera"
    assert sentinel.read_bytes() == b"original" and len(list(cache.iterdir())) == 1
    assert not (s.jobs / JOB / "t1").exists()


def test_camera_valid_tar_bad_signals_no_write(env):
    c, s, _ = env
    _create(c)
    task = c.get("/remote/t1/next", headers=AUTH).json()
    response = _post_camera(c, task, _camera_tar(), signals=_signals(TOKENS[:1]))
    assert response.status_code == 422 and response.json()["error"]["code"] == "bad_signals"
    assert not (s.jobs / JOB / "cache").exists()


def test_camera_unpacked_size_limit(env):
    c, s, _ = env
    s.remote_max_result_mb = 0.005
    # Sparse archive header exceeds decompressed budget, without allocating payload.
    buf = io.BytesIO()
    with tarfile.open(fileobj=buf, mode="w") as tf:
        member = tarfile.TarInfo("cache/context_frame.parquet")
        member.size = 6000
        tf.addfile(member, io.BytesIO(b"x" * 6000))
    _create(c)
    task = c.get("/remote/t1/next", headers=AUTH).json()
    response = _post_camera(c, task, buf.getvalue())
    assert response.status_code == 413
    assert not (s.jobs / JOB / "cache").exists()


@pytest.mark.parametrize("accepts,enabled,fail", [
    (True, True, False), (False, True, False), (None, True, False),
    (True, False, False), (True, True, True),
])
def test_agent_camera_capability_and_optional_failure(tmp_path, monkeypatch, accepts, enabled, fail):
    from types import SimpleNamespace
    agent = _load_agent()
    exp = tmp_path / "exp"
    exp.mkdir()
    pd.DataFrame(dict(sample_token=TOKENS)).to_parquet(exp / "index.parquet")
    monkeypatch.setattr(agent, "fetch_bundle", lambda *args: (exp, tmp_path / "data"))
    class HB:
        def __init__(self, *args): pass
        def start(self): pass
        def stop(self): pass
    monkeypatch.setattr(agent, "Heartbeat", HB)
    original = agent.camera_archive
    calls = []
    def camera(*args):
        calls.append(True)
        if fail:
            raise agent.StageError("camera failed")
        return original(*args)
    monkeypatch.setattr(agent, "camera_archive", camera)
    sent = []
    class Client:
        def call(self, method, path, **kw):
            assert path.endswith("/result")
            sent.append({name: value[1].read() for name, value in kw["files"].items()})
    task = dict(taskId="t1_aaaaaaaaaaaa", jobId=JOB, acceptsCamera=accepts)
    agent.process(Client(), task, SimpleNamespace(work=str(tmp_path), dry_run=True,
                  train=False, heartbeat_sec=60, camera=enabled))
    assert bool(calls) == (accepts is True and enabled)
    assert "signals" in sent[0]
    assert ("camera" in sent[0]) == (accepts is True and enabled and not fail)
    if "camera" in sent[0]:
        with tarfile.open(fileobj=io.BytesIO(sent[0]["camera"])) as tf:
            assert set(tf.getnames()) == set(agent.CAMERA_FILES)


def test_agent_camera_real_commands_and_missing_output(tmp_path, monkeypatch):
    agent = _load_agent()
    exp = tmp_path / "exp"
    exp.mkdir()
    (exp / "index.parquet").write_bytes(b"index")
    calls = []
    monkeypatch.setattr(agent, "run_stage", lambda command, env, cwd: calls.append(command))
    assert agent.camera_archive(exp, tmp_path / "data", tmp_path, False) is None
    assert calls[0][2] == "c4.cli.lidar_t0" and "cloud" in calls[0]
    assert calls[1][2] == "c4.cli.camera_context"
    assert (tmp_path / "exp_cam/lidar/index.parquet").read_bytes() == b"index"



def test_camera_unpacked_limit_and_three_multipart_files(env, tmp_path):
    from service.remote import _unpack_camera
    from service.errors import ApiError
    archive = tmp_path / "camera.tar"
    archive.write_bytes(_camera_tar())
    dest = tmp_path / "staging"
    with pytest.raises(ApiError) as error:
        _unpack_camera(archive, dest, 20)  # 7 * 3 unpacked bytes
    assert error.value.status == 413
    assert not dest.exists()
    c, s, _ = env
    _create(c)
    task = c.get("/remote/t1/next", headers=AUTH).json()
    response = c.post(f"/remote/t1/{task['taskId']}/result", headers=_lease(task),
                      files={"signals": ("s.parquet", _signals(TOKENS)),
                             "manifest": ("m.json", b"{}"),
                             "camera": ("camera.tar", archive.read_bytes())})
    assert response.status_code == 200, response.text
    assert (s.jobs / JOB / "t1/signals.parquet.manifest.json").read_bytes() == b"{}"
