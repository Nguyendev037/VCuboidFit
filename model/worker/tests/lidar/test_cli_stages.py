"""Stage CLI LiDAR (P01b): lidar_index rồi lidar_t0 trên nuScenes giả."""
import copy
import json

import numpy as np
import pandas as pd
import pytest

from c4.cli import lidar_index, lidar_t0
from c4.contracts import read_table
from c4.lidar import load_lidar_config
from tests.fixtures.make_nuscenes import make_nuscenes

N_SCENES, FRAMES_PER_SCENE = 3, 5
N = N_SCENES * FRAMES_PER_SCENE


@pytest.fixture
def cfg(monkeypatch):
    """Cấu hình thật, chỉ hạ min_points để 300 điểm/frame của fixture đều hợp lệ."""
    c = copy.deepcopy(load_lidar_config())
    c["filter"]["min_points"] = 50
    monkeypatch.setattr(lidar_t0, "load_lidar_config", lambda: c)
    return c


def _index(root, job, *extra):
    return lidar_index.main(["--data-root", str(root), "--job-dir", str(job), *extra])


def _t0(root, job, *extra):
    return lidar_t0.main(["--data-root", str(root), "--job-dir", str(job), *extra])


def test_two_stages_write_all_artifacts(tmp_path, cfg):
    root = make_nuscenes(tmp_path, n_scenes=N_SCENES, frames_per_scene=FRAMES_PER_SCENE)
    job = tmp_path / "job"
    assert _index(root, job) == 0
    index = read_table(job / "lidar" / "index.parquet", "lidar_index")
    assert len(index) == N and (index["split"] == "pool").all()
    assert _t0(root, job) == 0
    z0 = np.load(job / "lidar" / "z0.npy")
    assert z0.shape[0] == N and np.isfinite(z0).all()
    assert json.loads((job / "progress" / "t0.json").read_text(encoding="utf-8"))["done"] == N
    assert len(list((job / "media" / "bev").glob("*.png"))) == N
    filt = read_table(job / "lidar" / "filter.parquet", "lidar_filter")
    assert len(filt) == N and bool(filt["keep"].all())


def test_resume_skips_both_stages(tmp_path, cfg):
    root = make_nuscenes(tmp_path, n_scenes=N_SCENES, frames_per_scene=FRAMES_PER_SCENE)
    job = tmp_path / "job"
    assert _index(root, job) == 0
    assert _t0(root, job) == 0
    ip, zp = job / "lidar" / "index.parquet", job / "lidar" / "z0.npy"
    before = (ip.stat().st_mtime_ns, zp.stat().st_mtime_ns, zp.read_bytes())
    assert _index(root, job, "--resume") == 0
    assert _t0(root, job, "--resume") == 0
    assert (ip.stat().st_mtime_ns, zp.stat().st_mtime_ns, zp.read_bytes()) == before


def test_missing_data_root_exits_4(tmp_path, cfg, capsys):
    nodata = tmp_path / "nodata"
    assert _index(nodata, tmp_path / "job") == 4
    root = make_nuscenes(tmp_path, n_scenes=N_SCENES, frames_per_scene=FRAMES_PER_SCENE)
    job = tmp_path / "job"
    assert _index(root, job) == 0
    assert _t0(nodata, job) == 4
    assert "Không có frame LiDAR hợp lệ" in capsys.readouterr().err


def test_dataset_without_lidar_top_exits_4(tmp_path, cfg, capsys):
    root = make_nuscenes(tmp_path, n_scenes=N_SCENES, frames_per_scene=FRAMES_PER_SCENE,
                         with_lidar=False)
    assert _index(root, tmp_path / "job") == 4
    assert "LIDAR_TOP" in capsys.readouterr().err


def test_no_valid_frame_exits_4(tmp_path, cfg, monkeypatch, capsys):
    strict = copy.deepcopy(cfg)
    strict["filter"]["min_points"] = 10 ** 6
    monkeypatch.setattr(lidar_t0, "load_lidar_config", lambda: strict)
    root = make_nuscenes(tmp_path, n_scenes=N_SCENES, frames_per_scene=FRAMES_PER_SCENE)
    job = tmp_path / "job"
    assert _index(root, job) == 0
    assert _t0(root, job) == 4
    assert "Không có frame LiDAR hợp lệ" in capsys.readouterr().err


def test_index_writes_lidar_gt_when_dataset_has_annotations(tmp_path, cfg):
    root = make_nuscenes(tmp_path, n_scenes=N_SCENES, frames_per_scene=FRAMES_PER_SCENE,
                         with_annotations=True)
    job = tmp_path / "job"
    assert _index(root, job) == 0
    gt = read_table(job / "gt" / "gt_rare_lidar.parquet", "gt_rare_lidar")
    assert len(gt) == N and list(gt["sample_token"]) == list(
        read_table(job / "lidar" / "index.parquet", "lidar_index")["sample_token"])
    assert int(gt["n_boxes"].sum()) > 0  # category của fixture đều có trong gt.yaml
    cf = pd.read_csv(job / "gt" / "cell_freq.csv")
    assert {"split", "cell", "n_frames", "freq"} <= set(cf.columns) and len(cf) > 0
    assert (job / "gt" / "gt_rare_lidar.parquet.manifest.json").is_file()


def test_index_skips_lidar_gt_without_annotations(tmp_path, cfg, capsys):
    root = make_nuscenes(tmp_path, n_scenes=N_SCENES, frames_per_scene=FRAMES_PER_SCENE,
                         with_annotations=False)
    job = tmp_path / "job"
    assert _index(root, job) == 0
    assert not (job / "gt").exists()
    assert "bỏ qua gt/" in capsys.readouterr().out


def test_index_resume_still_writes_missing_gt(tmp_path, cfg):
    root = make_nuscenes(tmp_path, n_scenes=N_SCENES, frames_per_scene=FRAMES_PER_SCENE)
    job = tmp_path / "job"
    assert _index(root, job) == 0
    (job / "gt" / "gt_rare_lidar.parquet").unlink()
    assert _index(root, job, "--resume") == 0
    assert (job / "gt" / "gt_rare_lidar.parquet").is_file()
