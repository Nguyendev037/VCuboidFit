"""T2 · kiểm thử nhánh PointPillars (pp_candidates, merge_candidates, missed_by_model) bằng dữ liệu tổng hợp (H16)."""
import math
import numpy as np
import pytest

from c4.rare.candidates import load_class_map, merge_candidates, pp_candidates


def test_pp_candidates_box_mapping():
    """(1) pp_candidates với 3 box giả (pedestrian, bicycle, car) -> cls_pred đúng theo class_map_pred_v24.yaml,
    source="pointpillars", pts=0."""
    class_map = load_class_map()
    # class_map: pp_class_names = [car, truck, construction_vehicle, bus, trailer, barrier, motorcycle, bicycle, pedestrian, traffic_cone]
    # base = 1: car -> 1, bicycle -> 8, pedestrian -> 9
    preds = {
        "boxes": np.array([
            [10.0, 2.0, 0.0, 0.8, 0.8, 1.7, 0.1],  # pedestrian (label 9)
            [15.0, 3.0, -0.5, 1.8, 0.6, 1.2, 0.2],  # bicycle (label 8)
            [20.0, -2.0, 0.5, 4.5, 2.0, 1.6, -0.1],  # car (label 1)
        ], dtype=np.float32),
        "labels": np.array([9, 8, 1], dtype=np.int64),
        "scores": np.array([0.90, 0.85, 0.95], dtype=np.float32),
    }

    cands = pp_candidates(preds, class_map)
    assert len(cands) == 3

    # (1) Pedestrian
    p = cands[0]
    assert p["cls_pred"] == "pedestrian"
    assert p["source"] == "pointpillars"
    assert p["pts"] == 0
    assert p["pp_score"] == pytest.approx(0.90)
    assert p["cx"] == pytest.approx(10.0)
    assert p["cy"] == pytest.approx(2.0)
    assert p["cz"] == pytest.approx(0.0)
    assert p["l"] == pytest.approx(0.8)
    assert p["w"] == pytest.approx(0.8)
    assert p["h"] == pytest.approx(1.7)
    assert p["yaw"] == pytest.approx(0.1)
    assert p["dist_m"] == pytest.approx(math.hypot(10.0, 2.0))
    assert p["missed_by_model"] is False

    # (2) Bicycle
    b = cands[1]
    assert b["cls_pred"] == "bicycle"
    assert b["source"] == "pointpillars"
    assert b["pts"] == 0
    assert b["pp_score"] == pytest.approx(0.85)
    assert b["missed_by_model"] is False

    # (3) Car -> mapped to "other" according to pp_to_group
    c = cands[2]
    assert c["cls_pred"] == "other"
    assert c["source"] == "pointpillars"
    assert c["pts"] == 0
    assert c["pp_score"] == pytest.approx(0.95)
    assert c["missed_by_model"] is False


def test_merge_candidates_with_pointpillars():
    """(2) merge_candidates: 1 cụm trùng box PP (IoU BEV >= 0.3) -> 1 object source="merged", pts lấy từ cụm,
    box lấy từ PP; 1 cụm không khớp -> missed_by_model=True."""
    # Cluster 0: trùng PP (cx=10.0, cy=2.0, l=1.0, w=1.0)
    cluster_match = {
        "object_id": "c000",
        "source": "cluster",
        "cls_pred": "vru_unknown",
        "cx": 10.0,
        "cy": 2.0,
        "cz": 0.0,
        "l": 1.0,
        "w": 1.0,
        "h": 1.8,
        "yaw": 0.0,
        "pts": 142,
        "dist_m": math.hypot(10.0, 2.0),
        "gx": 10.0,
        "gy": 2.0,
        "track_id": "",
        "speed_mps": None,
        "missed_by_model": False,
    }
    # Cluster 1: không khớp PP (xa hẳn)
    cluster_nomatch = {
        "object_id": "c001",
        "source": "cluster",
        "cls_pred": "bicycle",
        "cx": 35.0,
        "cy": 12.0,
        "cz": -0.2,
        "l": 1.9,
        "w": 0.7,
        "h": 1.1,
        "yaw": 0.5,
        "pts": 64,
        "dist_m": math.hypot(35.0, 12.0),
        "gx": 35.0,
        "gy": 12.0,
        "track_id": "",
        "speed_mps": None,
        "missed_by_model": False,
    }
    # PP candidate: trùng cluster 0 (cx=10.1, cy=2.05, l=0.9, w=0.9)
    # BEV IoU giao / hợp ~ 0.81 / 1.18 >= 0.3
    pp_box = {
        "object_id": "p000",
        "source": "pointpillars",
        "cls_pred": "pedestrian",
        "cx": 10.1,
        "cy": 2.05,
        "cz": 0.15,
        "l": 0.9,
        "w": 0.9,
        "h": 1.75,
        "yaw": 0.08,
        "pts": 0,
        "dist_m": math.hypot(10.1, 2.05),
        "pp_score": 0.88,
        "track_id": "",
        "speed_mps": None,
        "missed_by_model": False,
    }

    merged = merge_candidates([cluster_match, cluster_nomatch], [pp_box], iou_thr=0.3, tier1_available=True)
    assert len(merged) == 2

    # Tìm object merged và cluster không khớp
    m_objs = [o for o in merged if o["source"] == "merged"]
    c_objs = [o for o in merged if o["source"] == "cluster"]
    assert len(m_objs) == 1
    assert len(c_objs) == 1

    mo = m_objs[0]
    assert mo["pts"] == 142  # pts lấy từ cụm
    assert mo["cx"] == pytest.approx(10.1)  # box lấy từ PP
    assert mo["cy"] == pytest.approx(2.05)
    assert mo["cz"] == pytest.approx(0.15)
    assert mo["l"] == pytest.approx(0.9)
    assert mo["w"] == pytest.approx(0.9)
    assert mo["h"] == pytest.approx(1.75)
    assert mo["yaw"] == pytest.approx(0.08)
    assert mo["cls_pred"] == "pedestrian"  # cls_pred từ PP
    assert mo["pp_score"] == pytest.approx(0.88)
    assert mo["missed_by_model"] is False

    co = c_objs[0]
    assert co["cx"] == pytest.approx(35.0)
    assert co["pts"] == 64
    assert co["missed_by_model"] is True  # cụm không khớp PP khi Tầng 1 khả dụng


def test_merge_candidates_tier1_unavailable():
    """(3) Tầng 1 không khả dụng -> missed_by_model False toàn bộ."""
    clusters = [
        {
            "object_id": "c000",
            "source": "cluster",
            "cls_pred": "pedestrian",
            "cx": 8.0,
            "cy": 1.0,
            "cz": 0.0,
            "l": 0.8,
            "w": 0.8,
            "h": 1.7,
            "yaw": 0.0,
            "pts": 95,
            "dist_m": math.hypot(8.0, 1.0),
            "gx": 8.0,
            "gy": 1.0,
            "track_id": "",
            "speed_mps": None,
            "missed_by_model": False,
        },
        {
            "object_id": "c001",
            "source": "cluster",
            "cls_pred": "bicycle",
            "cx": 18.0,
            "cy": -3.0,
            "cz": 0.0,
            "l": 1.8,
            "w": 0.6,
            "h": 1.2,
            "yaw": 0.2,
            "pts": 50,
            "dist_m": math.hypot(18.0, -3.0),
            "gx": 18.0,
            "gy": -3.0,
            "track_id": "",
            "speed_mps": None,
            "missed_by_model": False,
        },
    ]

    # Trường hợp 1: t1 = [] và tier1_available=None (mặc định avail=bool(t1)=False)
    merged_none = merge_candidates(clusters, [], tier1_available=None)
    assert len(merged_none) == 2
    assert all(o["missed_by_model"] is False for o in merged_none)
    assert all(o["source"] == "cluster" for o in merged_none)

    # Trường hợp 2: tier1_available=False tường minh
    merged_flag = merge_candidates(clusters, [], tier1_available=False)
    assert len(merged_flag) == 2
    assert all(o["missed_by_model"] is False for o in merged_flag)
