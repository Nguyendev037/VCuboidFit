import json
import logging

import numpy as np
import pytest
import torch
from torch.utils.data import Dataset

from c4.data.index import build_frames
from c4.data.nusc import NuscTables
from c4.extract.base import Images, Progress, concat_shards, run_shards
from c4.extract.fake import fake_detect, fake_embed, fake_models_enabled
from c4.extract.quality import quality_metrics
from tests.fixtures.make_nuscenes import make_nuscenes


class Counter(Dataset):
    """Item i = tensor([i]); ok luôn True."""

    def __init__(self, n):
        self.n = n

    def __len__(self):
        return self.n

    def __getitem__(self, i):
        return torch.tensor([float(i)]), True


def _double(x):
    return (x * 2).numpy()


def _prog(tmp_path, total):
    return Progress(tmp_path / "job", "dino", total)


# ---------- Images ----------

def test_images_returns_tensor_and_ok(tmp_path):
    root = make_nuscenes(tmp_path)
    fr = build_frames(NuscTables.load(root), root)
    ds = Images(fr, root, (90, 160))
    x, ok = ds[0]
    assert x.shape == (3, 90, 160) and x.dtype == torch.float32 and ok is True
    assert 0.0 <= float(x.min()) and float(x.max()) <= 1.0 and float(x.mean()) > 0
    assert len(ds) == len(fr)


def test_corrupt_jpeg_gives_zero_tensor_ok_false_and_logs_token(tmp_path, caplog):
    bad = "samples/CAM_FRONT/scene1_f2__CAM_FRONT.jpg"
    root = make_nuscenes(tmp_path, corrupt=[bad])
    fr = build_frames(NuscTables.load(root), root)
    i = int(np.flatnonzero(fr["img_path"] == bad)[0])
    ds = Images(fr, root, (90, 160))
    with caplog.at_level(logging.WARNING):
        x, ok = ds[i]
        _, ok_good = ds[0]
    assert ok is False and ok_good is True
    assert x.shape == (3, 90, 160) and float(x.abs().sum()) == 0.0
    assert "scene1_f2" in caplog.text


def test_missing_file_is_also_not_ok(tmp_path):
    root = make_nuscenes(tmp_path)
    fr = build_frames(NuscTables.load(root), root)
    (root / fr["img_path"].iloc[3]).unlink()
    x, ok = Images(fr, root, (90, 160))[3]
    assert ok is False and float(x.abs().sum()) == 0.0


# ---------- run_shards / concat_shards ----------

def test_shards_written_and_concat(tmp_path):
    out = tmp_path / "sh"
    run_shards(_double, Counter(10), out, bs=3, shard=4, workers=0, progress=_prog(tmp_path, 10))
    assert sorted(p.name for p in out.glob("shard_*.npy")) == \
        ["shard_00000.npy", "shard_00001.npy", "shard_00002.npy"]
    arr = concat_shards(out)
    assert arr.shape == (10, 1) and arr[:, 0].tolist() == [2.0 * i for i in range(10)]


def test_resume_continues_from_last_shard_and_is_byte_identical(tmp_path):
    ref = tmp_path / "ref"
    run_shards(_double, Counter(10), ref, bs=2, shard=4, workers=0,
               progress=_prog(tmp_path / "r", 10))

    def crashing(x):
        if float(x.max()) >= 4:  # shard 1 bắt đầu → "mất điện"
            raise RuntimeError("laptop sleeps")
        return _double(x)

    out = tmp_path / "out"
    with pytest.raises(RuntimeError):
        run_shards(crashing, Counter(10), out, bs=2, shard=4, workers=0,
                   progress=_prog(tmp_path / "a", 10))
    assert [p.name for p in out.glob("shard_*.npy")] == ["shard_00000.npy"]

    seen = []

    def recording(x):
        seen.extend(x[:, 0].tolist())
        return _double(x)

    prog = _prog(tmp_path / "b", 10)
    run_shards(recording, Counter(10), out, bs=2, shard=4, workers=0, progress=prog)
    assert seen[0] == 4.0 and min(seen) == 4.0  # không làm lại shard 0
    assert concat_shards(out).tobytes() == concat_shards(ref).tobytes()
    for p in ref.glob("shard_*.npy"):
        assert (out / p.name).read_bytes() == p.read_bytes()
    assert json.loads((tmp_path / "b" / "job" / "progress" / "dino.json").read_text())["done"] == 10


def test_oom_halves_batch_and_completes(tmp_path):
    sizes = []

    def fn(x):
        sizes.append(len(x))
        if len(x) > 4:
            raise torch.cuda.OutOfMemoryError("simulated")
        return _double(x)

    out = tmp_path / "sh"
    prog = _prog(tmp_path, 20)
    run_shards(fn, Counter(20), out, bs=16, shard=16, workers=0, progress=prog)
    assert max(sizes[sizes.index(4):]) == 4 and 16 in sizes and 8 in sizes
    assert concat_shards(out)[:, 0].tolist() == [2.0 * i for i in range(20)]
    prog.flush()
    assert json.loads((tmp_path / "job" / "progress" / "dino.json").read_text())["done"] == 20


def test_oom_at_batch_one_exits_3(tmp_path):
    def always_oom(x):
        raise torch.cuda.OutOfMemoryError("simulated")

    with pytest.raises(SystemExit) as e:
        run_shards(always_oom, Counter(4), tmp_path / "sh", bs=2, shard=4, workers=0,
                   progress=_prog(tmp_path, 4))
    assert e.value.code == 3


def test_concat_shards_empty_dir_raises(tmp_path):
    (tmp_path / "sh").mkdir()
    with pytest.raises(FileNotFoundError):
        concat_shards(tmp_path / "sh")


# ---------- Progress ----------

def test_progress_file_has_done_total_and_fields(tmp_path):
    p = Progress(tmp_path / "job", "det", 50)
    p.advance(7)
    p.flush()
    d = json.loads((tmp_path / "job" / "progress" / "det.json").read_text())
    assert d["done"] == 7 and d["total"] == 50
    assert isinstance(d["peak_vram_mb"], int) and d["peak_vram_mb"] >= 0
    assert "T" in d["updated_at"]


def test_progress_throttles_writes_to_every_2s(tmp_path, monkeypatch):
    import c4.extract.base as base
    now = [1000.0]
    monkeypatch.setattr(base.time, "monotonic", lambda: now[0])
    p = Progress(tmp_path / "job", "clip", 100)
    f = tmp_path / "job" / "progress" / "clip.json"
    p.advance(1)
    assert json.loads(f.read_text())["done"] == 1
    now[0] += 0.5
    p.advance(1)
    assert json.loads(f.read_text())["done"] == 1  # chưa tới 2 s
    now[0] += 2.0
    p.advance(1)
    assert json.loads(f.read_text())["done"] == 3


# ---------- quality ----------

def test_quality_of_black_image_is_zero():
    assert quality_metrics(np.zeros((252, 448), np.uint8)) == (0.0, 0.0)


def test_quality_bright_and_blur_ordering():
    rng = np.random.default_rng(0)
    sharp = rng.integers(0, 256, (252, 448), dtype=np.uint8)
    flat = np.full((252, 448), 200, np.uint8)
    qb_s, bl_s = quality_metrics(sharp)
    qb_f, bl_f = quality_metrics(flat)
    assert qb_f == pytest.approx(200.0) and bl_f == 0.0
    assert bl_s > 100 and 100 < qb_s < 160


# ---------- fakes ----------

def test_fake_models_enabled_follows_env(monkeypatch):
    monkeypatch.delenv("C4_FAKE_MODELS", raising=False)
    assert fake_models_enabled() is False
    monkeypatch.setenv("C4_FAKE_MODELS", "1")
    assert fake_models_enabled() is True
    monkeypatch.setenv("C4_FAKE_MODELS", "0")
    assert fake_models_enabled() is False


def test_fake_embed_is_deterministic_unit_vectors():
    paths = ["a/b.jpg", "a/c.jpg", "a/b.jpg"]
    e = fake_embed(paths, 16, seed=1)
    assert e.shape == (3, 16)
    np.testing.assert_allclose(np.linalg.norm(e, axis=1), 1.0, atol=1e-5)
    np.testing.assert_array_equal(e[0], e[2])
    assert not np.allclose(e[0], e[1])
    assert not np.allclose(e[0], fake_embed(paths, 16, seed=2)[0])
    np.testing.assert_array_equal(e, fake_embed(paths, 16, seed=1))


def test_fake_detect_is_deterministic_and_well_formed():
    paths = [f"samples/CAM_FRONT/{i}.jpg" for i in range(20)]
    d1, d2 = fake_detect(paths), fake_detect(paths)
    assert d1 == d2 and len(d1) == 20
    assert any(len(x) >= 1 for x in d1)
    for dets in d1:
        for cls, conf, x1, y1, x2, y2 in dets:
            assert isinstance(cls, int) and 0.05 <= conf <= 1.0
            assert 0 <= x1 < x2 <= 1600 and 0 <= y1 < y2 <= 900


def test_progress_flush_retries_when_reader_holds_file(tmp_path, monkeypatch):
    """Windows: os.replace lên file đang được mở đọc ⇒ PermissionError; không được làm sập stage."""
    import c4.extract.base as base
    real, calls = base.os.replace, [0]

    def flaky(src, dst):
        calls[0] += 1
        if calls[0] < 3:
            raise PermissionError("[WinError 5] Access is denied")
        return real(src, dst)

    monkeypatch.setattr(base.os, "replace", flaky)
    monkeypatch.setattr(base.time, "sleep", lambda s: None)
    p = Progress(tmp_path / "job", "clip", 5)
    p.advance(2)
    assert calls[0] == 3
    assert json.loads((tmp_path / "job" / "progress" / "clip.json").read_text())["done"] == 2


def test_progress_flush_never_raises_when_file_stays_locked(tmp_path, monkeypatch):
    import c4.extract.base as base

    def locked(src, dst):
        raise PermissionError("[WinError 5] Access is denied")

    monkeypatch.setattr(base.os, "replace", locked)
    monkeypatch.setattr(base.time, "sleep", lambda s: None)
    p = Progress(tmp_path / "job", "clip", 5)
    p.advance(1)  # tiến độ chỉ là thông tin phụ: bỏ lần ghi này, không raise
    p.flush()
