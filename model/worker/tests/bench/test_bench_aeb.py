"""Hộp tạo tay ở đúng các biên AEB đã đăng ký."""
import numpy as np
import pandas as pd
import pytest

from c4.bench.aeb import aeb_objects
from c4.contracts import JUDGE_DET, read_table, write_table


def tables(x=10, y=0, category="human.pedestrian.adult", height=40, pts=1, full_width=20):
    boxes2d = pd.DataFrame([dict(sample_token="f", ann_token="a", cam="CAM_FRONT",
                                category=category, x1=0, y1=0, x2=20, y2=height,
                                corners=[[u, v] for u, v in
                                         [(0, 0), (full_width, 0), (0, height),
                                          (full_width, height)] * 2])])
    boxes3d = pd.DataFrame([dict(sample_token="f", ann_token="a",
                                corners=(np.zeros((8, 3)) + [x, y, 0]).tolist())])
    meta = pd.DataFrame([dict(ann_token="a", instance_token="i", scene_token="s", num_lidar_pts=pts)])
    return boxes2d, boxes3d, meta


@pytest.mark.parametrize("kwargs,keep", [({}, True), ({"x": 40}, True), ({"x": 41}, False),
    ({"height": 19}, False), ({"height": 20}, True), ({"pts": 0}, False),
    ({"full_width": 40}, True), ({"full_width": 41}, False),
    ({"category": "animal"}, False), ({"category": "vehicle.car", "y": 3}, False),
    ({"category": "vehicle.car", "x": 0}, False),
    ({"category": "vehicle.car", "y": 2}, True)])
def test_aeb_boundaries(kwargs, keep):
    assert len(aeb_objects(*tables(**kwargs))) == int(keep)


def test_one_camera_largest_and_stable_tie():
    two, three, meta = tables()
    other = two.copy()
    other["cam"], other["x2"] = "CAM_BACK", 30
    both = pd.concat([two, other], ignore_index=True)
    got = aeb_objects(both, three, meta)
    assert len(got) == 1 and got.iloc[0].cam == "CAM_BACK"
    assert got.instance_token.tolist() == ["i"]


def test_detection_keyless_roundtrip(tmp_path):
    row = dict(judge="JA", sample_token="f", cam="CAM_FRONT", coco_label=1, group="vru",
               score=0.5, x1=0, y1=0, x2=20, y2=40)
    path = tmp_path / "det.parquet"
    write_table(pd.DataFrame([row, row], columns=JUDGE_DET), path, "judge_det")
    assert len(read_table(path, "judge_det")) == 2
