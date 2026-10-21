"""Camera orchestration contracts, without running GPU inference."""
import json
import subprocess
import sys
from types import SimpleNamespace

import pandas as pd
import pytest

from c4.cli import camera_context as camera
from c4.jobs import runner


def _touch(job, *paths):
    for rel in paths:
        path = job / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.touch()


def _args(job):
    return ["--job-dir", str(job), "--data-root", "D", "--profile", "azure-lite", "--resume"]


@pytest.mark.parametrize("torch", [None, SimpleNamespace(cuda=SimpleNamespace(is_available=lambda: False))])
def test_no_torch_or_gpu_writes_nothing(tmp_path, monkeypatch, capsys, torch):
    monkeypatch.setitem(sys.modules, "torch", torch)
    job = tmp_path / "absent"
    assert camera.main(_args(job)) == 0
    assert not job.exists()
    assert "camera: bỏ qua — máy không có GPU/torch" in capsys.readouterr().err


@pytest.fixture
def gpu(monkeypatch):
    monkeypatch.setattr(camera, "gpu_available", lambda: True)


def test_steps_commands_manifest_and_progress(tmp_path, monkeypatch, gpu):
    from c4 import contracts
    from c4.cli import context, build_index

    calls, progress = [], []
    monkeypatch.setattr(contracts, "read_table", lambda path, schema:
                        pd.DataFrame({"sample_token": ["b", "a", "b"]}))
    atomic = camera._atomic_json

    def record_progress(value, path):
        progress.append(value.copy())
        atomic(value, path)

    def run(cmd, *, check):
        assert check is True
        assert cmd[:2] == [sys.executable, "-m"]
        module = cmd[2].split(".")[-1]
        # Parse with the real parsers: catches misplaced context subcommands/flags.
        parser = context.make_parser() if module == "context" else build_index.make_parser("test")
        args = parser.parse_args(cmd[3:])
        assert args.job_dir == str(tmp_path) and args.data_root == "D"
        calls.append((module, getattr(args, "cmd", None)))
        if module in ("build_index", "extract_clip"):
            assert args.device == "cuda"
        if module == "context" and args.cmd == "fit":
            assert args.split == "V"
            assert (tmp_path / "split_manifest.csv").read_text() == "sample_token,split\nb,V\na,V\n"
        if module == "context" and args.cmd == "run":
            assert args.profile == "multisensor"

    def crops(job, root, device):
        assert str(root) == "D" and device == "cuda"
        calls.append(("crops", None))

    monkeypatch.setattr(camera, "_atomic_json", record_progress)
    monkeypatch.setattr(camera.subprocess, "run", run)
    monkeypatch.setattr(camera, "_build_crops", crops)
    assert camera.main(_args(tmp_path)) == 0
    assert calls == [("build_index", None), ("extract_clip", None), ("context", "cv"),
                     ("context", "fit"), ("context", "run"), ("crops", None)]
    assert progress == [dict(done=i, total=7, etaSec=None) for i in range(1, 8)]
    assert json.loads((tmp_path / "progress/camera.json").read_text()) == progress[-1]


def test_existing_outputs_skip_all_work_and_preserve_manifest(tmp_path, monkeypatch, gpu):
    _touch(tmp_path, "index/frames.parquet", "index/cam_poses.parquet", "cache/clip_img.npy",
           "cache/quality_cv.parquet", "cache/context_thresholds_v1.json",
           "cache/context_frame.parquet", "cache/rare_crops.npy")
    manifest = tmp_path / "split_manifest.csv"
    manifest.write_text("sample_token,split\noriginal,V\n")

    def fail(*args, **kwargs):
        pytest.fail("existing outputs must skip work")

    monkeypatch.setattr(camera.subprocess, "run", fail)
    monkeypatch.setattr(camera, "_build_crops", fail)
    assert camera.main(_args(tmp_path)) == 0
    assert manifest.read_text() == "sample_token,split\noriginal,V\n"
    assert json.loads((tmp_path / "progress/camera.json").read_text())["done"] == 7


@pytest.mark.parametrize("existing", ["index/frames.parquet", "index/cam_poses.parquet"])
def test_partial_index_rebuilt(tmp_path, monkeypatch, gpu, existing):
    _touch(tmp_path, existing)
    calls = []

    def stop(cmd, **kwargs):
        calls.append(cmd)
        raise subprocess.CalledProcessError(2, cmd)

    monkeypatch.setattr(camera.subprocess, "run", stop)
    assert camera.main(_args(tmp_path)) == 2
    assert calls[0][2] == "c4.cli.build_index"


def test_missing_weights_preserves_exit_and_hint(tmp_path, monkeypatch, gpu, capsys):
    _touch(tmp_path, "index/frames.parquet", "index/cam_poses.parquet")

    def missing(cmd, **kwargs):
        raise subprocess.CalledProcessError(4, cmd)

    monkeypatch.setattr(camera.subprocess, "run", missing)
    assert camera.main(_args(tmp_path)) == 4
    assert "fetch_weights.py" in capsys.readouterr().err
    assert json.loads((tmp_path / "progress/camera.json").read_text())["done"] == 2


def test_build_crops_uses_exact_selection(tmp_path, monkeypatch):
    from c4.rare import pipeline, semantic

    calls = []

    def select(job, root, **kwargs):
        calls.append((job, root, kwargs))
        return {"selectionId": "fresh-selection"}

    monkeypatch.setattr(pipeline, "run_rare_v24", select)
    monkeypatch.setattr(semantic, "build_crops", lambda job, root, **kwargs: calls.append(kwargs))
    camera._build_crops(tmp_path, tmp_path / "data", "cuda")
    assert calls == [(tmp_path, tmp_path / "data", dict(profile="lidar_only", pool_split="all", ref_split="all")),
                     dict(device="cuda", sid="fresh-selection")]


@pytest.mark.parametrize("rc, message, state, reason", [
    (0, "camera: bỏ qua — máy không có GPU/torch", "skipped", "Máy không có GPU"),
    (4, "camera: lỗi bước 3 (mã 4) — chạy fetch_weights.py", "failed", "fetch_weights.py"),
    (1, "camera: lỗi bước 7: ValueError: lỗi crops", "failed", "lỗi crops"),
])
def test_camera_optional_runner(tmp_path, monkeypatch, rc, message, state, reason):
    import threading

    st = runner._Status(tmp_path, "lidar")
    monkeypatch.setattr(runner, "_is_done", lambda job, stage: stage != "camera")

    def run(job, status, stage, cmd, env, cancel):
        assert stage == "camera" and cmd[2] == "c4.cli.camera_context"
        log = job / "logs/camera.log"
        log.parent.mkdir(parents=True, exist_ok=True)
        log.write_text(message, encoding="utf-8")
        return rc

    monkeypatch.setattr(runner, "_run_stage", run)
    result = runner._run_stages(tmp_path, tmp_path, "local-4060", st, {}, threading.Event())
    assert result["state"] == "done" and result["error"] is None
    assert st.stage("camera")["state"] == state
    assert reason in st.stage("camera")["reason"]
    assert not (tmp_path / "progress/camera.done.json").exists()


def test_camera_outputs_and_resume_marker(tmp_path, monkeypatch):
    import threading

    outputs = ["cache/context_frame.parquet", "cache/context_frame.parquet.manifest.json",
               "cache/rare_crops.npy", "cache/rare_crops.parquet",
               "cache/rare_crops.parquet.manifest.json", "cache/concepts_text.npy", "cache/concepts_text.json"]
    assert runner.OUTPUTS["camera"] == outputs
    st = runner._Status(tmp_path, "lidar")
    monkeypatch.setattr(runner, "_is_done", lambda job, stage: stage != "camera")

    def run(*args):
        _touch(tmp_path, *outputs)
        return 0

    monkeypatch.setattr(runner, "_run_stage", run)
    result = runner._run_stages(tmp_path, tmp_path, "local-4060", st, {}, threading.Event())
    assert result["state"] == "done" and st.stage("camera")["state"] == "done"
    assert (tmp_path / "progress/camera.done.json").is_file()
