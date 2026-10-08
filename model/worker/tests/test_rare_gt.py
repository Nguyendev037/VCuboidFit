import json

import numpy as np
import pandas as pd
import pytest

from c4.cli import build_index
from c4.contracts import CAMS, read_table
from c4.data.index import build_frames
from c4.data.nusc import NuscTables
from c4.data.project import project_boxes
from c4.data.rare_gt import group_frequencies, load_rare_def, rare_flags
from tests.fixtures.make_nuscenes import IMG_H, IMG_W, make_nuscenes

GROUPS = ["A_night", "A_rain", "B_rare_class", "C_crowd", "C_low_vis", "C_far"]


def _load(root):
    t = NuscTables.load(root)
    return t, build_frames(t, root)


def _rare_def(**over):
    d = load_rare_def()
    d.update(over)
    return d


def test_load_rare_def_has_documented_keys():
    d = load_rare_def()
    for k in ("night_keywords", "rain_keywords", "rare_classes", "crowd_min_peds",
              "low_vis_level", "far_max_lidar_pts", "rare_max_freq"):
        assert k in d


def test_rare_flags_one_row_per_sample_with_contract_columns(tmp_path):
    root = make_nuscenes(tmp_path, n_scenes=2, frames_per_scene=4)
    t, fr = _load(root)
    flags = rare_flags(t, fr, _rare_def())
    assert list(flags["sample_token"]) == list(fr["sample_token"].drop_duplicates())
    assert set(GROUPS) | {"is_rare"} <= set(flags.columns)
    assert flags["is_rare"].dtype == bool


def test_night_scene_flags_a_night_and_rain_scene_flags_a_rain(tmp_path):
    root = make_nuscenes(tmp_path, n_scenes=3, night_scenes=(0,), rain_scenes=(1,))
    t, fr = _load(root)
    flags = rare_flags(t, fr, _rare_def()).set_index("sample_token")
    assert flags.loc["scene0_f0", "A_night"] and not flags.loc["scene0_f0", "A_rain"]
    assert flags.loc["scene1_f0", "A_rain"] and not flags.loc["scene1_f0", "A_night"]
    assert not flags.loc["scene2_f0", ["A_night", "A_rain"]].any()


def test_keyword_match_is_case_insensitive(tmp_path):
    root = make_nuscenes(tmp_path, n_scenes=1, night_scenes=(0,))  # mô tả "Parked cars, Night"
    t, fr = _load(root)
    assert rare_flags(t, fr, _rare_def(night_keywords=["NIGHT"]))["A_night"].all()


def test_motorcycle_flags_b_rare_class_by_prefix(tmp_path):
    root = make_nuscenes(tmp_path, n_scenes=1, frames_per_scene=3)
    t, fr = _load(root)
    assert rare_flags(t, fr, _rare_def())["B_rare_class"].all()
    assert not rare_flags(t, fr, _rare_def(rare_classes=["animal"]))["B_rare_class"].any()
    assert rare_flags(t, fr, _rare_def(rare_classes=["vehicle"]))["B_rare_class"].all()


def test_box_groups_follow_thresholds(tmp_path):
    root = make_nuscenes(tmp_path, n_scenes=1, frames_per_scene=3)  # 1 người (50 pts, vis 4)
    t, fr = _load(root)
    base = rare_flags(t, fr, _rare_def())
    assert not base[["C_crowd", "C_low_vis", "C_far"]].any().any()
    assert rare_flags(t, fr, _rare_def(crowd_min_peds=1))["C_crowd"].all()
    assert not rare_flags(t, fr, _rare_def(crowd_min_peds=2))["C_crowd"].any()
    assert rare_flags(t, fr, _rare_def(low_vis_level="4"))["C_low_vis"].all()
    assert rare_flags(t, fr, _rare_def(far_max_lidar_pts=20))["C_far"].all()  # xe máy 20 điểm
    assert not rare_flags(t, fr, _rare_def(far_max_lidar_pts=19))["C_far"].any()


def test_far_excludes_boxes_with_zero_lidar_points(tmp_path):
    root = make_nuscenes(tmp_path, n_scenes=1, frames_per_scene=2)
    ann = root / "v1.0-mini" / "sample_annotation.json"
    rows = json.loads(ann.read_text())
    for r in rows:
        r["num_lidar_pts"] = 0
    ann.write_text(json.dumps(rows))
    t, fr = _load(root)
    assert not rare_flags(t, fr, _rare_def(far_max_lidar_pts=100))["C_far"].any()


def test_rare_max_freq_excludes_group_present_in_every_frame(tmp_path):
    root = make_nuscenes(tmp_path, n_scenes=2, frames_per_scene=6, night_scenes=(0, 1))
    t, fr = _load(root)
    flags = rare_flags(t, fr, _rare_def())
    assert flags["A_night"].all()  # cột cờ vẫn ghi
    assert not flags["is_rare"].any()  # nhưng không tính vào is_rare
    freq = group_frequencies(flags)
    assert freq["A_night"] == 1.0 and freq["B_rare_class"] == 1.0
    assert set(freq) == set(GROUPS)


def test_is_rare_is_or_over_groups_under_threshold(tmp_path):
    root = make_nuscenes(tmp_path, n_scenes=2, frames_per_scene=6, night_scenes=(0,))
    t, fr = _load(root)
    flags = rare_flags(t, fr, _rare_def(rare_max_freq=0.6)).set_index("sample_token")
    assert group_frequencies(flags.reset_index())["A_night"] == 0.5
    assert flags.loc[[f"scene0_f{i}" for i in range(6)], "is_rare"].all()  # đêm 50 % ≤ 0.6
    assert not flags.loc[[f"scene1_f{i}" for i in range(6)], "is_rare"].any()  # B = 100 % bị loại


def test_group_frequencies_is_fraction_of_samples():
    df = pd.DataFrame({g: [True, False, False, False] for g in GROUPS}
                      | {"sample_token": list("abcd"), "is_rare": False})
    assert all(v == 0.25 for v in group_frequencies(df).values())


def test_project_boxes_front_cam_sees_both_boxes_near_centre(tmp_path):
    root = make_nuscenes(tmp_path, n_scenes=1, frames_per_scene=2)
    t, fr = _load(root)
    b2d, b3d = project_boxes(t, fr)
    front = b2d[(b2d["cam"] == "CAM_FRONT") & (b2d["sample_token"] == "scene0_f0")]
    assert set(front["category"]) == {"human.pedestrian.adult", "vehicle.motorcycle"}
    ped = front[front["category"] == "human.pedestrian.adult"].iloc[0]
    cx = (ped["x1"] + ped["x2"]) / 2
    # người cao 1.8 m ở (10, 0, 0.9) ego; camera ở z = 1.5 ⇒ tâm hộp thấp hơn trục ảnh
    assert cx == pytest.approx(816.3, abs=5)
    assert 0 <= ped["x1"] < ped["x2"] <= IMG_W and 0 <= ped["y1"] < ped["y2"] <= IMG_H
    assert ped["depth"] == pytest.approx(8.5, abs=0.2)  # 10 − 1.5 (camera cách ego 1.5 m)
    assert len(ped["corners"]) == 16
    assert ped["visibility"] == "4" and ped["num_lidar_pts"] == 50
    assert ped["ann_token"] == "ann_scene0_f0_human.pedestrian.adult"


def test_project_boxes_drops_box_behind_camera_and_keeps_only_visible_cams(tmp_path):
    root = make_nuscenes(tmp_path, n_scenes=1, frames_per_scene=1)
    t, fr = _load(root)
    b2d, _ = project_boxes(t, fr)
    back = b2d[b2d["cam"] == "CAM_BACK"]
    assert back.empty  # hộp ở phía trước xe nằm sau lưng CAM_BACK
    assert set(b2d["cam"]) <= set(CAMS)
    assert not b2d.empty


def test_project_boxes_clips_to_image_but_keeps_raw_corners(tmp_path):
    root = make_nuscenes(tmp_path, n_scenes=1, frames_per_scene=1)
    ann = root / "v1.0-mini" / "sample_annotation.json"
    rows = json.loads(ann.read_text())
    for r in rows:  # đẩy hộp ra mép phải ảnh CAM_FRONT: một phần nằm ngoài khung
        if "pedestrian" in r["token"]:
            r["translation"] = [10.0, -5.3, 0.9]
    ann.write_text(json.dumps(rows))
    t, fr = _load(root)
    b2d, _ = project_boxes(t, fr)
    ped = b2d[(b2d["cam"] == "CAM_FRONT") & b2d["category"].str.startswith("human")].iloc[0]
    us = np.array(ped["corners"])[0::2]
    assert us.min() < IMG_W < us.max()  # góc chưa cắt vắt qua mép phải
    assert ped["x2"] == IMG_W


def test_project_boxes_drops_box_with_no_corner_inside_image(tmp_path):
    root = make_nuscenes(tmp_path, n_scenes=1, frames_per_scene=1)
    ann = root / "v1.0-mini" / "sample_annotation.json"
    rows = json.loads(ann.read_text())
    for r in rows:
        r["translation"] = [10.0, -30.0, 0.9]  # xa sang phải, hoàn toàn ngoài CAM_FRONT
    ann.write_text(json.dumps(rows))
    t, fr = _load(root)
    b2d, _ = project_boxes(t, fr)
    assert b2d[b2d["cam"] == "CAM_FRONT"].empty


def test_boxes_3d_in_lidar_ego_frame_one_row_per_annotation(tmp_path):
    root = make_nuscenes(tmp_path, n_scenes=1, frames_per_scene=2)
    t, fr = _load(root)
    _, b3d = project_boxes(t, fr)
    assert len(b3d) == 2 * 2 and not b3d.duplicated(["sample_token", "ann_token"]).any()
    ped = b3d[(b3d["sample_token"] == "scene0_f0")
              & b3d["category"].str.startswith("human")].iloc[0]
    c = np.array(ped["corners"]).reshape(8, 3)  # corners[24] = 8 góc × (x,y,z) xen kẽ
    assert c.mean(axis=0) == pytest.approx([10.0, 0.0, 0.9], abs=1e-4)  # hệ ego của LIDAR_TOP


def test_project_boxes_without_annotations_is_empty_with_columns(tmp_path):
    root = make_nuscenes(tmp_path, with_annotations=False)
    t, fr = _load(root)
    b2d, b3d = project_boxes(t, fr)
    assert b2d.empty and b3d.empty
    assert "corners" in b2d.columns and "corners" in b3d.columns


def test_build_index_writes_gt_tables_when_annotations_exist(tmp_path):
    root = make_nuscenes(tmp_path / "ds", n_scenes=2, frames_per_scene=3)
    job = tmp_path / "job"
    assert build_index.main(["--data-root", str(root), "--job-dir", str(job)]) == 0
    rare = read_table(job / "gt" / "gt_rare.parquet", "gt_rare")
    b2d = read_table(job / "gt" / "gt_boxes_2d.parquet", "gt_boxes_2d")
    b3d = read_table(job / "gt" / "boxes_3d.parquet", "boxes_3d")
    assert len(rare) == 2 * 3 and len(b3d) == 2 * 3 * 2 and len(b2d) > 0
    manifest = json.loads((job / "gt" / "gt_rare.parquet.manifest.json").read_text())
    assert set(manifest["group_frequencies"]) == set(GROUPS)
    assert manifest["group_frequencies"]["A_night"] == 0.5


def test_build_index_without_annotations_writes_no_gt_and_exits_zero(tmp_path, capsys):
    root = make_nuscenes(tmp_path / "ds", with_annotations=False)
    job = tmp_path / "job"
    assert build_index.main(["--data-root", str(root), "--job-dir", str(job)]) == 0
    assert (job / "index" / "frames.parquet").is_file()
    assert not (job / "gt").exists()
    assert "annotation" in capsys.readouterr().out.lower()


def test_build_index_respects_limit_for_gt(tmp_path):
    root = make_nuscenes(tmp_path / "ds", n_scenes=2, frames_per_scene=3)
    job = tmp_path / "job"
    assert build_index.main(["--data-root", str(root), "--job-dir", str(job),
                             "--limit", "6"]) == 0
    fr = read_table(job / "index" / "frames.parquet", "frames")
    rare = read_table(job / "gt" / "gt_rare.parquet", "gt_rare")
    assert set(rare["sample_token"]) == set(fr["sample_token"])
