"""Đo phân tích rare_v24 bằng bảng tổng hợp nhỏ, không cần nuScenes thật."""
import json
from types import SimpleNamespace

import numpy as np
import pandas as pd
import pytest

from service import engines
from service import rare_analysis as ra
from service.models import SelectionResult


@pytest.fixture
def sample():
    tokens = [f"f{i}" for i in range(10)]
    index = pd.DataFrame(dict(sample_token=tokens, scene_token=["s2"] * 4 + ["s1"] * 3
                             + ["s3"] * 3))
    frames = pd.DataFrame(dict(sample_token=tokens, gate=["valid"] * 10,
        pred_tags=["R1|R2", "R2", "", "R2", "", "", "", "", "", ""],
        s_frame=np.linspace(0, 1, 10), crowd=[1, 1, 0, 3, 0, 0, 0, 0, 0, 0],
        evidence=[json.dumps({"top_object": "o"})] * 10))
    objects = pd.DataFrame(dict(sample_token=["f0", "f1", "f3", "f3"],
        object_id=["o", "o", "o", "other"],
        cls_pred=["pedestrian", "bicycle", "vru_unknown", "other"],
        dist_m=[float("nan"), 55., 10., 25.],
        reasons=["vru p100", "concept child", "shape p90", "unc p50"]))
    return index, frames, objects, ["f0", "f1", "f2"]


def test_label_free_rates_and_unique_rare_frames(sample, tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)  # Không có thư mục nhãn hay dữ liệu.
    out = ra.label_free(*sample)
    assert out["tagRates"][1] == dict(tag="R2", selected=2, selectedPct=.6667,
                                     poolPct=.3, lift=2.2222)
    assert out["tagRates"][2]["lift"] is None
    assert out["selected"]["taggedRare"] == 2
    assert out["pool"] == dict(frames=10, eligible=10, scenes=3, objects=4, vru=3, taggedRare=3)
    assert [r["scene"] for r in out["scenes"]] == ["s2", "s1", "s3"]
    assert sum(out["scoreHistogram"]["counts"]) == 10


def test_top_object_reasons(sample):
    out = ra.label_free(*sample)
    assert {r["code"]: r["frames"] for r in out["reasons"]} == {
        "vru": 1, "concept": 1, "none": 1}
    assert sum(r["frames"] for r in out["reasons"]) == 3


def test_distance_bins_exclude_nan_and_other(sample):
    out = ra.label_free(*sample)
    assert out["distance"] == dict(edges=[0, 10, 20, 30, 40, 50],
                                    selected=[0, 0, 0, 0, 0, 1], pool=[0, 1, 0, 0, 0, 1])


def test_eligible_pool_and_empty_selection(sample):
    index, frames, objects, _ = sample
    frames.loc[3, "gate"] = "suspect"
    out = ra.label_free(index, frames, objects, [])
    assert out["pool"]["frames"] == 10 and out["pool"]["eligible"] == 9
    assert out["pool"]["objects"] == 2
    assert out["selected"] == dict(frames=0, scenes=0, objects=0, vru=0, taggedRare=0)
    assert out["scoreHistogram"]["threshold"] == 0


def test_build_reads_cache(sample, tmp_path, monkeypatch):
    monkeypatch.setattr(ra, "evaluate_in_sample", lambda *a: (None, "no_annotations"))
    first = ra.build(tmp_path, tmp_path, "sid", *sample)
    path = tmp_path / "engines/rare_v24/sid/rare_analysis.json"
    assert json.loads(path.read_text(encoding="utf-8")) == first
    assert not path.with_suffix(".json.tmp").exists()

    def forbidden(*a):
        raise AssertionError("Không được tính lại cache")

    monkeypatch.setattr(ra, "label_free", forbidden)
    monkeypatch.setattr(ra, "evaluate_in_sample", forbidden)
    assert ra.build(tmp_path, tmp_path, "sid", *sample) == first


@pytest.mark.parametrize("annotated,n,reason", [
    (False, 10, "no_annotations"), (True, 5001, "too_large")])
def test_evaluation_guards(tmp_path, monkeypatch, annotated, n, reason):
    monkeypatch.setattr(ra.NuscTables, "load",
                        lambda *a: SimpleNamespace(has_annotations=annotated))
    index = pd.DataFrame(dict(sample_token=[str(i) for i in range(n)]))
    frames = index.assign(gate="valid")
    assert ra.evaluate_in_sample(tmp_path, index, frames, []) == (None, reason)


def _mock_gt(monkeypatch, sample, targets=True):
    index, frames, _, _ = sample
    monkeypatch.setattr(ra.NuscTables, "load", lambda *a: SimpleNamespace(has_annotations=True))
    monkeypatch.setattr(ra, "load_rare_def", lambda: (object(), "sha"))
    seen = []
    monkeypatch.setattr(ra, "load_boxes", lambda t, pool: seen.append(pool) or {})
    monkeypatch.setattr(ra, "frame_context", lambda t, pool: {})
    monkeypatch.setattr(ra, "fit_reference", lambda *a: object())
    gt_frame = index.assign(is_target=[True] + [False] * 9, c_night=False, c_rain=False)
    gt_inst = pd.DataFrame([dict(instance_token="i", axes="r2_combo|r1_class" if targets else "",
                                 frames="f0|f3")])
    monkeypatch.setattr(ra, "label_gt", lambda *a: (gt_frame, gt_inst))
    return seen


def test_evaluation_rows_axes_and_fixed_seeds(sample, tmp_path, monkeypatch):
    seen = _mock_gt(monkeypatch, sample)
    out, reason = ra.evaluate_in_sample(tmp_path, sample[0], sample[1], sample[3])
    assert reason == "ok" and out["B"] == 3 and out["nTargets"] == 1
    assert seen == [sample[0]["sample_token"].tolist()]
    assert [r["key"] for r in out["rows"]] == ["ours", "score_only", "crowd", "random", "oracle"]
    assert out["rows"][0] == dict(key="ours", iy=.3333, iyStd=None, nInstances=1, irecall=1.)
    pool = sample[0]["sample_token"].tolist()
    captures = [int(bool(set(ra.random_selector(s)(pool, 3)) & {"f0", "f3"})) for s in range(100)]
    rand = out["rows"][3]
    assert rand["iy"] == round(float(np.mean(captures)) / 3, 4)
    assert rand["iyStd"] == round(float(np.std(np.array(captures) / 3)), 4)
    assert rand["nInstances"] == rand["irecall"] == round(float(np.mean(captures)), 4)
    assert [r["axis"] for r in out["byAxis"]] == list(ra.AXES)
    assert out["byAxis"][-1] == dict(axis="h_hard", targets=0, ours=0, randomMean=0)
    assert ra.evaluate_in_sample(tmp_path, sample[0], sample[1], sample[3])[0] == out
    analysis = ra.label_free(*sample)
    analysis.update(evaluation=out, evaluationReason=reason)
    assert SelectionResult.model_validate(_response(analysis)).rare_analysis.evaluation.B == 3


def test_no_targets(sample, tmp_path, monkeypatch):
    _mock_gt(monkeypatch, sample, targets=False)
    assert ra.evaluate_in_sample(tmp_path, sample[0], sample[1], sample[3]) == (None, "no_targets")


def test_build_isolates_failures(sample, tmp_path, monkeypatch):
    def broken(*a):
        raise RuntimeError("synthetic failure")
    monkeypatch.setattr(ra, "evaluate_in_sample", broken)
    out = ra.build(tmp_path, tmp_path, "eval", *sample)
    assert out["evaluation"] is None and out["evaluationReason"] == "error"
    monkeypatch.setattr(ra, "label_free", broken)
    assert ra.build(tmp_path, tmp_path, "label", *sample) is None


def test_rare_select_survives_analysis_exception(tmp_path, monkeypatch):
    from tests.service.test_engines import test_rare_v24_fixture_and_context_api

    def broken(*a):
        raise RuntimeError("synthetic analysis failure")

    real_select = engines.rare_select
    calls = []

    def select(*a):
        result = real_select(*a)
        assert result.rare_analysis is None and result.preview and result.budget_b > 0
        calls.append(result.selection_id)
        return result

    monkeypatch.setattr(ra, "build", broken)
    monkeypatch.setitem(engines.ENGINES, "rare_v24", select)
    test_rare_v24_fixture_and_context_api(tmp_path, monkeypatch)
    assert len(calls) == 2


def _response(analysis):
    return dict(selectionId="sid", params={}, poolSize=10, budgetB=3, rareAnalysis=analysis)


def test_pydantic_camel_case(sample):
    analysis = ra.label_free(*sample)
    analysis.update(evaluation=None, evaluationReason="no_annotations")
    result = SelectionResult.model_validate(_response(analysis)).model_dump(by_alias=True)
    assert result["rareAnalysis"]["tagRates"][0]["selectedPct"] == .3333
    assert SelectionResult.model_validate(_response(None)).rare_analysis is None
