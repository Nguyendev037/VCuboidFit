import numpy as np
import pytest
from PIL import Image

from c4.cli import build_index
from c4.contracts import ContractError
from c4.data.index import build_frames
from c4.data.media import export_lidar, lidar_to_bin, make_thumbs
from c4.data.nusc import NuscTables
from tests.fixtures.make_nuscenes import N_LIDAR_PTS, make_nuscenes


def _load(root):
    t = NuscTables.load(root)
    return t, build_frames(t, root)


def test_thumbnails_exist_with_expected_size_and_name(tmp_path):
    root = make_nuscenes(tmp_path / "ds", n_scenes=1, frames_per_scene=2)
    _, fr = _load(root)
    out = tmp_path / "thumbs"
    assert make_thumbs(fr, root, out) == len(fr) == 12
    f = out / "scene0_f0_CAM_FRONT.webp"
    assert f.is_file()
    with Image.open(f) as im:
        assert im.size == (320, 180) and im.format == "WEBP"
    assert len(list(out.glob("*.webp"))) == 12
    assert not list(out.glob("*.tmp"))


def test_thumbnail_rerun_does_not_rewrite(tmp_path):
    root = make_nuscenes(tmp_path / "ds", n_scenes=1, frames_per_scene=2)
    _, fr = _load(root)
    out = tmp_path / "thumbs"
    make_thumbs(fr, root, out)
    before = {p.name: p.stat().st_mtime_ns for p in out.glob("*.webp")}
    assert make_thumbs(fr, root, out) == 0
    assert {p.name: p.stat().st_mtime_ns for p in out.glob("*.webp")} == before


def test_thumbnail_resume_fills_only_the_missing_ones(tmp_path):
    root = make_nuscenes(tmp_path / "ds", n_scenes=1, frames_per_scene=2)
    _, fr = _load(root)
    out = tmp_path / "thumbs"
    make_thumbs(fr, root, out)
    (out / "scene0_f1_CAM_BACK.webp").unlink()
    assert make_thumbs(fr, root, out, workers=2) == 1
    assert (out / "scene0_f1_CAM_BACK.webp").is_file()


def test_thumbnail_keeps_image_content(tmp_path):
    root = make_nuscenes(tmp_path / "ds", n_scenes=1, frames_per_scene=1)
    _, fr = _load(root)
    make_thumbs(fr, root, tmp_path / "t")
    with Image.open(root / "samples/CAM_FRONT/scene0_f0__CAM_FRONT.jpg") as src, \
            Image.open(tmp_path / "t" / "scene0_f0_CAM_FRONT.webp") as th:
        want = np.asarray(src.convert("RGB").resize((320, 180))).mean(axis=(0, 1))
        got = np.asarray(th.convert("RGB")).mean(axis=(0, 1))
    assert np.abs(want - got).max() < 12  # ảnh phẳng 1 màu: màu trung bình giữ nguyên


def test_corrupt_jpeg_is_skipped_not_fatal(tmp_path, capsys):
    bad = "samples/CAM_FRONT/scene0_f0__CAM_FRONT.jpg"
    root = make_nuscenes(tmp_path / "ds", n_scenes=1, frames_per_scene=1, corrupt=[bad])
    t = NuscTables.load(root)
    fr = build_frames(t, root)  # file 0 byte vẫn "tồn tại" nên nằm trong index
    out = tmp_path / "t"
    assert make_thumbs(fr, root, out) == len(fr) - 1
    assert not (out / "scene0_f0_CAM_FRONT.webp").exists()
    assert "scene0_f0" in capsys.readouterr().err


def _calib(**kw):
    h = float(np.sqrt(0.5))
    return dict(translation=[1.0, 2.0, 3.0], rotation=[h, 0.0, 0.0, h], **kw)  # yaw 90°


def _write_pcd(path, pts):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(np.asarray(pts, dtype=np.float32).tobytes())


def test_lidar_bin_size_and_known_point_through_nonidentity_calib(tmp_path):
    pcd = tmp_path / "a.pcd.bin"
    # (x, y, z, intensity, ring): (1,0,0) quay 90° quanh z → (0,1,0), cộng t → (1,3,3)
    _write_pcd(pcd, [[1, 0, 0, 7, 0], [0, 0, 0, 3, 1], [0, 2, 0, 5, 2]])
    out = tmp_path / "lidar" / "a.bin"
    assert lidar_to_bin(pcd, _calib(), out) == 3
    assert out.stat().st_size == 3 * 4 * 2
    arr = np.fromfile(out, dtype=np.float16).reshape(3, 4)
    assert np.allclose(arr[0], [1, 3, 3, 7], atol=1e-3)
    assert np.allclose(arr[1], [1, 2, 3, 3], atol=1e-3)  # gốc cảm biến → t_calib
    assert np.allclose(arr[2], [-1, 2, 3, 5], atol=1e-3)  # (0,2,0) → (-2,0,0) + t


def test_lidar_bin_rejects_file_with_wrong_size(tmp_path):
    pcd = tmp_path / "bad.pcd.bin"
    pcd.write_bytes(b"\x00" * 21)
    with pytest.raises(ContractError):
        lidar_to_bin(pcd, _calib(), tmp_path / "o.bin")
    assert not (tmp_path / "o.bin").exists()


def test_export_lidar_writes_one_bin_per_sample_in_ego_frame(tmp_path):
    root = make_nuscenes(tmp_path / "ds", n_scenes=2, frames_per_scene=3)
    t, fr = _load(root)
    out = tmp_path / "lidar"
    assert export_lidar(t, fr, root, out) == 6
    f = out / "scene1_f2.bin"
    assert f.stat().st_size == N_LIDAR_PTS * 4 * 2
    src = np.fromfile(root / "samples/LIDAR_TOP/scene1_f2__LIDAR_TOP.pcd.bin",
                      dtype=np.float32).reshape(-1, 5)
    got = np.fromfile(f, dtype=np.float16).reshape(-1, 4)
    # calib LIDAR_TOP giả: quay đơn vị, t = (0.9, 0, 1.8)
    assert np.allclose(got[:, :3], src[:, :3] + [0.9, 0.0, 1.8], atol=0.1)  # fp16 ở |x| ≤ 32
    assert np.allclose(got[:, 3], src[:, 3], atol=0.05)


def test_export_lidar_resume_skips_existing(tmp_path):
    root = make_nuscenes(tmp_path / "ds", n_scenes=1, frames_per_scene=2)
    t, fr = _load(root)
    out = tmp_path / "lidar"
    export_lidar(t, fr, root, out)
    mtimes = {p.name: p.stat().st_mtime_ns for p in out.glob("*.bin")}
    assert export_lidar(t, fr, root, out) == 0
    assert {p.name: p.stat().st_mtime_ns for p in out.glob("*.bin")} == mtimes


def test_export_lidar_without_lidar_is_noop(tmp_path):
    root = make_nuscenes(tmp_path / "ds", with_lidar=False)
    t, fr = _load(root)
    out = tmp_path / "lidar"
    assert export_lidar(t, fr, root, out) == 0
    assert not out.exists()


def test_export_lidar_skips_sample_whose_pcd_file_is_missing(tmp_path):
    root = make_nuscenes(tmp_path / "ds", n_scenes=1, frames_per_scene=3)
    (root / "samples/LIDAR_TOP/scene0_f1__LIDAR_TOP.pcd.bin").unlink()
    t, fr = _load(root)
    assert export_lidar(t, fr, root, tmp_path / "lidar") == 2
    assert not (tmp_path / "lidar" / "scene0_f1.bin").exists()


def test_build_index_writes_media(tmp_path):
    root = make_nuscenes(tmp_path / "ds", n_scenes=2, frames_per_scene=3)
    job = tmp_path / "job"
    assert build_index.main(["--data-root", str(root), "--job-dir", str(job)]) == 0
    assert len(list((job / "media" / "thumbs").glob("*.webp"))) == 2 * 3 * 6
    assert len(list((job / "media" / "lidar").glob("*.bin"))) == 2 * 3
    assert (job / "gt" / "gt_rare.parquet").is_file()


def test_build_index_without_lidar_writes_no_lidar_dir_and_exits_zero(tmp_path):
    root = make_nuscenes(tmp_path / "ds", with_lidar=False, n_scenes=1, frames_per_scene=2)
    job = tmp_path / "job"
    assert build_index.main(["--data-root", str(root), "--job-dir", str(job)]) == 0
    assert (job / "media" / "thumbs").is_dir()
    assert not (job / "media" / "lidar").exists()


def test_build_index_resume_after_index_still_produces_media(tmp_path):
    root = make_nuscenes(tmp_path / "ds", n_scenes=1, frames_per_scene=2)
    job = tmp_path / "job"
    argv = ["--data-root", str(root), "--job-dir", str(job)]
    assert build_index.main(argv) == 0
    for p in (job / "media" / "thumbs").glob("*scene0_f1*"):
        p.unlink()  # giả lập tiến trình chết giữa chừng sau khi index đã ghi
    assert build_index.main([*argv, "--resume"]) == 0
    assert len(list((job / "media" / "thumbs").glob("*.webp"))) == 2 * 6


def test_build_index_limit_limits_thumbnails(tmp_path):
    root = make_nuscenes(tmp_path / "ds", n_scenes=2, frames_per_scene=3)
    job = tmp_path / "job"
    assert build_index.main(["--data-root", str(root), "--job-dir", str(job),
                             "--limit", "6"]) == 0
    assert len(list((job / "media" / "thumbs").glob("*.webp"))) == 6
    assert len(list((job / "media" / "lidar").glob("*.bin"))) == 1
