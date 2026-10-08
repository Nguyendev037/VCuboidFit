"""P04 · S4 merge_features + job runner (model giả, nuScenes giả, stage con thật hoặc stub)."""
import json
import sys
import threading
import time
from datetime import datetime
from pathlib import Path

import numpy as np
import pandas as pd
import pytest
from PIL import Image

from c4.cli import merge_features as merge_cli
from c4.cli import run_job as run_job_cli
from c4.config import load_config
from c4.contracts import ContractError, read_table, write_table
from c4.data.index import build_frames
from c4.data.nusc import NuscTables
from c4.extract.clip import extract_clip
from c4.extract.det import extract_det
from c4.extract.dino import extract_dino
from c4.jobs import runner
from c4.jobs.runner import STAGES, run_job
from c4.params import SelectParams
from c4.pipeline import run_selection
from tests.fixtures.make_nuscenes import make_nuscenes

FAKE = {"C4_FAKE_MODELS": "1"}


def _stub(code: str):
    return [sys.executable, "-c", code]


def _patch_stages(monkeypatch, per_stage: dict[str, str], default: str = "pass"):
    """Thay lệnh stage con bằng đoạn Python ngắn (đường nhanh để test hành vi runner)."""
    monkeypatch.setattr(
        runner, "stage_command",
        lambda stage, job_dir, data_root, profile: _stub(per_stage.get(stage, default)))


def _textured_nuscenes(base: Path) -> Path:
    """nuScenes giả có ảnh camera dạng ô nhiễu (ảnh phẳng của fixture cho q_blur = 0 ⇒ q_ok sai)."""
    root = make_nuscenes(base)
    rng = np.random.default_rng(0)
    for p in sorted(root.glob("samples/CAM_*/*.jpg")):
        noise = rng.integers(0, 256, (90, 160, 3), dtype=np.uint8)
        Image.fromarray(noise).resize((1600, 900), Image.NEAREST).save(p, "JPEG", quality=60)
    return root


def _status(job: Path) -> dict:
    return json.loads((job / "status.json").read_text(encoding="utf-8"))


def _wait_for(pred, timeout=30.0, step=0.05):
    end = time.monotonic() + timeout
    while time.monotonic() < end:
        v = pred()
        if v:
            return v
        time.sleep(step)
    raise AssertionError("hết thời gian chờ điều kiện")


def _ts(s: str) -> float:
    return datetime.fromisoformat(s).timestamp()


@pytest.fixture
def ws(tmp_path):
    return {"C4_WORKSPACE_DIR": str(tmp_path / "ws")}


# ---------------------------------------------------------------- merge_features

@pytest.fixture
def extracted_job(tmp_path, monkeypatch):
    """Job có index + đủ cache của S1–S3 (model giả, gọi thẳng hàm trong tiến trình)."""
    monkeypatch.setenv("C4_FAKE_MODELS", "1")
    root = _textured_nuscenes(tmp_path)
    frames = build_frames(NuscTables.load(root), root)
    job = tmp_path / "job"
    (job / "index").mkdir(parents=True)
    write_table(frames, job / "index" / "frames.parquet", "frames")
    extract_dino(job, root, device="cpu")
    extract_det(job, root, device="cpu")
    extract_clip(job, root, device="cpu")
    return job, frames


def test_merge_row_count_keys_and_q_ok_formula(extracted_job):
    job, frames = extracted_job
    cfg = load_config()
    out = merge_cli.merge_features(job)
    assert len(out) == len(frames)
    assert (out["sample_token"] == frames["sample_token"]).all()
    assert (out["cam"] == frames["cam"]).all()
    assert out["emb_row"].tolist() == list(range(len(frames)))
    dino = pd.read_parquet(job / "cache" / "feat_dino.parquet")
    det = pd.read_parquet(job / "cache" / "feat_det.parquet")
    clip = pd.read_parquet(job / "cache" / "feat_clip.parquet")
    want = ((dino["q_bright"] >= cfg.quality["min_luma"])
            & (dino["q_blur"] >= cfg.quality["min_blur_var"]) & (det["det_n"] >= 1))
    assert out["q_ok"].tolist() == want.tolist()
    assert out["q_ok"].any()
    np.testing.assert_array_equal(out["det_n"].to_numpy(), det["det_n"].to_numpy())
    np.testing.assert_array_equal(out["nov_knn"].to_numpy(), dino["nov_knn"].to_numpy())
    np.testing.assert_array_equal(out["qry_max"].to_numpy(), clip["qry_max"].to_numpy())
    # file ghi ra qua write_table: đọc lại bằng read_table phải qua validate
    back = read_table(job / "cache" / "features_cache.parquet", "features_cache")
    assert len(back) == len(frames)
    assert (job / "cache" / "features_cache.parquet.manifest.json").is_file()


def test_merge_q_ok_false_when_no_detection_or_dark_or_blurry(extracted_job):
    job, _ = extracted_job
    det = pd.read_parquet(job / "cache" / "feat_det.parquet")
    dino = pd.read_parquet(job / "cache" / "feat_dino.parquet")
    det.loc[0, "det_n"] = 0
    dino.loc[1, "q_bright"] = 0.0
    dino.loc[2, "q_blur"] = 0.0
    det.to_parquet(job / "cache" / "feat_det.parquet", index=False)
    dino.to_parquet(job / "cache" / "feat_dino.parquet", index=False)
    out = merge_cli.merge_features(job)
    assert not out.loc[[0, 1, 2], "q_ok"].any()


@pytest.mark.parametrize("victim", ["dino_cls.npy", "clip_img.npy"])
def test_merge_row_mismatch_is_contract_error_exit_2(extracted_job, victim):
    job, frames = extracted_job
    arr = np.load(job / "cache" / victim)
    np.save(job / "cache" / victim, arr[:-1])
    with pytest.raises(ContractError):
        merge_cli.merge_features(job)
    rc = merge_cli.main(["--data-root", str(job), "--job-dir", str(job)])
    assert rc == 2
    assert not (job / "cache" / "features_cache.parquet").exists()


def test_merge_missing_input_is_exit_4(tmp_path):
    job = tmp_path / "empty"
    job.mkdir()
    assert merge_cli.main(["--data-root", str(tmp_path), "--job-dir", str(job)]) == 4


# ---------------------------------------------------------------- run_job (stage thật)

@pytest.fixture(scope="module")
def done_job(tmp_path_factory):
    base = tmp_path_factory.mktemp("runner")
    root = _textured_nuscenes(base)
    job = base / "ws" / "jobs" / "j1"
    env = {**FAKE, "C4_WORKSPACE_DIR": str(base / "ws")}
    t0 = time.monotonic()
    st = run_job(job, root, "local-4060", env=env)
    return dict(job=job, root=root, env=env, status=st, seconds=time.monotonic() - t0)


def test_full_run_done_and_run_selection_succeeds(done_job):
    st, job = done_job["status"], done_job["job"]
    assert st["state"] == "done" and st["error"] is None
    assert [s["name"] for s in st["stages"]] == STAGES == ["index", "dino", "det", "clip", "merge"]
    assert all(s["state"] == "done" for s in st["stages"])
    assert all(isinstance(s["durationSec"], (int, float)) and s["durationSec"] > 0
               for s in st["stages"])
    assert all(isinstance(s["peakVramMb"], int) for s in st["stages"])
    assert _status(job) == st
    assert st["jobId"] == "j1"
    assert (job / "logs" / "dino.log").is_file()
    assert json.loads((job / "progress" / "dino.json").read_text())["done"] > 0
    feat = read_table(job / "cache" / "features_cache.parquet", "features_cache")
    frames = read_table(job / "index" / "frames.parquet", "frames")
    assert len(feat) == len(frames)
    res = run_selection(job, SelectParams())
    assert res["poolSize"] > 0 and (job / "out" / "selections" / res["selectionId"]
                                    / "result.json").is_file()


def test_rerun_skips_every_stage_without_spawning(done_job, monkeypatch):
    def boom(*a, **k):
        raise AssertionError("không được chạy stage con khi đã có output")

    monkeypatch.setattr(runner.subprocess, "Popen", boom)
    t0 = time.monotonic()
    st = run_job(done_job["job"], done_job["root"], "local-4060", env=done_job["env"])
    assert time.monotonic() - t0 < 5
    assert st["state"] == "done"
    assert all(s["state"] == "done" and s["skipped"] and s["durationSec"] == 0
               for s in st["stages"])
    assert st["stages"][1]["peakVramMb"] == done_job["status"]["stages"][1]["peakVramMb"]


def test_cli_run_job_exit_0_on_done_and_stage_code_on_failure(done_job, monkeypatch, tmp_path):
    for k, v in done_job["env"].items():
        monkeypatch.setenv(k, v)
    argv = ["--data-root", str(done_job["root"]), "--job-dir", str(done_job["job"]),
            "--profile", "local-4060"]
    assert run_job_cli.main(argv) == 0
    monkeypatch.setenv("C4_WORKSPACE_DIR", str(tmp_path / "ws2"))
    _patch_stages(monkeypatch, {"dino": "import sys; sys.exit(3)"})
    bad = ["--data-root", str(done_job["root"]), "--job-dir", str(tmp_path / "jbad")]
    assert run_job_cli.main(bad) == 3


# ---------------------------------------------------------------- bảng lỗi (stub)

@pytest.mark.parametrize("code,needle", [(3, "VRAM"), (4, "thiếu"), (2, "contract")])
def test_stage_exit_code_maps_to_failed_with_vietnamese_message(tmp_path, ws, monkeypatch,
                                                                code, needle):
    msg = {3: "oom", 4: "thiếu file X", 2: "vi phạm contract Y"}[code]
    _patch_stages(monkeypatch, {"dino": f"import sys; print({msg!r}, file=sys.stderr); "
                                        f"sys.exit({code})"})
    job = tmp_path / "ws" / "jobs" / "j"
    st = run_job(job, tmp_path, "local-4060", env=ws)
    assert st["state"] == "failed" and st["stage"] == "dino"
    assert st["error"]["code"] == code
    assert needle in st["error"]["message"]
    by = {s["name"]: s["state"] for s in st["stages"]}
    assert by == {"index": "done", "dino": "failed", "det": "queued", "clip": "queued",
                  "merge": "queued"}
    assert _status(job)["error"]["code"] == code
    if code == 4:
        assert "thiếu file X" in st["error"]["message"]  # nêu file thiếu lấy từ log của stage


def test_failed_job_resumes_from_failed_stage_when_rerun(tmp_path, ws, monkeypatch):
    marker = tmp_path / "dino_ran"
    out = tmp_path / "ws" / "jobs" / "j"
    _patch_stages(monkeypatch, {"dino": "import sys; sys.exit(3)"})
    assert run_job(out, tmp_path, "local-4060", env=ws)["state"] == "failed"
    # lần sau: stage dino hết lỗi và chạy tiếp tới hết
    _patch_stages(monkeypatch, {"dino": f"open({str(marker)!r}, 'w').write('x')"})
    assert run_job(out, tmp_path, "local-4060", env=ws)["state"] == "done"
    assert marker.is_file()


# ---------------------------------------------------------------- huỷ

def test_cancel_terminates_child_and_marks_cancelled(tmp_path, ws, monkeypatch):
    started, survived = tmp_path / "started", tmp_path / "survived"
    _patch_stages(monkeypatch, {"dino": (
        f"import time; open({str(started)!r}, 'w').write('1'); time.sleep(3); "
        f"open({str(survived)!r}, 'w').write('1')")})
    job = tmp_path / "ws" / "jobs" / "j"
    cancel, out = threading.Event(), {}
    th = threading.Thread(target=lambda: out.update(st=run_job(job, tmp_path, "local-4060",
                                                               cancel=cancel, env=ws)))
    th.start()
    _wait_for(started.exists)
    t0 = time.monotonic()
    cancel.set()
    th.join(timeout=15)
    assert not th.is_alive()
    assert time.monotonic() - t0 < 2.5  # không chờ stage con chạy hết
    st = out["st"]
    assert st["state"] == "cancelled" and st["error"] is None
    assert {s["name"]: s["state"] for s in st["stages"]}["dino"] == "cancelled"
    assert _status(job)["state"] == "cancelled"
    time.sleep(3.5)
    assert not survived.exists(), "tiến trình con vẫn sống sau khi huỷ"


def test_cancel_while_waiting_for_gpu_lock(tmp_path, ws, monkeypatch):
    from filelock import FileLock

    (tmp_path / "ws").mkdir()
    _patch_stages(monkeypatch, {})
    cancel, out = threading.Event(), {}
    with FileLock(str(tmp_path / "ws" / "gpu.lock")):
        th = threading.Thread(target=lambda: out.update(
            st=run_job(tmp_path / "ws" / "jobs" / "j", tmp_path, "local-4060", cancel=cancel,
                       env=ws)))
        th.start()
        _wait_for(lambda: (tmp_path / "ws" / "jobs" / "j" / "status.json").exists())
        cancel.set()
        th.join(timeout=15)
    assert out["st"]["state"] == "cancelled"


# ---------------------------------------------------------------- pipeline lidar

def _lidar_job(tmp_path, job_id="L1", pipeline="lidar") -> Path:
    job = tmp_path / "ws" / "jobs" / job_id
    job.mkdir(parents=True)
    (job / "job.json").write_text(json.dumps(dict(jobId=job_id, datasetId="d",
                                                  pipeline=pipeline)), encoding="utf-8")
    return job


def test_lidar_pipeline_runs_lidar_index_then_t0(tmp_path, ws, monkeypatch):
    seen = []

    def cmd(stage, job_dir, data_root, profile):
        seen.append(stage)
        return _stub("pass")

    monkeypatch.setattr(runner, "stage_command", cmd)
    job = _lidar_job(tmp_path)
    st = run_job(job, tmp_path, "local-4060", env=ws)
    assert st["state"] == "done" and st["error"] is None and st["pipeline"] == "lidar"
    assert seen == ["lidar_index", "t0"]
    assert [s["name"] for s in st["stages"]] == runner.PIPELINES["lidar"] == ["lidar_index", "t0"]
    assert (job / "progress" / "lidar_index.done.json").is_file()
    assert (job / "progress" / "t0.done.json").is_file()
    assert runner.MODULES["lidar_index"] == "lidar_index" and runner.MODULES["t0"] == "lidar_t0"
    assert runner.OUTPUTS["lidar_index"] == ["lidar/index.parquet"]
    assert set(runner.OUTPUTS["t0"]) == {"lidar/z0.npy", "lidar/filter.parquet"}
    assert _status(job)["pipeline"] == "lidar"


def test_lidar_rerun_skips_stages_with_outputs(tmp_path, ws, monkeypatch):
    _patch_stages(monkeypatch, {}, default="pass")
    job = _lidar_job(tmp_path, "L2")
    assert run_job(job, tmp_path, "local-4060", env=ws)["state"] == "done"
    for rel in ("lidar/index.parquet", "lidar/z0.npy", "lidar/filter.parquet"):
        p = job / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_bytes(b"x")

    def boom(*a, **k):
        raise AssertionError("không được chạy stage con khi đã có output")

    monkeypatch.setattr(runner.subprocess, "Popen", boom)
    st = run_job(job, tmp_path, "local-4060", env=ws)
    assert st["state"] == "done"
    assert all(s["state"] == "done" and s["skipped"] for s in st["stages"])


def test_unknown_pipeline_falls_back_to_camera(tmp_path, ws, monkeypatch):
    seen = []

    def cmd(stage, job_dir, data_root, profile):
        seen.append(stage)
        return _stub("pass")

    monkeypatch.setattr(runner, "stage_command", cmd)
    job = _lidar_job(tmp_path, "L3", pipeline="lung-tung")
    assert run_job(job, tmp_path, "local-4060", env=ws)["pipeline"] == "camera"
    assert seen == runner.STAGES


# ---------------------------------------------------------------- tiến độ

def test_progress_file_is_polled_into_status(tmp_path, ws, monkeypatch):
    job = tmp_path / "ws" / "jobs" / "j"
    prog = job / "progress" / "dino.json"
    _patch_stages(monkeypatch, {"dino": (
        "import json, pathlib, time; p = pathlib.Path(%r); p.parent.mkdir(parents=True, "
        "exist_ok=True); p.write_text(json.dumps(dict(done=3, total=10, peak_vram_mb=123, "
        "updated_at='x'))); time.sleep(2.5)" % str(prog))})
    th = threading.Thread(target=lambda: run_job(job, tmp_path, "local-4060", env=ws))
    th.start()

    def seen():
        try:
            s = _status(job)
        except (OSError, ValueError):
            return None
        return s if s["stage"] == "dino" and s["done"] == 3 else None

    s = _wait_for(seen)
    th.join(timeout=30)
    assert s["state"] == "running" and s["total"] == 10
    assert s["etaSec"] is None or s["etaSec"] >= 0
    dino = next(x for x in _status(job)["stages"] if x["name"] == "dino")
    assert dino["peakVramMb"] == 123


# ---------------------------------------------------------------- khoá GPU

def test_second_job_waits_for_gpu_lock(tmp_path, ws, monkeypatch):
    _patch_stages(monkeypatch, {}, default="import time; time.sleep(0.6)")
    j1, j2 = tmp_path / "ws" / "jobs" / "a", tmp_path / "ws" / "jobs" / "b"
    t1 = threading.Thread(target=lambda: run_job(j1, tmp_path, "local-4060", env=ws))
    t2 = threading.Thread(target=lambda: run_job(j2, tmp_path, "local-4060", env=ws))
    t1.start()
    _wait_for(lambda: (j1 / "status.json").exists() and _status(j1)["state"] == "running")
    t2.start()
    queued = _wait_for(lambda: (j2 / "status.json").exists() and _status(j2)["state"] == "queued")
    assert queued and _status(j1)["state"] == "running"
    t1.join(timeout=30)
    t2.join(timeout=30)
    s1, s2 = _status(j1), _status(j2)
    assert s1["state"] == s2["state"] == "done"
    end1 = max(_ts(s["finishedAt"]) for s in s1["stages"])
    start2 = _ts(next(s for s in s2["stages"] if s["name"] == "index")["startedAt"])
    assert start2 >= end1
