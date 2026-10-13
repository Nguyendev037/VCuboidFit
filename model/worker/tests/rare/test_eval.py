"""M5 · eval theo instance (TESTING §0 pitching: đường chính + oracle cận trên)."""
import pandas as pd

from c4.rare.eval import (
    budget,
    evaluate,
    metrics,
    oracle_instance,
    reachability,
    target_frames,
    topk_selector,
)


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


def test_capture_rare_form_excludes_normal_visible_frame():
    from c4.rare.eval import bootstrap_fixed
    frame, inst = _gt()
    frame["target_instances"] = ["long" if i == 1 else "a" if i == 10 else "b" if i == 11 else ""
                                 for i in range(20)]
    sel = {"normal": lambda p, b: ["f0"], "rare": lambda p, b: ["f1"]}
    a = evaluate(sel, frame, inst, capture="any")
    b = evaluate(sel, frame, inst, capture="rare_form")
    assert a["methods"]["normal"]["iy"] == 1
    assert b["methods"]["normal"]["iy"] == 0 and b["methods"]["rare"]["iy"] == 1
    tf = target_frames(inst, capture="rare_form", gt_frame=frame)
    assert tf["long"] == {"f1"}
    boot = bootstrap_fixed({"normal": ["f0"], "rare": ["f1"]}, frame, target_frames(inst),
                           n_boot=20, capture="rare_form")
    assert (boot["normal"] == 0).all() and boot["rare"].max() == 1


def test_reachability_counts_only_candidates_in_rare_form_frames():
    # hit: ứng viên cách 0,5 m trong frame dạng hiếm f1 ⇒ đạt. miss: ứng viên chỉ nằm ở f2
    # (dạng thường của nó) ⇒ không đạt. radius mặc định 1,0 m, cột hệ ego.
    objects = pd.DataFrame(dict(sample_token=["f1", "f2"], cx=[0.5, 0.1], cy=[0.0, 0.0]))
    gt = pd.DataFrame(dict(instance_token=["hit", "miss"], sample_token=["f1", "f2"],
                           cx=[0.0, 0.0], cy=[0.0, 0.0]))
    assert reachability(objects, gt, {"hit": {"f1"}, "miss": {"f0"}}) == dict(
        reach=0.5, n_reachable=1, n_targets=2)
    # f2 là dạng hiếm của miss ⇒ ứng viên đó phải tính ⇒ chứng minh bộ lọc frame mới là thứ loại nó.
    assert reachability(objects, gt, {"hit": {"f1"}, "miss": {"f2"}})["reach"] == 1.0
    # ứng viên 2,0 m ngoài bán kính 1,0 m ⇒ không tính; tập target rỗng ⇒ 0/0 quy ước 0,0.
    far = pd.DataFrame(dict(sample_token=["f1"], cx=[2.0], cy=[0.0]))
    assert reachability(far, gt, {"hit": {"f1"}, "miss": {"f0"}})["reach"] == 0.0
    assert reachability(objects, gt, {}) == dict(reach=0.0, n_reachable=0, n_targets=0)
