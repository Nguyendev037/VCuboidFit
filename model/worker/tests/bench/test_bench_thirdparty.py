from pathlib import Path

import cv2
import numpy as np
import pandas as pd
import pytest

from c4.bench.thirdparty import (
    blur_selector,
    crowd_selector,
    dark_selector,
    entropy_selector,
    external_selector,
    frame_features,
    kcenter_selector,
)
from c4.extract.quality import quality_metrics


def test_kcenter_matches_hand_calculated_toy():
    tokens = ["a", "b", "c", "d", "e", "f"]
    emb = np.array([[1, 0], [1, 0], [0, 1], [0, 1], [-1, 0], [-1, 0]], dtype=float)
    selector = kcenter_selector(emb, tokens)
    assert selector(tokens, 3) == ["a", "e", "c"]


def test_selectors_are_deterministic_and_have_expected_direction():
    tokens = ["a", "b", "c"]
    unc = pd.Series([0.1, 0.9, 0.2], index=tokens)
    crowd = pd.Series([1, 4, 2], index=tokens)
    blur = pd.Series([9.0, 1.0, 4.0], index=tokens)
    bright = pd.Series([200.0, 80.0, 120.0], index=tokens)
    selectors = [
        entropy_selector(unc), crowd_selector(crowd), blur_selector(blur),
        dark_selector(bright),
    ]
    assert all(selector(tokens, 2) == selector(tokens, 2) for selector in selectors)
    assert selectors[0](tokens, 1) == ["b"]
    assert selectors[1](tokens, 1) == ["b"]
    assert selectors[2](tokens, 1) == ["b"]
    assert selectors[3](tokens, 1) == ["b"]


def test_frame_features_aggregate_cached_features(tmp_path: Path):
    cache = tmp_path / "cache"
    cache.mkdir()
    pd.DataFrame({
        "sample_token": ["a", "a", "b"],
        "cam": ["0", "1", "0"],
        "emb_row": [0, 1, 2],
        "q_blur": [9.0, 4.0, 3.0],
        "q_bright": [100.0, 120.0, 50.0],
    }).to_parquet(cache / "feat_dino.parquet")
    np.save(cache / "dino_cls.npy", np.array([[1, 0], [0, 1], [1, 1]], dtype=np.float32))
    pd.DataFrame({"sample_token": ["a", "b"], "unc": [0.2, 0.8]}).to_parquet(
        cache / "feat_det.parquet")
    pd.DataFrame({
        "sample_token": ["a", "a", "b"],
        "cls": [0, 2, 3],
        "conf": [0.9, 0.9, 0.4],
    }).to_parquet(cache / "detections.parquet")
    out = frame_features(tmp_path).set_index("sample_token")
    assert out.loc["a", "unc_max"] == pytest.approx(0.2)
    assert out.loc["a", "vru_count"] == 1
    assert out.loc["a", "q_blur_min"] == 4.0


def test_quality_blur_direction_and_external_order(tmp_path: Path):
    rng = np.random.default_rng(0)
    sharp = rng.integers(0, 256, (252, 448), dtype=np.uint8)
    blurred = cv2.GaussianBlur(sharp, (0, 0), sigmaX=5)
    assert quality_metrics(blurred)[1] < quality_metrics(sharp)[1]
    source = tmp_path / "ranking.txt"
    source.write_text("b\na\n", encoding="utf-8")
    assert external_selector(source)(["a", "b", "c"], 2) == ["b", "a"]
    assert external_selector(source)(["a", "b", "c"], 3) == ["b", "a"]  # không bù token
    with pytest.raises(ValueError, match="ORDER_VIOLATION"):
        external_selector(source)(["a"], 1)


def test_thirdparty_does_not_import_forbidden_ground_truth_code():
    source = Path(__file__).parents[2] / "c4" / "bench" / "thirdparty.py"
    text = source.read_text(encoding="utf-8")
    assert "rare_gt" not in text
    assert "gt/" not in text
