"""Tầng 0 + khung đánh giá (planning/04 SPEC-P01)."""
import copy
import pickle

import numpy as np
import pandas as pd
import pytest

from c4.lidar import eval as ev
from c4.lidar import load_gt_config, load_lidar_config, nusc_splits
from c4.lidar.descriptor import block_dims, embed, frame_descriptor
from c4.lidar.pcd import remove_close, voxel_downsample
from c4.lidar.score import combine, pct_rank, rarity
from c4.lidar.select import budget, select_coreset, select_mmr, select_random, select_topk
from c4.lidar.splits import plan_splits
from c4.lidar.uncertainty import entropy, inconsistency, load_preds, match_count


@pytest.fixture
def cfg():
    c = copy.deepcopy(load_lidar_config())
    c["filter"]["min_points"] = 50
    return c


def _cloud(seed, n=4000):
    rng = np.random.default_rng(seed)
    ground = np.c_[rng.uniform(-40, 40, (n, 2)), rng.normal(-1.8, 0.03, n)]
    box = np.c_[rng.uniform(5, 7, (n // 4, 2)), rng.uniform(-1.5, 0.5, n // 4)]
    xyz = np.r_[ground, box]
    return np.c_[xyz, rng.uniform(0, 255, len(xyz)), rng.integers(0, 32, len(xyz))].astype(
        np.float32)


def test_remove_close_and_voxel_deterministic():
    p = np.array([[0.5, 0.5, 0, 0, 0], [3, 0, 0, 0, 0], [3.05, 0.01, 0, 0, 0]], np.float32)
    assert len(remove_close(p, 1.0)) == 2
    v1 = voxel_downsample(p, 0.2)
    v2 = voxel_downsample(p[::-1].copy(), 0.2)
    assert len(v1) == len(v2) == 2


def test_frame_descriptor_blocks_and_filter(tmp_path, cfg):
    f = tmp_path / "a.pcd.bin"
    _cloud(0).tofile(f)
    r = frame_descriptor(f, cfg, bev_path=tmp_path / "bev.png")
    dims = block_dims(cfg)
    assert {k: len(v) for k, v in r["blocks"].items()} == dims
    assert (tmp_path / "bev.png").is_file()
    r2 = frame_descriptor(f, cfg)
    assert all(np.array_equal(r["blocks"][k], r2["blocks"][k]) for k in dims)  # tất định
    few = tmp_path / "few.pcd.bin"
    _cloud(0, n=8)[:10].tofile(few)
    assert frame_descriptor(few, cfg)["reason"] == "few_points"
    bad = tmp_path / "bad.pcd.bin"
    bad.write_bytes(b"\x00" * 7)
    assert frame_descriptor(bad, cfg)["reason"] == "read_error"


def test_embed_pca_shape_drop_and_keep():
    rng = np.random.default_rng(0)
    raw = {k: rng.normal(size=(30, d)).astype(np.float32)
           for k, d in dict(A=9, B=16, C=100, D=14, E=3).items()}
    keep = np.ones(30, bool)
    keep[3] = False
    z = embed(raw, keep, 64)
    assert z.shape == (30, 28)  # min(64, n_fit-1=28, D)
    assert np.array_equal(z, embed(raw, keep, 64))
    zd = embed(raw, keep, 8, drop_blocks=("C",))
    assert zd.shape == (30, 8)


def test_rarity_ignores_same_scene_neighbors():
    z = np.array([[0.0], [0.01], [10.0], [10.2]], np.float32)
    scene = np.array([0, 0, 1, 1])
    r = rarity(z, scene, k=1)
    # láng giềng gần nhất khác scene của frame 0 là frame 2 (≈10), không phải frame 1 (0.01)
    assert r[0] == pytest.approx(10.0, abs=1e-4)
    invalid = np.array([True, True, False, True])
    assert rarity(z, scene, k=1, valid=invalid)[0] == pytest.approx(10.2, abs=1e-4)


def test_pct_rank_masks_and_combine_weights():
    x = np.array([1.0, 2.0, 3.0, 4.0])
    m = np.array([True, True, True, False])
    np.testing.assert_allclose(pct_rank(x, m), [1 / 3, 2 / 3, 1.0, 0.0], rtol=1e-6)
    assert not pct_rank(np.zeros(4), m).any()  # tín hiệu hằng không mang thông tin ⇒ hạng 0
    idx = pd.DataFrame(dict(sample_token=list("abcd"), scene_token=["s0", "s0", "s1", "s1"],
                            split="V", frame_idx=[0, 1, 0, 1]))
    sc = combine(idx, m, x, None, None, 1, 0, 0)
    assert sc["s"].tolist() == pytest.approx([1 / 3, 2 / 3, 1.0, 0.0], rel=1e-5)


def _scores(n_scenes=5, per=10, seed=0):
    rng = np.random.default_rng(seed)
    n = n_scenes * per
    idx = pd.DataFrame(dict(sample_token=[f"t{i:03d}" for i in range(n)],
                            scene_token=[f"s{i // per}" for i in range(n)], split="V",
                            frame_idx=[i % per for i in range(n)]))
    keep = np.ones(n, bool)
    return combine(idx, keep, rng.random(n).astype(np.float32), None, None, 1, 0, 0), \
        rng.normal(size=(n, 8)).astype(np.float32)


def test_select_mmr_quota_and_budget():
    sc, z = _scores()
    B = budget(len(sc), 0.2)
    sel, warn = select_mmr(sc, z, B, lam=0.7, m=2)
    assert len(sel) == B == 10 and not warn
    assert sel.groupby("scene_token").size().max() <= 2
    assert sel["reason"].str.startswith("rarity p").all()
    sel2, warn2 = select_mmr(sc, z, 15, lam=0.7, m=2)  # 5 scene × 2 < 15 ⇒ tự nâng m
    assert len(sel2) == 15 and warn2


def test_baselines_sizes_and_determinism():
    sc, z = _scores()
    assert select_random(sc, 7, 3).equals(select_random(sc, 7, 3))
    rq = select_random(sc, 10, 1, m=2)
    assert rq.groupby("scene_token").size().max() <= 2 and len(rq) == 10
    assert len(select_coreset(sc, z, 6)) == 6
    top = select_topk(sc, 5)
    assert top["s"].tolist() == sorted(sc["s"], reverse=True)[:5]


def test_eval_metrics_hand_example():
    idx = pd.DataFrame(dict(sample_token=list("abcdef"), scene_token=["s0"] * 3 + ["s1"] * 3,
                            timestamp=np.array([0, 0.5, 5, 0, 5, 10]) * 1e6))
    gt = pd.DataFrame(dict(sample_token=list("abcdef"),
                           is_rare=[True, False, True, False, False, True],
                           A_env=[False] * 3 + [True] * 3, B_few=[True, False, False, False,
                                                                  False, True],
                           Bp_medium=False, C_sensor=False, n_boxes=[1, 2, 3, 4, 5, 6],
                           rare_cells=["x", "", "y", "", "", "x|z"]))
    t = ev.Truth(gt, idx)
    m = ev.metrics(["a", "b"], t, B=2, dt=2.0)
    assert m["recall"] == pytest.approx(1 / 3)
    assert m["nRecall"] == pytest.approx(1 / 2)
    assert m["uplift"] == pytest.approx((1 / 3) / (2 / 6))
    assert m["precision"] == pytest.approx(0.5)
    assert m["sceneRecall"] == 0.0
    assert m["coverage"] == pytest.approx(1 / 3)
    assert m["redundancy"] == pytest.approx(1.0)  # a, b cùng scene cách 0.5 s
    assert m["nBoxes"] == 3
    assert m["byGroup"]["B"] == pytest.approx(0.5)
    assert ev.oracle(t, 2)[:2] == ["f", "a"]


def test_uncertainty_entropy_and_flip_consistency():
    assert entropy(np.array([])) == 0.0
    assert entropy(np.array([0.5])) == pytest.approx(np.log(2))
    a = dict(boxes=np.array([[0, 0, 0, 1, 1, 1, 0], [10, 0, 0, 1, 1, 1, 0]], np.float32),
             labels=np.array([0, 1]), scores=np.array([0.9, 0.4]))
    b = dict(boxes=np.array([[0.5, 0, 0, 1, 1, 1, 0]], np.float32), labels=np.array([0]),
             scores=np.array([0.8]))
    assert match_count(a, b, 1.0) == 1
    assert inconsistency(a, b, 1.0) == pytest.approx(0.5)
    assert inconsistency(a, a, 1.0) == 0.0


def test_load_preds_rejects_misordered(tmp_path):
    from c4.contracts import ContractError

    p = tmp_path / "p.pkl"
    with open(p, "wb") as f:
        pickle.dump([dict(sample_token="b"), dict(sample_token="a")], f)
    with pytest.raises(ContractError):
        load_preds(p, ["a", "b"])


def test_official_splits_and_scene_disjoint(cfg):
    assert len(nusc_splits.TRAIN) == 700 and len(nusc_splits.VAL) == 150
    assert not set(nusc_splits.TRAIN) & set(nusc_splits.VAL)
    mini = list(nusc_splits.MINI_TRAIN) + list(nusc_splits.MINI_VAL)
    m = plan_splits(mini, cfg)
    assert {k for k, v in m.items() if v == "T"} == set(nusc_splits.MINI_VAL)
    assert sorted(m.values()).count("S") == 2 and sorted(m.values()).count("V") == 3
    tv = plan_splits(list(nusc_splits.TRAIN) + list(nusc_splits.VAL), cfg)
    assert sum(v == "T" for v in tv.values()) == 150
    assert sum(v == "S" for v in tv.values()) == 35 and sum(v == "V" for v in tv.values()) == 100
    assert plan_splits(["my_scene"], cfg) == {"my_scene": "pool"}


def test_gt_config_groups_disjoint():
    g = load_gt_config()
    assert not set(g["few"]) & set(g["medium"])
    assert set(g["few"]) | set(g["medium"]) <= set(g["class_map"].values())


def test_q4_minmax_score_keeps_magnitude_and_default_is_minmax():
    """Q4 (Đ15): min-max giữ biên độ Rar, hạng % thì nén; mặc định = minmax."""
    from c4.lidar.select import minmax_score

    idx = pd.DataFrame(dict(sample_token=list("abcd"), scene_token=["s0", "s0", "s1", "s1"],
                            split="V", frame_idx=[0, 1, 0, 1]))
    rar = np.array([1.0, 1.1, 1.2, 4.0], np.float32)
    sc = combine(idx, np.ones(4, bool), rar, None, None, 1, 0, 0)
    mm = minmax_score(sc)
    assert mm[3] == pytest.approx(1.0) and mm[2] < 0.1  # khe 1.0 → 0.07 (min-max)
    assert sc["s"].iloc[3] - sc["s"].iloc[2] == pytest.approx(0.25)  # hạng %: khe chỉ 0.25
    assert load_lidar_config()["mmr_score"] == "minmax"
    z = np.eye(4, dtype=np.float32)
    a, _ = select_mmr(sc, z, 2, 0.7, None, score_norm="rank")
    b, _ = select_mmr(sc, z, 2, 0.7, None, score_norm="minmax")
    assert len(a) == len(b) == 2 and "d" in set(b["sample_token"])
    with pytest.raises(ValueError):
        select_mmr(sc, z, 2, 0.7, None, score_norm="zscore")
