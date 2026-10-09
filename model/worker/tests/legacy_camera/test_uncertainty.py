import numpy as np
import pandas as pd
import pytest

from c4.mining.uncertainty import uncertainty


def frames(rows):
    return pd.DataFrame(rows, columns=["sample_token", "cam", "scene_token", "frame_idx"])


def det(rows):
    return pd.DataFrame(rows, columns=["sample_token", "cam", "conf"])


def test_entropy_normalised():
    fr = frames([("a", "CAM_FRONT", "s", 0), ("b", "CAM_FRONT", "s1", 0),
                 ("c", "CAM_FRONT", "s2", 0)])
    out = uncertainty(det([("a", "CAM_FRONT", 0.5), ("b", "CAM_FRONT", 0.99)]), fr)
    ent = out.set_index("sample_token")["det_ent"]
    assert ent["a"] == pytest.approx(1.0)
    assert ent["b"] < 0.1
    assert ent["c"] == 0.0


def test_tmp_same_camera():
    fr = frames([("a", "CAM_FRONT", "s", 0), ("b", "CAM_FRONT", "s", 1)])
    d = det([("a", "CAM_FRONT", 0.9)] * 2 + [("b", "CAM_FRONT", 0.9)] * 4)
    out = uncertainty(d, fr).set_index("sample_token")["det_tmp"]
    assert out["a"] == 0.0
    assert out["b"] == pytest.approx(0.5)


def test_tmp_zero_when_prev_frame_missing_cam():
    fr = frames([("a", "CAM_FRONT", "s", 0), ("b", "CAM_FRONT", "s", 1),
                 ("b", "CAM_BACK", "s", 1)])
    d = det([("a", "CAM_FRONT", 0.9), ("b", "CAM_BACK", 0.9), ("b", "CAM_BACK", 0.9)])
    out = uncertainty(d, fr).set_index(["sample_token", "cam"])["det_tmp"]
    assert out[("b", "CAM_BACK")] == 0.0


def test_unc_is_half_sum():
    fr = frames([("a", "CAM_FRONT", "s", 0), ("b", "CAM_FRONT", "s", 1)])
    d = det([("a", "CAM_FRONT", 0.7), ("b", "CAM_FRONT", 0.6), ("b", "CAM_FRONT", 0.3)])
    out = uncertainty(d, fr)
    assert np.allclose(out["unc"], 0.5 * out["det_ent"] + 0.5 * out["det_tmp"])
    assert out["det_n"].dtype == np.int16
