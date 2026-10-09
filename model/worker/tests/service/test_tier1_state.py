"""Plan 09 H02: khả dụng Tầng 1 là thuộc tính của máy; POST /jobs/{id}/t1/run chặn khi job bận."""
import json

import pytest
from fastapi.testclient import TestClient

from service.main import create_app
from service.settings import Settings


@pytest.fixture
def client(tmp_path):
    s = Settings(workspace=tmp_path / "ws", sevenzip="__khong_co_7z__")
    with TestClient(create_app(s)) as c:
        yield c, s


def _job(s, jid, state):
    d = s.jobs / jid
    d.mkdir(parents=True, exist_ok=True)
    (d / "job.json").write_text(json.dumps(dict(
        jobId=jid, datasetId="d", pipeline="lidar", createdAt="2026-10-09T00:00:00",
        state=state)), encoding="utf-8")


def _exp(tmp_path):
    exp = tmp_path / "exp"
    for rel in ("index.parquet", "t1/cfg/pp_seed.yaml", "t1/ckpt/seed_latest.pth"):
        f = exp / rel
        f.parent.mkdir(parents=True, exist_ok=True)
        f.write_bytes(b"x")
    return exp


def test_machine_ready_gives_tier_available_without_signals(client, tmp_path, monkeypatch):
    c, s = client
    monkeypatch.setenv("VCF_T1_EXP", str(_exp(tmp_path)))
    _job(s, "aaaaaaaaaaaa", "done")  # chưa có t1/signals.parquet
    r = c.get("/jobs/aaaaaaaaaaaa/params-schema")
    assert r.status_code == 200 and r.json()["tierAvailable"] == [0, 1]
    monkeypatch.delenv("VCF_T1_EXP")
    assert c.get("/jobs/aaaaaaaaaaaa/params-schema").json()["tierAvailable"] == [0]


def test_post_t1_run_conflicts_when_job_busy(client, tmp_path, monkeypatch):
    c, s = client
    monkeypatch.setenv("VCF_T1_EXP", str(_exp(tmp_path)))
    _job(s, "bbbbbbbbbbbb", "running")
    r = c.post("/jobs/bbbbbbbbbbbb/t1/run")
    assert r.status_code == 409
    assert c.post("/jobs/cccccccccccc/t1/run").status_code == 404


# ---- plan 09 H04: POST /select kiểm Tầng 1 như params-schema; nov_source=none ⇒ β = 0 -----------
import copy  # noqa: E402

import numpy as np  # noqa: E402

from c4.cli import lidar_index, lidar_t0  # noqa: E402
from c4.contracts import read_table, write_table  # noqa: E402
from c4.lidar import load_lidar_config  # noqa: E402
from c4.lidar.uncertainty import signals  # noqa: E402
from tests.fixtures.make_nuscenes import make_nuscenes  # noqa: E402


@pytest.fixture
def lidar_job(client, tmp_path, monkeypatch):
    """Job LiDAR thật (index + t0) đặt trong workspace của service, trạng thái done."""
    c, s = client
    cfg = copy.deepcopy(load_lidar_config())
    cfg["filter"]["min_points"] = 50
    monkeypatch.setattr(lidar_t0, "load_lidar_config", lambda: cfg)
    root = make_nuscenes(tmp_path, n_scenes=4, frames_per_scene=8, with_annotations=True)
    jid = "dddddddddddd"
    _job(s, jid, "done")
    (s.jobs / jid / "status.json").write_text(json.dumps(
        dict(jobId=jid, pipeline="lidar", state="done", stage="t1", done=1, total=1,
             stages=[])), encoding="utf-8")
    assert lidar_index.main(["--data-root", str(root), "--job-dir", str(s.jobs / jid)]) == 0
    assert lidar_t0.main(["--data-root", str(root), "--job-dir", str(s.jobs / jid)]) == 0
    return c, s, jid


def _write_signals(job, nov_source):
    index = read_table(job / "lidar" / "index.parquet", "lidar_index")
    rng = np.random.default_rng(1)
    z1 = rng.normal(size=(len(index), 8)).astype(np.float32)
    preds = [dict(sample_token=t, boxes=rng.uniform(-9, 9, (2, 7)).astype(np.float32),
                  labels=np.array([0, 1], np.int32), scores=np.array([0.5, 0.9], np.float32))
             for t in index["sample_token"]]
    sig = signals(index, preds, preds, z1, (index["frame_idx"] == 0).to_numpy(),
                  load_lidar_config())
    (job / "t1").mkdir(exist_ok=True)
    write_table(sig, str(job / "t1" / "signals.parquet"), "t1_signals", nov_source=nov_source)


def test_select_checks_tier_like_params_schema_machine_ready(lidar_job, tmp_path, monkeypatch):
    """Máy sẵn sàng, job chưa có signals: schema báo [0,1] thì select phải cùng hiểu như vậy."""
    c, s, jid = lidar_job
    monkeypatch.setenv("VCF_T1_EXP", str(_exp(tmp_path)))
    assert c.get(f"/jobs/{jid}/params-schema").json()["tierAvailable"] == [0, 1]
    r = c.post(f"/jobs/{jid}/select", json={})  # tier mặc định: chưa có tín hiệu ⇒ rơi về Tầng 0
    assert r.status_code == 200, r.text
    assert r.json()["tierAvailable"] == [0, 1] and r.json()["params"]["tier"] == 0
    r1 = c.post(f"/jobs/{jid}/select", json={"tier": 1})  # Tầng 1 chưa chạy ⇒ 422 rõ lý do
    assert r1.status_code == 422 and r1.json()["error"]["code"] == "tier_unavailable"
    assert "chạy Tầng 1" in r1.json()["error"]["message"]


def test_select_tier1_rejected_when_machine_not_ready_and_no_signals(lidar_job, monkeypatch):
    c, s, jid = lidar_job
    monkeypatch.delenv("VCF_T1_EXP", raising=False)
    r = c.post(f"/jobs/{jid}/select", json={"tier": 1})
    assert r.status_code == 422 and r.json()["error"]["code"] == "tier_unavailable"
    assert c.post(f"/jobs/{jid}/select", json={}).json()["tierAvailable"] == [0]


def test_select_tier1_works_with_job_signals_without_machine(lidar_job, monkeypatch):
    c, s, jid = lidar_job
    monkeypatch.delenv("VCF_T1_EXP", raising=False)
    _write_signals(s.jobs / jid, "seed")
    r = c.post(f"/jobs/{jid}/select", json={})
    assert r.status_code == 200, r.text
    assert r.json()["params"]["tier"] == 1 and r.json()["tierAvailable"] == [0, 1]
    assert r.json()["params"]["beta"] > 0


def test_nov_source_none_sets_beta_zero_with_warning(lidar_job, monkeypatch):
    c, s, jid = lidar_job
    monkeypatch.delenv("VCF_T1_EXP", raising=False)
    _write_signals(s.jobs / jid, "none")
    r = c.post(f"/jobs/{jid}/select", json={})
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["params"]["tier"] == 1 and body["params"]["beta"] == 0
    assert any("Lạ với model" in w for w in body["warnings"]), body["warnings"]


# ---- plan 09 §8 (Technical Lead): lý do dễ hiểu, khối tier0, chọn khi chỉ còn t1 chạy
from c4.jobs.runner import tier1_reason  # noqa: E402


@pytest.mark.parametrize("log, want", [
    ("skip: VCF_T1_EXP chưa đặt\n", "Lúc phân tích, máy chưa bật model Tầng 1."),
    ("skip: thiếu " + r"F:\ws\exp\t1\ckpt\seed_latest.pth" + "\n",
     "Model Tầng 1 trên máy chưa đủ file."),
    ("open //./pipe/dockerDesktopLinuxEngine: not found\ndocker lỗi (1)\n",
     "Không chạy được Docker"),
    ("cần GPU\n", "Máy không có GPU"),
])
def test_tier1_reason_is_friendly_and_hides_paths(tmp_path, log, want):
    f = tmp_path / "t1.log"
    f.write_text(log, encoding="utf-8")
    got = tier1_reason(f, 5)
    assert got.startswith(want), got
    assert "VCF_" not in got and ":\\" not in got and "/" not in got


def test_tier1_reason_unknown_line_strips_paths(tmp_path):
    f = tmp_path / "t1.log"
    f.write_text("lạ: không mở được " + r"C:\a\b.bin" + "\n", encoding="utf-8")
    got = tier1_reason(f, 7)
    assert got.startswith("Tầng 1 lỗi (mã 7)") and "b.bin" not in got


def test_job_status_has_tier0_block(lidar_job):
    c, s, jid = lidar_job
    t0 = c.get(f"/jobs/{jid}").json()["tier0"]
    assert t0["nKeep"] is not None and t0["nTotal"] >= t0["nKeep"] > 0


def test_select_allowed_while_only_t1_runs(lidar_job, monkeypatch):
    """D4: chạy lại Tầng 1 không được làm mất khả năng chọn theo Tầng 0."""
    c, s, jid = lidar_job
    monkeypatch.delenv("VCF_T1_EXP", raising=False)
    d = s.jobs / jid
    st = dict(jobId=jid, pipeline="lidar", state="running", stage="t1", done=0, total=1,
              stages=[dict(name="lidar_index", state="done"), dict(name="t0", state="done"),
                      dict(name="t1", state="running")])
    (d / "status.json").write_text(json.dumps(st), encoding="utf-8")
    assert c.post(f"/jobs/{jid}/select", json={}).status_code == 200
    st["stage"], st["stages"][1]["state"] = "t0", "running"  # t0 chưa xong ⇒ vẫn chặn
    (d / "status.json").write_text(json.dumps(st), encoding="utf-8")
    assert c.post(f"/jobs/{jid}/select", json={}).status_code == 409


# ---- plan 09 H05: lý do máy chưa sẵn sàng (Docker / thiếu checkpoint)
@pytest.mark.parametrize("stage_state", [None, "skipped"])
def test_worker_in_docker_reports_skipped(client, tmp_path, monkeypatch, stage_state):
    from pathlib import Path

    from c4.lidar.pipeline import tier1_machine_ready, tier1_machine_reason

    c, s = client
    monkeypatch.setenv("VCF_T1_EXP", str(_exp(tmp_path)))
    original_exists = Path.exists
    monkeypatch.setattr(Path, "exists", lambda path:
                        True if path == Path("/.dockerenv") else original_exists(path))
    _job(s, "eeeeeeeeeeee", "done")
    if stage_state:
        (s.jobs / "eeeeeeeeeeee" / "status.json").write_text(json.dumps(dict(
            jobId="eeeeeeeeeeee", pipeline="lidar", state="done", stage="t1",
            done=1, total=1, stages=[dict(name="t1", state=stage_state,
                                         reason="Lúc phân tích, máy chưa bật model Tầng 1.")]
        )), encoding="utf-8")
    r = c.get("/jobs/eeeeeeeeeeee")
    assert r.status_code == 200
    t1 = r.json()["tier1"]
    assert t1["state"] == "skipped" and t1["canRun"] is False
    assert t1["reason"] == (
        "Worker đang chạy trong Docker nên không chạy được Tầng 1 trên máy này.")
    assert tier1_machine_reason() == t1["reason"]
    assert tier1_machine_ready() is False
    assert c.get("/jobs/eeeeeeeeeeee/params-schema").json()["tierAvailable"] == [0]


def test_missing_checkpoint_reports_incomplete_model(client, tmp_path, monkeypatch):
    from c4.lidar.pipeline import tier1_machine_ready, tier1_machine_reason

    c, s = client
    exp = tmp_path / "incomplete-exp"
    for rel in ("index.parquet", "t1/cfg/pp_seed.yaml"):
        f = exp / rel
        f.parent.mkdir(parents=True, exist_ok=True)
        f.write_bytes(b"x")
    monkeypatch.setenv("VCF_T1_EXP", str(exp))
    _job(s, "ffffffffffff", "done")
    r = c.get("/jobs/ffffffffffff")
    assert r.status_code == 200
    t1 = r.json()["tier1"]
    assert t1["state"] == "skipped" and t1["canRun"] is False
    assert t1["reason"] == "Model Tầng 1 trên máy chưa đủ file."
    assert tier1_machine_reason() == t1["reason"]
    assert tier1_machine_ready() is False
    assert c.get("/jobs/ffffffffffff/params-schema").json()["tierAvailable"] == [0]


def test_machine_params_schema_without_job(client, tmp_path, monkeypatch):
    """Plan 09 D1 phía web: chưa có job vẫn biết máy có Tầng 1 hay chưa, kèm lý do."""
    c, s = client
    r = c.get("/params-schema")
    assert r.status_code == 200 and r.json()["tierAvailable"] == [0]
    assert r.json()["tier1Reason"] == "Máy này chưa có model Tầng 1."
    monkeypatch.setenv("VCF_T1_EXP", str(_exp(tmp_path)))
    body = c.get("/params-schema").json()
    assert body["tierAvailable"] == [0, 1] and body["tier1Reason"] is None
    assert any(f["key"] == "tier" for f in body["fields"])
