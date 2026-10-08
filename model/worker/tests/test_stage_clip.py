import json

import numpy as np
import pandas as pd
import pytest
import torch

from c4.cli import extract_clip
from c4.config import load_queries
from c4.contracts import write_table
from c4.data.index import build_frames
from c4.data.nusc import NuscTables
from c4.extract.clip import FakeTextEncoder, OpenClipTextEncoder
from c4.extract.clip import extract_clip as run_clip
from c4.extract.dino import weights_dir
from c4.mining.query import apply_queries
from tests.fixtures.make_nuscenes import make_nuscenes


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
    return extract_clip.main(["--data-root", str(root), "--job-dir", str(job),
                              "--device", "cpu", *extra])


def test_outputs_have_contract_shapes_and_default_query_ids(tmp_path):
    root, job, frames = _job(tmp_path)
    assert _cli(root, job) == 0
    C = np.load(job / "cache" / "clip_img.npy")
    feat = pd.read_parquet(job / "cache" / "feat_clip.parquet")
    assert C.shape == (len(frames), 512) and C.dtype == np.float16
    np.testing.assert_allclose(np.linalg.norm(C.astype(np.float32), axis=1), 1.0, atol=2e-3)
    assert list(feat.columns) == ["sample_token", "cam", "qry_max", "qry_best"]
    assert (feat["sample_token"] == frames["sample_token"]).all()
    assert (feat["cam"] == frames["cam"]).all()
    assert set(feat["qry_best"]) <= {q["id"] for q in load_queries()}
    assert str(feat["qry_max"].dtype) == "float32"
    assert feat["qry_max"].between(-1.0001, 1.0001).all()
    assert json.loads((job / "progress" / "clip.json").read_text())["done"] == len(frames)


def test_qry_matches_best_cosine_with_the_default_queries(tmp_path):
    root, job, _ = _job(tmp_path)
    assert _cli(root, job) == 0
    C = np.load(job / "cache" / "clip_img.npy").astype(np.float32)
    feat = pd.read_parquet(job / "cache" / "feat_clip.parquet")
    qs = load_queries()
    T = OpenClipTextEncoder().encode([q["text"] for q in qs])
    sim = C @ T.T
    np.testing.assert_allclose(feat["qry_max"], sim.max(1), atol=2e-3)
    assert feat["qry_best"].tolist() == [qs[i]["id"] for i in sim.argmax(1)]


def test_limit_processes_only_first_n_images(tmp_path):
    root, job, frames = _job(tmp_path)
    assert _cli(root, job, "--limit", "3") == 0
    feat = pd.read_parquet(job / "cache" / "feat_clip.parquet")
    assert np.load(job / "cache" / "clip_img.npy").shape[0] == 3
    assert feat["sample_token"].tolist() == frames["sample_token"].head(3).tolist()


def test_resume_does_not_recompute_and_survives_a_kill(tmp_path):
    root, job, frames = _job(tmp_path)
    run_clip(job, root, shard=16, workers=0, device="cpu")
    shard_dir = job / "cache" / "clip_shards"
    shards = sorted(shard_dir.glob("shard_*.npy"))
    assert len(shards) == -(-len(frames) // 16) >= 4
    ref = (job / "cache" / "clip_img.npy").read_bytes()
    ref_feat = pd.read_parquet(job / "cache" / "feat_clip.parquet")
    before = {p.name: p.stat().st_mtime_ns for p in shards}

    run_clip(job, root, shard=16, workers=0, device="cpu", resume=True)
    assert {p.name: p.stat().st_mtime_ns for p in shard_dir.glob("shard_*.npy")} == before

    for p in shards[2:]:  # "mất điện" sau shard 1
        p.unlink()
    (job / "cache" / "clip_img.npy").unlink()
    run_clip(job, root, shard=16, workers=0, device="cpu", resume=True)
    assert (job / "cache" / "clip_img.npy").read_bytes() == ref
    pd.testing.assert_frame_equal(pd.read_parquet(job / "cache" / "feat_clip.parquet"), ref_feat)
    for p in shards[:2]:
        assert p.stat().st_mtime_ns == before[p.name]


def test_resume_ignores_shards_from_a_different_limit(tmp_path):
    root, job, frames = _job(tmp_path)
    assert _cli(root, job, "--limit", "3") == 0
    assert _cli(root, job, "--resume") == 0
    assert np.load(job / "cache" / "clip_img.npy").shape[0] == len(frames)


def test_corrupt_jpeg_does_not_crash(tmp_path):
    bad = "samples/CAM_FRONT/scene1_f2__CAM_FRONT.jpg"
    root, job, frames = _job(tmp_path, corrupt=[bad])
    assert _cli(root, job) == 0
    assert len(pd.read_parquet(job / "cache" / "feat_clip.parquet")) == len(frames)


# ---------- text encoder ----------

def test_open_clip_text_encoder_in_fake_mode_returns_unit_vectors():
    enc = OpenClipTextEncoder()
    T = enc.encode(["a night road", "a cyclist", "a night road"])
    assert T.shape == (3, 512) and T.dtype == np.float32
    np.testing.assert_allclose(np.linalg.norm(T, axis=1), 1.0, atol=1e-5)
    np.testing.assert_array_equal(T[0], T[2])  # cùng text → cùng vector
    assert not np.allclose(T[0], T[1])
    np.testing.assert_array_equal(OpenClipTextEncoder().encode(["a cyclist"])[0], T[1])


def test_fake_text_encoder_is_deterministic_unit_vectors():
    T = FakeTextEncoder().encode(["x", "y"])
    assert T.shape == (2, 512)
    np.testing.assert_allclose(np.linalg.norm(T, axis=1), 1.0, atol=1e-5)
    np.testing.assert_array_equal(T, FakeTextEncoder().encode(["x", "y"]))


def test_text_encoder_is_lazy_and_plugs_into_plan1_apply_queries(tmp_path, monkeypatch):
    monkeypatch.delenv("C4_FAKE_MODELS")
    monkeypatch.setenv("C4_WEIGHTS_DIR", str(tmp_path / "no_weights"))
    OpenClipTextEncoder()  # dựng object không đụng trọng số
    monkeypatch.setenv("C4_FAKE_MODELS", "1")
    root, job, _ = _job(tmp_path)
    assert _cli(root, job) == 0
    feat = pd.read_parquet(job / "cache" / "feat_clip.parquet").assign(
        emb_row=lambda d: np.arange(len(d)))
    C = np.load(job / "cache" / "clip_img.npy")
    out = apply_queries(feat, C, [{"id": "custom_a", "text": "a zebra on the highway"}],
                        OpenClipTextEncoder())
    assert (out["qry_best"] == "custom_a").all() and len(out) == len(feat)


def test_missing_frames_table_exits_4(tmp_path, capsys):
    assert _cli(tmp_path / "nodata", tmp_path / "emptyjob") == 4
    assert "frames.parquet" in capsys.readouterr().err


def test_missing_weights_exits_4_and_names_fetch_command(tmp_path, monkeypatch, capsys):
    monkeypatch.delenv("C4_FAKE_MODELS")
    monkeypatch.setenv("C4_WEIGHTS_DIR", str(tmp_path / "no_weights"))
    root, job, _ = _job(tmp_path)
    assert _cli(root, job) == 4
    assert "python scripts/fetch_weights.py" in capsys.readouterr().err


def test_text_encoder_missing_weights_raises_file_not_found(tmp_path, monkeypatch):
    monkeypatch.delenv("C4_FAKE_MODELS")
    monkeypatch.setenv("C4_WEIGHTS_DIR", str(tmp_path / "no_weights"))
    with pytest.raises(FileNotFoundError, match="fetch_weights.py"):
        OpenClipTextEncoder().encode(["x"])


def _real_clip_ready():
    d = weights_dir() / "open_clip"
    if not torch.cuda.is_available():
        pytest.skip("không có CUDA")
    if not d.is_dir() or not any(d.iterdir()):
        pytest.skip(f"thiếu trọng số {d} (chạy scripts/fetch_weights.py)")


@pytest.mark.gpu
def test_real_clip_on_eight_images(tmp_path, monkeypatch):
    monkeypatch.delenv("C4_FAKE_MODELS")
    _real_clip_ready()
    root, job, _ = _job(tmp_path)
    feat = run_clip(job, root, limit=8, device="cuda")
    C = np.load(job / "cache" / "clip_img.npy")
    assert C.shape == (8, 512) and len(feat) == 8
    assert set(feat["qry_best"]) <= {q["id"] for q in load_queries()}


@pytest.mark.gpu
def test_real_text_encoder_unit_vectors(monkeypatch):
    monkeypatch.delenv("C4_FAKE_MODELS")
    _real_clip_ready()
    T = OpenClipTextEncoder().encode(["a cat", "a dog"])
    assert T.shape == (2, 512)
    np.testing.assert_allclose(np.linalg.norm(T, axis=1), 1.0, atol=1e-4)
