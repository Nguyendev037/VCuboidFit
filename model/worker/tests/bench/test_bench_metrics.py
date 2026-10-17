"""Metric tay, Holm, và bootstrap max phải tính lại mỗi lượt."""
import pandas as pd
import pytest

from c4.bench.metrics import (
    bench_report, cohen_kappa, empty_rate, holm, struggle_frames, sy, unc_at_b,
)
from c4.contracts import ContractError


def toy_report():
    frames = pd.DataFrame(dict(sample_token=["f0", "f1", "f2", "f3"],
                               scene_token=["s0", "s0", "s1", "s1"]))
    st = pd.DataFrame([dict(sample_token=f, ann_token=f"a{i}", instance_token=f"i{i}",
                            scene_token=s, struggle=True, unc=0.8)
                       for i, (f, s) in enumerate(zip(frames.sample_token, frames.scene_token))])
    methods = {m: dict(tokens=["f0"]) for m in ("OURS", "M1", "M2", "X1", "X2", "X3", "N1", "N2")}
    methods["X0"] = dict(seeds={str(s): ["f0"] for s in range(100)})
    sels = dict(dataset="pandaset", B=1, n_pool=4, methods=methods,
                judges={j: dict(tau=0.5, validity=dict(ok=True)) for j in ("JA", "JB")})
    return sels, {"JA": st, "JB": st.copy()}, st, frames


def test_sy_counts_instances_not_frames():
    tf = {"i1": {"a", "b"}, "i2": {"a"}}
    assert sy(["a"], tf) == 2
    assert sy(["a", "b"], tf) == 1
    assert sy([], tf) == 0


def test_unc_empty_and_kappa():
    _, tables, objs, _ = toy_report()
    assert unc_at_b(["f0"], tables["JA"]) == 0.8
    assert unc_at_b(["missing"], tables["JA"]) == 0
    assert empty_rate(["f0", "missing"], objs) == 0.5
    assert cohen_kappa(tables["JA"], tables["JB"]) == 1
    a = tables["JA"].copy()
    a["struggle"] = [True, True, False, False]
    b = a.copy()
    b["struggle"] = [True, False, True, False]
    assert cohen_kappa(a, b) == 0


def test_instance_in_two_scenes_rejected():
    _, tables, _, _ = toy_report()
    bad = tables["JA"].copy()
    bad["instance_token"] = "same"
    with pytest.raises(ContractError, match="more than one scene"):
        struggle_frames(bad)


def test_holm_textbook_order():
    assert holm([0.03, 0.01, 0.04]) == pytest.approx([0.06, 0.03, 0.06])


def test_bootstrap_retakes_max(monkeypatch):
    sels, tables, objs, frames = toy_report()

    def fake_boot(sels, gt_frame, tf, **kwargs):
        assert kwargs["capture"] == "any"
        data = {m: [0.0, 0.0, 0.0, 0.0] for m in sels}
        data.update(OURS=[2.0] * 4, X1=[3.0, 0, 3.0, 0], X2=[0, 3.0, 0, 3.0])
        return pd.DataFrame(data)

    monkeypatch.setattr("c4.bench.metrics.bootstrap_fixed", fake_boot)
    report = bench_report(sels, tables, objs, frames, n_boot=4)
    contrast = next(r for r in report["contrasts"] if r["judge"] == "JA" and r["b"] == "Xbest")
    assert contrast["lo"] == contrast["hi"] == -1.0
    assert report["label"] == "preliminary" and report["verdict"]["win"] is False
    assert set(report["curve"]) == {"0.01", "0.02", "0.05", "0.10"}


def test_report_rejects_outside_pool():
    sels, tables, objs, frames = toy_report()
    sels["methods"]["X1"]["tokens"] = ["outside"]
    with pytest.raises(ContractError):
        bench_report(sels, tables, objs, frames, n_boot=2)


def test_report_rejects_instance_across_judges():
    sels, tables, objs, frames = toy_report()
    tables["JB"]["scene_token"] = "other"
    with pytest.raises(ContractError):
        bench_report(sels, tables, objs, frames, n_boot=2)
