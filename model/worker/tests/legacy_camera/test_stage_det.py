import json
from types import SimpleNamespace

import numpy as np
import pandas as pd
import pytest
import torch

from c4.cli import extract_det
from c4.contracts import write_table
from c4.data.index import build_frames
from c4.data.nusc import NuscTables
from c4.extract.det import align_results
from c4.extract.det import extract_det as run_det
from c4.extract.dino import weights_dir
from tests.fixtures.make_nuscenes import make_nuscenes

FEAT_COLS = ["sample_token", "cam", "det_n", "det_n_conf", "det_ent", "det_tmp", "unc"]
DET_COLS = ["sample_token", "cam", "cls", "conf", "x1", "y1", "x2", "y2"]


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
    return extract_det.main(["--data-root", str(root), "--job-dir", str(job),
                             "--device", "cpu", *extra])


def _spy(inner):
    calls = []

    def predictor(paths, batch):
        calls.append((list(paths), batch))
        return inner(paths, batch)

    return predictor, calls


def _empty(paths, batch):
    return [np.zeros((0, 6), np.float32) for _ in paths]


def test_outputs_follow_contract_columns_and_pixel_range(tmp_path):
    root, job, frames = _job(tmp_path)
    assert _cli(root, job) == 0
    det = pd.read_parquet(job / "cache" / "detections.parquet")
    feat = pd.read_parquet(job / "cache" / "feat_det.parquet")
    assert list(det.columns) == DET_COLS and list(feat.columns) == FEAT_COLS
    assert str(det["cls"].dtype) == "int16" and str(det["conf"].dtype) == "float32"
    assert len(det) > 0 and det["conf"].between(0.05, 1.0).all()
    assert (det["x1"] >= 0).all() and (det["x2"] <= 1600).all() and (det["x1"] < det["x2"]).all()
    assert (det["y1"] >= 0).all() and (det["y2"] <= 900).all() and (det["y1"] < det["y2"]).all()
    assert (feat["sample_token"] == frames["sample_token"]).all()
    assert (feat["cam"] == frames["cam"]).all()
    assert feat["det_n"].sum() == len(det)
    assert np.isfinite(feat[["det_ent", "det_tmp", "unc"]].to_numpy()).all()
    assert json.loads((job / "progress" / "det.json").read_text())["done"] == len(frames)


def test_every_frame_row_present_even_with_zero_detections(tmp_path):
    root, job, frames = _job(tmp_path)
    feat = run_det(job, root, device="cpu", predictor=_empty)[1]
    det = pd.read_parquet(job / "cache" / "detections.parquet")
    assert len(feat) == len(frames) and len(det) == 0 and list(det.columns) == DET_COLS
    assert (feat["det_n"] == 0).all() and (feat["det_tmp"] == 0).all() and (feat["unc"] == 0).all()


def test_frames_without_detections_mixed_with_detected_ones(tmp_path):
    root, job, frames = _job(tmp_path)

    def only_front(paths, batch):
        return [np.array([[2, 0.9, 10, 20, 300, 200]], np.float32) if "CAM_FRONT/" in p
                else np.zeros((0, 6), np.float32) for p in paths]

    feat = run_det(job, root, device="cpu", predictor=only_front)[1]
    assert len(feat) == len(frames)
    front = feat["cam"] == "CAM_FRONT"
    assert (feat.loc[front, "det_n"] == 1).all() and (feat.loc[~front, "det_n"] == 0).all()


def test_det_tmp_is_zero_on_first_frame_of_each_scene(tmp_path):
    root, job, frames = _job(tmp_path)
    assert _cli(root, job) == 0
    feat = pd.read_parquet(job / "cache" / "feat_det.parquet")
    first = (frames["frame_idx"] == 0).to_numpy()
    assert first.sum() == 12 and (feat.loc[first, "det_tmp"] == 0).all()
    assert (feat.loc[~first, "det_tmp"] > 0).any()  # model giả đổi số box giữa các frame


def test_limit_processes_only_first_n_images(tmp_path):
    root, job, frames = _job(tmp_path)
    assert _cli(root, job, "--limit", "3") == 0
    feat = pd.read_parquet(job / "cache" / "feat_det.parquet")
    assert feat["sample_token"].tolist() == frames["sample_token"].head(3).tolist()
    assert json.loads((job / "progress" / "det.json").read_text())["total"] == 3


def test_resume_skips_finished_chunks(tmp_path):
    root, job, frames = _job(tmp_path)
    pred, calls = _spy(lambda paths, b: [np.zeros((1, 6), np.float32) + [1, .5, 1, 1, 9, 9]
                                         for _ in paths])
    run_det(job, root, device="cpu", predictor=pred, chunk=16)
    n_chunks = -(-len(frames) // 16)
    assert len(calls) == n_chunks >= 4
    ref_det = pd.read_parquet(job / "cache" / "detections.parquet")
    ref_feat = pd.read_parquet(job / "cache" / "feat_det.parquet")

    calls.clear()
    run_det(job, root, device="cpu", predictor=pred, chunk=16, resume=True)
    assert calls == []  # không chunk nào chạy lại

    (job / "cache" / "det_shards" / f"chunk_{n_chunks - 1:05d}.parquet").unlink()
    run_det(job, root, device="cpu", predictor=pred, chunk=16, resume=True)
    assert len(calls) == 1 and calls[0][0] == frames["img_path"].tolist()[(n_chunks - 1) * 16:]
    pd.testing.assert_frame_equal(pd.read_parquet(job / "cache" / "detections.parquet"), ref_det)
    pd.testing.assert_frame_equal(pd.read_parquet(job / "cache" / "feat_det.parquet"), ref_feat)


def test_resume_ignores_chunks_from_a_different_limit(tmp_path):
    root, job, frames = _job(tmp_path)
    assert _cli(root, job) == 0
    ref = pd.read_parquet(job / "cache" / "detections.parquet")
    assert _cli(root, job, "--limit", "3") == 0
    assert _cli(root, job, "--resume") == 0
    assert len(pd.read_parquet(job / "cache" / "feat_det.parquet")) == len(frames)
    pd.testing.assert_frame_equal(pd.read_parquet(job / "cache" / "detections.parquet"), ref)


def test_oom_halves_batch_and_retries_the_chunk(tmp_path):
    root, job, frames = _job(tmp_path)
    seen = []

    def fn(paths, batch):
        seen.append(batch)
        if batch > 4:
            raise torch.cuda.OutOfMemoryError("simulated")
        return _empty(paths, batch)

    run_det(job, root, device="cpu", predictor=fn, chunk=16)  # profile local-4060: batch 16
    assert seen[:3] == [16, 8, 4] and set(seen[2:]) == {4}  # batch đã giảm được giữ cho chunk sau
    assert len(pd.read_parquet(job / "cache" / "feat_det.parquet")) == len(frames)


def test_oom_at_batch_one_exits_3(tmp_path):
    root, job, _ = _job(tmp_path)

    def always_oom(paths, batch):
        raise torch.cuda.OutOfMemoryError("simulated")

    with pytest.raises(SystemExit) as e:
        run_det(job, root, device="cpu", predictor=always_oom, chunk=16)
    assert e.value.code == 3


def test_align_results_by_path_when_unreadable_image_is_skipped():
    paths = ["/d/a.jpg", "/d/b.jpg", "/d/c.jpg"]

    def res(p, rows):
        b = SimpleNamespace(cls=torch.tensor([r[0] for r in rows], dtype=torch.float32),
                            conf=torch.tensor([r[1] for r in rows]),
                            xyxy=torch.tensor([r[2:] for r in rows], dtype=torch.float32))
        return SimpleNamespace(path=p, boxes=b)

    # ultralytics bỏ qua b.jpg (không đọc được): kết quả ngắn hơn danh sách đầu vào
    out = align_results(paths, [res("/d/a.jpg", [(3, .9, 1, 2, 3, 4)]),
                                res("/d/c.jpg", [(0, .4, 5, 6, 7, 8), (2, .6, 9, 9, 20, 20)])])
    assert [len(o) for o in out] == [1, 0, 2]
    assert out[0].tolist() == [[3, pytest.approx(.9), 1, 2, 3, 4]]
    assert out[1].shape == (0, 6) and out[2][1].tolist()[0] == 2


def test_missing_frames_table_exits_4(tmp_path, capsys):
    assert _cli(tmp_path / "nodata", tmp_path / "emptyjob") == 4
    assert "frames.parquet" in capsys.readouterr().err


def test_missing_weights_exits_4_and_names_fetch_command(tmp_path, monkeypatch, capsys):
    monkeypatch.delenv("C4_FAKE_MODELS")
    monkeypatch.setenv("C4_WEIGHTS_DIR", str(tmp_path / "no_weights"))
    root, job, _ = _job(tmp_path)
    assert _cli(root, job) == 4
    assert "python scripts/fetch_weights.py" in capsys.readouterr().err


@pytest.mark.gpu
def test_real_yolo_on_eight_images(tmp_path, monkeypatch):
    monkeypatch.delenv("C4_FAKE_MODELS")
    pt = weights_dir() / "yolo11m.pt"
    if not torch.cuda.is_available():
        pytest.skip("không có CUDA")
    if not pt.is_file():
        pytest.skip(f"thiếu trọng số {pt} (chạy scripts/fetch_weights.py)")
    root, job, _ = _job(tmp_path)
    det, feat = run_det(job, root, limit=8, device="cuda")
    assert len(feat) == 8 and set(det.columns) == set(DET_COLS)
