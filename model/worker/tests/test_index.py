import json
from pathlib import Path

import numpy as np
import pytest

from c4.cli import build_index
from c4.contracts import CAMS, ContractError, read_table
from c4.data.index import build_frames, cam_poses
from c4.data.nusc import NuscTables
from tests.fixtures.make_nuscenes import make_nuscenes


def _frames(root, **kw):
    t = NuscTables.load(root)
    return t, build_frames(t, root)


def test_frame_count_is_scenes_times_frames_times_cams(tmp_path):
    root = make_nuscenes(tmp_path, n_scenes=3, frames_per_scene=5)
    _, fr = _frames(root)
    assert fr["sample_token"].nunique() == 3 * 5
    assert len(fr) == 3 * 5 * 6
    assert set(fr["split"]) == {"pool"}


def test_frame_idx_follows_next_chain_from_zero(tmp_path):
    root = make_nuscenes(tmp_path, n_scenes=2, frames_per_scene=4)
    _, fr = _frames(root)
    for _, g in fr.groupby("scene_token"):
        per_sample = g.drop_duplicates("sample_token").sort_values("frame_idx")
        assert per_sample["frame_idx"].tolist() == [0, 1, 2, 3]
        assert per_sample["sample_token"].str.extract(r"_f(\d+)")[0].astype(int).tolist() \
            == [0, 1, 2, 3]
    assert fr["frame_idx"].dtype == np.int32 and fr["timestamp"].dtype == np.int64


def test_dropped_cams_are_absent(tmp_path):
    root = make_nuscenes(tmp_path, drop_cams={"scene0": ["CAM_BACK", "CAM_BACK_LEFT"]})
    _, fr = _frames(root)
    s0 = fr[fr["scene_name"] == "scene0"]
    assert not s0["cam"].isin(["CAM_BACK", "CAM_BACK_LEFT"]).any()
    assert s0.groupby("sample_token").size().eq(4).all()
    assert fr[fr["scene_name"] == "scene1"].groupby("sample_token").size().eq(6).all()


def test_frame_without_any_camera_file_is_dropped(tmp_path):
    root = make_nuscenes(tmp_path, drop_cams={"scene0": list(CAMS)})
    _, fr = _frames(root)
    assert set(fr["scene_name"]) == {"scene1"}


def test_img_path_is_relative_and_exists_and_no_lidar_or_sweeps(tmp_path):
    root = make_nuscenes(tmp_path)
    _, fr = _frames(root)
    assert len(fr)
    for p in fr["img_path"]:
        assert not Path(p).is_absolute() and p.startswith("samples/CAM_")
        assert (root / p).is_file()


def test_order_is_scene_frame_idx_then_cams_order(tmp_path):
    root = make_nuscenes(tmp_path, n_scenes=3, frames_per_scene=4)
    _, fr = _frames(root)
    cam_rank = fr["cam"].map({c: i for i, c in enumerate(CAMS)})
    keys = list(zip(fr["scene_token"], fr["frame_idx"], cam_rank))
    assert keys == sorted(keys)
    assert (fr.index == np.arange(len(fr))).all()


def test_scene_fields_filled(tmp_path):
    root = make_nuscenes(tmp_path, night_scenes=(0,))
    _, fr = _frames(root)
    s0 = fr[fr["scene_name"] == "scene0"].iloc[0]
    assert "Night" in s0["scene_desc"] and s0["scene_token"] == "sc0"
    assert s0["sd_token"].startswith("sd_")


def test_missing_required_table_names_it(tmp_path):
    root = make_nuscenes(tmp_path)
    (root / "v1.0-mini" / "sample.json").unlink()
    with pytest.raises(FileNotFoundError, match="sample"):
        NuscTables.load(root)


def test_multiple_version_dirs_is_contract_error(tmp_path):
    root = make_nuscenes(tmp_path)
    (root / "v1.0-trainval").mkdir()
    with pytest.raises(ContractError, match="v1.0-mini") as e:
        NuscTables.load(root)
    assert "v1.0-trainval" in str(e.value)


def test_has_annotations_flag_and_scene_samples_order(tmp_path):
    root = make_nuscenes(tmp_path, with_annotations=False)
    t = NuscTables.load(root)
    assert t.has_annotations is False
    assert [s["token"] for s in t.scene_samples("sc0")] == [f"scene0_f{i}" for i in range(6)]
    assert NuscTables.load(make_nuscenes(tmp_path / "b")).has_annotations is True


def test_build_frames_without_lidar_or_annotations(tmp_path):
    root = make_nuscenes(tmp_path, with_lidar=False, with_annotations=False)
    _, fr = _frames(root)
    assert len(fr) == 2 * 6 * 6


def test_cam_poses_match_calibration(tmp_path):
    root = make_nuscenes(tmp_path)
    t, fr = _frames(root)
    cp = cam_poses(t, fr)
    assert list(zip(cp["sample_token"], cp["cam"])) == list(zip(fr["sample_token"], fr["cam"]))
    row = cp[cp["cam"] == "CAM_FRONT"].iloc[0]
    assert len(row["translation"]) == 3 and len(row["rotation"]) == 4
    assert len(row["intrinsic"]) == 9
    assert abs(np.linalg.norm(row["rotation"]) - 1) < 1e-5
    assert row["intrinsic"][0] == pytest.approx(1266.4, rel=1e-5)
    back = cp[cp["cam"] == "CAM_BACK"].iloc[0]
    assert not np.allclose(back["rotation"], row["rotation"])


def test_cli_writes_both_tables_and_roundtrips(tmp_path, capsys):
    root = make_nuscenes(tmp_path / "ds")
    job = tmp_path / "job"
    assert build_index.main(["--data-root", str(root), "--job-dir", str(job)]) == 0
    fr = read_table(job / "index" / "frames.parquet", "frames")
    cp = read_table(job / "index" / "cam_poses.parquet", "cam_poses")
    assert len(fr) == len(cp) == 2 * 6 * 6
    assert len(cp["intrinsic"].iloc[0]) == 9
    assert str(len(fr)) in capsys.readouterr().out


def test_cli_exit_codes(tmp_path):
    root = make_nuscenes(tmp_path / "ds")
    (root / "v1.0-mini" / "sample_data.json").unlink()
    assert build_index.main(["--data-root", str(root), "--job-dir", str(tmp_path / "j")]) == 4
    root2 = make_nuscenes(tmp_path / "ds2")
    (root2 / "v1.0-test").mkdir()
    assert build_index.main(["--data-root", str(root2), "--job-dir", str(tmp_path / "j2")]) == 2


def test_cli_resume_skips_when_index_exists(tmp_path, capsys):
    root = make_nuscenes(tmp_path / "ds")
    job = tmp_path / "job"
    argv = ["--data-root", str(root), "--job-dir", str(job), "--resume"]
    assert build_index.main(argv) == 0
    mtime = (job / "index" / "frames.parquet").stat().st_mtime_ns
    capsys.readouterr()
    assert build_index.main(argv) == 0
    assert (job / "index" / "frames.parquet").stat().st_mtime_ns == mtime
    assert "skip" in capsys.readouterr().out


def test_list_columns_roundtrip_through_contracts(tmp_path):
    import pandas as pd

    from c4.contracts import write_table
    df = pd.DataFrame(dict(sample_token=["a"], cam=["CAM_FRONT"],
                           translation=[np.array([1, 2, 3], dtype=np.float32)],
                           rotation=[np.array([1, 0, 0, 0], dtype=np.float32)],
                           intrinsic=[np.arange(9, dtype=np.float32)]))
    write_table(df, tmp_path / "p.parquet", "cam_poses")
    back = read_table(tmp_path / "p.parquet", "cam_poses")
    assert list(back["translation"].iloc[0]) == [1, 2, 3]
    manifest = json.loads((tmp_path / "p.parquet.manifest.json").read_text())
    assert manifest["rows"] == 1
