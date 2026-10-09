"""E2E với GT KHÁC 0: vài frame rare thật (cell hiếm) kèm point cloud khác biệt hình học."""
import copy
import json

import numpy as np
import pandas as pd
import pytest

from c4.contracts import read_table
from c4.lidar import load_gt_config, load_lidar_config
from c4.lidar.experiment import prepare, run_split
from c4.lidar.selectors import budget
from tests.fixtures.make_nuscenes import make_nuscenes

N_SCENES, FRAMES = 5, 12
N = N_SCENES * FRAMES
RARE_FRAMES = {  # (scene_idx, frame_idx) -> [(category, ego xyz, num_lidar_pts)]
    (0, 3): [("human.pedestrian.child", (13.0, 3.0, 0.9), 30)],
    (2, 5): [("movable_object.debris", (14.0, -4.0, 0.3), 30)],
    (4, 8): [("human.pedestrian.child", (30.0, 5.0, 0.9), 12)],
}
RARE_TOKENS = {"scene0_f3", "scene2_f5", "scene4_f8"}


@pytest.fixture(scope="module")
def cfg():
    c = copy.deepcopy(load_lidar_config())
    c["filter"]["min_points"] = 50
    return c


@pytest.fixture(scope="module")
def env(tmp_path_factory, cfg):
    base = tmp_path_factory.mktemp("rare")
    root = make_nuscenes(base, n_scenes=N_SCENES, frames_per_scene=FRAMES,
                         rare_frames=RARE_FRAMES)
    out = base / "runs"
    prepare(root, out, cfg, load_gt_config(), n_jobs=1, log=lambda *_: None)
    res = run_split(out, "pool", cfg, None, do_tune=False, boot_n=0, log=lambda *_: None)
    gt = read_table(str(out / "gt" / "gt_rare_lidar.parquet"), "gt_rare_lidar")
    metrics = json.loads((out / "pool" / "metrics.json").read_text(encoding="utf-8"))
    return out, res, gt, metrics


def _sel(out, run):
    return pd.read_csv(out / "pool" / run / "selected_5pct.csv").sort_values("rank")


def test_fixture_gt_is_nonzero_and_exact(env):
    _, _, gt, _ = env
    assert set(gt.loc[gt["is_rare"], "sample_token"]) == RARE_TOKENS
    assert (gt.loc[gt["is_rare"], "rare_cells"] != "").all()
    assert gt["B_few"].sum() == 3  # child/debris đều thuộc nhóm B


def test_metrics_match_hand_computation(env, cfg):
    out, res, gt, metrics = env
    B = budget(N, cfg["defaults"]["budget"])
    assert res["B"] == B == 3 and metrics["pool"]["rare"] == 3
    rare = set(gt.loc[gt["is_rare"], "sample_token"])
    boxes = dict(zip(gt["sample_token"], gt["n_boxes"]))
    for name, m in metrics["runs"].items():
        toks = set(_sel(out, name)["sample_token"].head(B))
        hit = len(toks & rare)
        assert m["recall"] == pytest.approx(hit / 3), name
        assert m["nRecall"] == pytest.approx(hit / min(B, 3)), name
        assert m["uplift"] == pytest.approx((hit / 3) / (B / N)), name
        assert m["precision"] == pytest.approx(hit / B), name
        assert m["nBoxes"] == sum(boxes[t] for t in toks), name
        assert m["byGroup"]["B"] == pytest.approx(
            len(toks & set(gt.loc[gt["B_few"], "sample_token"])) / 3), name


def test_oracle_reaches_full_nrecall(env):
    out, _, _, metrics = env
    o = metrics["runs"]["oracle_label"]
    assert o["nRecall"] == pytest.approx(1.0) and o["recall"] == pytest.approx(1.0)
    assert set(_sel(out, "oracle_label")["sample_token"]) == RARE_TOKENS


def test_random_mean_recall_near_expected(env, cfg):
    out, _, _, metrics = env
    B = budget(N, cfg["defaults"]["budget"])
    per_seed = [len(set(_sel(out, f"random_{s}")["sample_token"]) & RARE_TOKENS) / 3
                for s in cfg["random_seeds"]]
    mean = float(np.mean(per_seed))
    assert metrics["random"]["mean"]["recall"] == pytest.approx(mean)
    assert metrics["expectedRandomRecall"] == pytest.approx(B / N)
    # sd của trung bình 10 seed ≈ 0.04 ⇒ dung sai 0.15 ≈ 3.5σ
    assert abs(mean - B / N) <= 0.15


def test_tier0_mmr_catches_geometrically_distinct_rare_frame(env):
    out, _, _, metrics = env
    caught = set(_sel(out, "t0_rar_mmr")["sample_token"]) & RARE_TOKENS
    assert len(caught) >= 1, "Tầng 0 không bắt được frame rare dù hình học khác biệt"
    assert metrics["runs"]["t0_rar_mmr"]["recall"] >= 1 / 3
