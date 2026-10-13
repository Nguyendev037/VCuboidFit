"""M5 · eval theo instance (TESTING §0 pitching: đường chính + oracle cận trên)."""
import pandas as pd

from c4.rare.eval import (budget, evaluate, metrics, oracle_instance, target_frames,
                          topk_selector)


def _gt():
    toks = [f"f{i}" for i in range(20)]
    frame = pd.DataFrame(dict(sample_token=toks, scene_token=["s0"] * 10 + ["s1"] * 10,
                              is_target=[i < 12 for i in range(20)], c_night=False, c_rain=False))
    inst = pd.DataFrame(dict(
        instance_token=["long", "a", "b"], axes=["r2_combo", "r2_combo", "r2_combo|i_conflict"],
        frames=["|".join(toks[:10]), "f10", "f11"]))
    return frame, inst


def test_instance_unit_counts_long_track_once():
    frame, inst = _gt()
    tf = target_frames(inst)
    m = metrics([f"f{i}" for i in range(5)], frame, tf)
    assert m["n_instances"] == 1 and m["precision"] == 1.0  # 5 frame cùng một instance ⇒ IY đếm 1


def test_oracle_bounds_every_method():
    frame, inst = _gt()
    tf = target_frames(inst)
    assert set(oracle_instance(list(frame["sample_token"]), 3, tf)) >= {"f10", "f11"}
    scores = pd.Series({f"f{i}": float(-i) for i in range(20)})  # chọn f0,f1,… (cùng một instance)
    rep = evaluate({"naive": topk_selector(scores)}, frame, inst, frac=0.15)
    assert rep["B"] == budget(20, 0.15) == 3
    assert rep["oracle"]["iy"] >= rep["methods"]["naive"]["iy"]


def test_bootstrap_fixed_keeps_selection_and_pairs_methods():
    from c4.rare.eval import bootstrap_fixed, paired_ci
    frame, inst = _gt()
    tf = target_frames(inst)
    boot = bootstrap_fixed({"good": ["f0", "f10", "f11"], "bad": ["f0", "f1", "f2"]}, frame, tf, n_boot=200)
    ci = paired_ci(boot, "good", "bad")
    assert len(boot) == 200 and ci["delta"] > 0 and ci["hi"] >= ci["lo"]
