import numpy as np
import pandas as pd
import pytest

from c4.eval.metrics import coverage, coverage_gain, evaluate, precision, recall, redundancy, uplift

KEYS = {"recall", "uplift", "precision", "coverage", "coverageGain", "redundancy", "byGroup"}


def test_doc_example():
    rare = set(range(200))
    sel = set(range(80)) | set(range(1000, 1220))  # 300 frame, 80 frame rare
    assert abs(recall(sel, rare) - 0.40) < 1e-9
    assert abs(uplift(sel, rare, 6000) - 8.0) < 1e-9
    assert abs(precision(sel, rare) - 80 / 300) < 1e-9


def test_redundancy_identical_pairs():
    Z = np.array([[1, 0], [1, 0], [1, 0], [0, 1]], np.float32)
    assert redundancy(Z, 0.9) == pytest.approx(3 / 6)


def test_redundancy_single_frame_is_zero():
    assert redundancy(np.array([[1.0, 0.0]], np.float32)) == 0.0


def test_coverage_gain_vs_random():
    groups = {"a": {1, 2}, "b": {3}, "c": {9}}
    assert coverage({1, 3}, groups) == pytest.approx(2 / 3)
    assert coverage_gain({1, 3}, [{9}, {5}], groups) == pytest.approx(2 / 3 - 1 / 6)


def sel_df(method, tokens, seed=0):
    return pd.DataFrame(dict(method=method, seed=seed, rank=np.arange(1, len(tokens) + 1),
                             sample_token=tokens))


def test_evaluate_shapes_and_none_without_gt():
    tokens = [f"t{i}" for i in range(100)]
    gt = pd.DataFrame(dict(sample_token=tokens, is_rare=[i < 10 for i in range(100)],
                           A_night=[i < 5 for i in range(100)], A_rain=False,
                           B_rare_class=[5 <= i < 10 for i in range(100)], C_crowd=False,
                           C_low_vis=False, C_far=False))
    emb = {t: np.eye(100, dtype=np.float32)[i] for i, t in enumerate(tokens)}

    def Zf(ts):
        return np.stack([emb[t] for t in ts]) if ts else np.zeros((0, 100), np.float32)
    sels = {"hybrid": sel_df("hybrid", tokens[:5] + tokens[50:60]),
            "novelty": sel_df("novelty", tokens[20:30])}
    for s in range(1, 6):
        sels[f"random_{s}"] = sel_df("random", list(np.random.default_rng(s).permutation(tokens)),
                                     seed=s)
    out = evaluate(sels, budget_B=5, n_pool=100, gt=gt, Z_frame_by_token=Zf)
    assert set(out["hybrid"]) == KEYS
    assert out["hybrid"]["recall"] == pytest.approx(0.5)  # 5 frame rare trong top-5
    assert out["hybrid"]["byGroup"] == {"A": 1.0, "B": 0.0, "C": 0.0}
    assert set(out["random"]) == {"mean", "std"} and set(out["random"]["mean"]) == KEYS
    assert set(out["ablation"]) == {"novelty"}
    assert evaluate(sels, 5, 100, None, Zf) is None
