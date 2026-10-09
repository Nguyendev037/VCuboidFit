import math
from types import SimpleNamespace

import numpy as np

from c4.config import load_config
from c4.contracts import CAMS, validate
from c4.mining.score import frame_embeddings, frame_scores
from c4.mining.select import reason, run_all, run_random, run_select
from c4.params import SelectParams, resolve
from tests.fixtures.make_fixture import make_fixture


def setup(n_scenes=20, frames=20, budget=0.05, feat_edit=None, **kw):
    fx = make_fixture(n_scenes=n_scenes, frames_per_scene=frames)
    feat = feat_edit(fx.feat.copy()) if feat_edit else fx.feat
    r = resolve(SelectParams(budget=budget, **kw), load_config())
    fs = frame_scores(feat, r.alpha, r.beta, r.gamma, CAMS)
    Zf, _ = frame_embeddings(fx.Z_img, feat, CAMS)
    return fx, fs, Zf, r


def top(sel, B):
    return sel[sel["rank"] <= B]


def test_selects_exactly_B_and_no_duplicates():
    fx, fs, Zf, r = setup()
    sel, warn = run_select(fs, Zf, r)
    B = math.ceil(0.05 * len(fs))
    validate(sel, "selected")
    assert len(top(sel, B)) == B
    assert sel["sample_token"].is_unique
    assert len(sel) == math.ceil(0.10 * len(fs))
    assert warn == []


def test_scene_cap_respected():
    fx, fs, Zf, r = setup()
    sel, _ = run_select(fs, Zf, r)
    assert top(sel, sel["budget_B"].iloc[0]).groupby("scene_token").size().max() <= r.m


def test_min_gap_respected():
    fx, fs, Zf, r = setup()
    sel, _ = run_select(fs, Zf, r)
    m = sel.merge(fs[["sample_token", "frame_idx"]], on="sample_token")
    for _, g in m.groupby("scene_token"):
        idx = np.sort(g["frame_idx"].to_numpy())
        assert (np.diff(idx) >= r.min_gap).all()


def test_nested_ranks():
    fx, fs, Zf, r5 = setup(budget=0.05)
    _, _, _, r3 = setup(budget=0.03)
    a, _ = run_select(fs, Zf, r5)
    b, _ = run_select(fs, Zf, r3)
    B = b["budget_B"].iloc[0]
    assert list(top(a, B)["sample_token"]) == list(top(b, B)["sample_token"])


def test_auto_relax_scene_cap():
    fx, fs, Zf, r = setup(n_scenes=2, frames=100)
    sel, warn = run_select(fs, Zf, r)
    assert len(top(sel, 10)) == 10
    assert len(warn) == 1 and "max_per_scene" in warn[0] and "5" in warn[0]


def test_all_bad_returns_empty_with_warning():
    def all_bad(feat):
        feat["q_ok"] = False
        return feat
    fx, fs, Zf, r = setup(feat_edit=all_bad)
    sel, warn = run_select(fs, Zf, r)
    assert len(sel) == 0 and warn


def test_random_seeds_differ_and_are_reproducible():
    fx, fs, Zf, r = setup()
    a, b, c = run_random(fs, r, 1), run_random(fs, r, 1), run_random(fs, r, 2)
    assert list(a["sample_token"]) == list(b["sample_token"])
    assert list(a["sample_token"]) != list(c["sample_token"])
    validate(a, "selected")


def test_reason_format():
    row = SimpleNamespace(r_nov=0.981, r_unc=0.1, r_qry=0.95, qry_best="night_rain")
    assert reason(row) == "novelty p98 · query night_rain p95"
    low = SimpleNamespace(r_nov=0.5, r_unc=0.1, r_qry=0.2, qry_best="bicycle")
    assert reason(low) == "điểm tổng hợp cao"


def test_hybrid_beats_random_on_fixture():
    fx, fs, Zf, r = setup()
    sels, _ = run_all(fs, Zf, r, [1, 2, 3, 4, 5])
    assert set(sels) == {"hybrid", "novelty", "uncertainty", "query", "hybrid_nodiv",
                         "random_1", "random_2", "random_3", "random_4", "random_5"}
    B = sels["hybrid"]["budget_B"].iloc[0]

    def rec(s):
        return len(set(top(s, B)["sample_token"]) & fx.rare_tokens) / len(fx.rare_tokens)
    rand = np.mean([rec(sels[f"random_{i}"]) for i in range(1, 6)])
    assert rec(sels["hybrid"]) > rand


def _only_scene0_rich(n_rich):
    def edit(feat):
        poor = (feat["scene_token"] != "scene0") & (feat["frame_idx"] > 0)
        rich_cut = (feat["scene_token"] == "scene0") & (feat["frame_idx"] >= n_rich)
        feat.loc[poor | rich_cut, "q_ok"] = False
        return feat
    return edit


def test_auto_relax_uneven_scenes_fills_budget():
    # 10 scene: scene0 có 36 frame hợp lệ (tối đa 9 frame với min_gap 4), 9 scene còn lại mỗi
    # scene 1 frame. N = 360, B = 18 -> cần m = 9.
    fx, fs, Zf, r = setup(n_scenes=10, frames=36, budget=0.05,
                          feat_edit=_only_scene0_rich(36))
    sel, warn = run_select(fs, Zf, r)
    B = sel["budget_B"].iloc[0]
    assert len(top(sel, B)) == B
    used_m = top(sel, B).groupby("scene_token").size().max()
    assert any("max_per_scene" in w and str(used_m) in w for w in warn)


def test_relax_min_gap_as_last_resort():
    # một scene 100 frame, min_gap 30 chỉ cho 4 frame, B = 5 -> phải nới min_gap
    fx, fs, Zf, r = setup(n_scenes=1, frames=100, budget=0.05, min_gap=30)
    sel, warn = run_select(fs, Zf, r)
    assert len(top(sel, 5)) == 5
    assert any("min_gap" in w for w in warn)
