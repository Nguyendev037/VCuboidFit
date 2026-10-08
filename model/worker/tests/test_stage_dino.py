import json
import os

import numpy as np
import pandas as pd
import pytest
import torch

from c4.cli import extract_dino
from c4.contracts import write_table
from c4.data.index import build_frames
from c4.data.nusc import NuscTables
from c4.extract.dino import extract_dino as run_dino
from c4.extract.dino import weights_dir
from tests.fixtures.make_nuscenes import make_nuscenes

BAD = "samples/CAM_FRONT/scene1_f2__CAM_FRONT.jpg"


@pytest.fixture(autouse=True)
def fake_models(monkeypatch):
    monkeypatch.setenv("C4_FAKE_MODELS", "1")


def _job(tmp_path, **kw):
    root = make_nuscenes(tmp_path, **kw)
    frames = build_frames(NuscTables.load(root), root)
    job = tmp_path / "job"
    (job / "index").mkdir(parents=True)
    write_table(frames, job / "index" / "frames.parquet", "frames")
    return root, job, frames


def _cli(root, job, *extra):
    return extract_dino.main(["--data-root", str(root), "--job-dir", str(job),
                              "--device", "cpu", *extra])


def test_outputs_have_one_row_per_image_with_contract_shapes(tmp_path):
    root, job, frames = _job(tmp_path)
    assert _cli(root, job) == 0
    Z = np.load(job / "cache" / "dino_cls.npy")
    feat = pd.read_parquet(job / "cache" / "feat_dino.parquet")
    assert Z.shape == (len(frames), 768) and Z.dtype == np.float16
    np.testing.assert_allclose(np.linalg.norm(Z.astype(np.float32), axis=1), 1.0, atol=2e-3)
    assert list(feat.columns) == ["sample_token", "cam", "emb_row", "nov_knn", "q_bright", "q_blur"]
    assert len(feat) == len(frames)
    assert (feat["sample_token"] == frames["sample_token"]).all()
    assert (feat["cam"] == frames["cam"]).all()
    assert feat["emb_row"].tolist() == list(range(len(frames)))
    assert str(feat["emb_row"].dtype) == "int32"
    assert str(feat["nov_knn"].dtype) == "float32"


def test_novelty_is_finite_and_quality_measured(tmp_path):
    root, job, _ = _job(tmp_path)
    assert _cli(root, job) == 0
    feat = pd.read_parquet(job / "cache" / "feat_dino.parquet")
    assert np.isfinite(feat[["nov_knn", "q_bright", "q_blur"]].to_numpy()).all()
    assert (feat["nov_knn"] > 0).all() and (feat["nov_knn"] <= 2).all()
    assert (feat["q_bright"] > 0).all() and (feat["q_blur"] >= 0).all()  # ảnh fixture phẳng


def test_limit_processes_only_first_n_images(tmp_path):
    root, job, frames = _job(tmp_path)
    assert _cli(root, job, "--limit", "3") == 0
    feat = pd.read_parquet(job / "cache" / "feat_dino.parquet")
    assert np.load(job / "cache" / "dino_cls.npy").shape[0] == 3
    assert feat["sample_token"].tolist() == frames["sample_token"].head(3).tolist()
    assert json.loads((job / "progress" / "dino.json").read_text())["total"] == 3


def test_resume_does_not_recompute_finished_shards(tmp_path):
    root, job, frames = _job(tmp_path)
    shard_dir = job / "cache" / "dino_shards"
    run_dino(job, root, shard=16, workers=0, device="cpu")
    shards = sorted(shard_dir.glob("shard_*.npy"))
    assert len(shards) == -(-len(frames) // 16) >= 4
    before = {p.name: p.stat().st_mtime_ns for p in shards}
    ref = (job / "cache" / "dino_cls.npy").read_bytes()
    run_dino(job, root, shard=16, workers=0, device="cpu", resume=True)
    assert {p.name: p.stat().st_mtime_ns for p in shard_dir.glob("shard_*.npy")} == before
    assert (job / "cache" / "dino_cls.npy").read_bytes() == ref


def test_resume_after_kill_is_byte_identical(tmp_path):
    root, job, _ = _job(tmp_path)
    run_dino(job, root, shard=16, workers=0, device="cpu")
    ref = (job / "cache" / "dino_cls.npy").read_bytes()
    ref_feat = pd.read_parquet(job / "cache" / "feat_dino.parquet")
    shards = sorted((job / "cache" / "dino_shards").glob("shard_*.npy"))
    survivors = {p.name: p.stat().st_mtime_ns for p in shards[:2]}
    for p in shards[2:]:  # giả lập "mất điện" sau shard 1
        p.unlink()
    (job / "cache" / "dino_cls.npy").unlink()
    run_dino(job, root, shard=16, workers=0, device="cpu", resume=True)
    assert (job / "cache" / "dino_cls.npy").read_bytes() == ref
    pd.testing.assert_frame_equal(pd.read_parquet(job / "cache" / "feat_dino.parquet"), ref_feat)
    for p in shards[:2]:
        assert p.stat().st_mtime_ns == survivors[p.name]


def test_resume_ignores_shards_from_a_different_limit(tmp_path):
    root, job, frames = _job(tmp_path)
    assert _cli(root, job, "--limit", "3") == 0
    assert _cli(root, job, "--resume") == 0
    assert np.load(job / "cache" / "dino_cls.npy").shape[0] == len(frames)


def test_without_resume_recomputes_everything(tmp_path):
    root, job, _ = _job(tmp_path)
    run_dino(job, root, shard=16, workers=0, device="cpu")
    shard = job / "cache" / "dino_shards" / "shard_00000.npy"
    shard.write_bytes(b"garbage")
    run_dino(job, root, shard=16, workers=0, device="cpu")
    assert len(np.load(shard)) == 16


def test_corrupt_jpeg_gives_zero_brightness_not_a_crash(tmp_path):
    root, job, frames = _job(tmp_path, corrupt=[BAD])
    assert _cli(root, job) == 0
    feat = pd.read_parquet(job / "cache" / "feat_dino.parquet")
    i = int(np.flatnonzero(frames["img_path"] == BAD)[0])
    assert feat["q_bright"].iloc[i] == 0.0 and feat["q_blur"].iloc[i] == 0.0
    assert len(feat) == len(frames)
    assert (np.delete(feat["q_bright"].to_numpy(), i) > 0).all()


def test_missing_frames_table_exits_4(tmp_path, capsys):
    assert _cli(tmp_path / "nodata", tmp_path / "emptyjob") == 4
    assert "frames.parquet" in capsys.readouterr().err


def test_missing_weights_exits_4_and_names_fetch_command(tmp_path, monkeypatch, capsys):
    monkeypatch.delenv("C4_FAKE_MODELS")
    monkeypatch.setenv("C4_WEIGHTS_DIR", str(tmp_path / "no_weights"))
    root, job, _ = _job(tmp_path)
    assert _cli(root, job) == 4
    assert "python scripts/fetch_weights.py" in capsys.readouterr().err


def test_weights_dir_follows_env(monkeypatch, tmp_path):
    monkeypatch.setenv("C4_WEIGHTS_DIR", str(tmp_path / "w"))
    assert weights_dir() == tmp_path / "w"
    monkeypatch.delenv("C4_WEIGHTS_DIR")
    assert weights_dir().parts[-2:] == ("workspace", "weights")


@pytest.mark.gpu
def test_real_dinov2_on_eight_images(tmp_path, monkeypatch):
    monkeypatch.delenv("C4_FAKE_MODELS")
    hub = weights_dir() / "torch_hub" / "checkpoints" / "dinov2_vitb14_pretrain.pth"
    if not torch.cuda.is_available():
        pytest.skip("không có CUDA")
    if not hub.is_file():
        pytest.skip(f"thiếu trọng số {hub} (chạy scripts/fetch_weights.py)")
    root, job, _ = _job(tmp_path)
    run_dino(job, root, limit=8, device="cuda")
    Z = np.load(job / "cache" / "dino_cls.npy")
    assert Z.shape == (8, 768) and np.isfinite(Z.astype(np.float32)).all()
    assert os.path.isfile(job / "progress" / "dino.json")
