"""Giám khảo JA/JB: ánh xạ tên lớp, struggle biên, τ lớn nhất, V2 và cổng POOL."""
import json

import numpy as np
import pandas as pd
import pytest

from c4.bench.gate import BenchGateError, freeze_selections, sha256
from c4.bench.judge import calibrate_tau, run_judge, struggle_table, validity
from c4.cli.bench_judge import main
from c4.contracts import AEB_OBJECTS


def frame_df(paths):
    return pd.DataFrame(dict(sample_token=[f"f{i}" for i in range(len(paths))],
                             cam="CAM_FRONT", img_path=list(paths)))


def fake_predictor(table):
    def predict(paths, batch):
        return [np.asarray(table[p], np.float32).reshape(-1, 6) for p in paths]

    return predict


def object_row(sample="f", ann="a", dist=10.0, pts=30, group="vru",
               x1=0.0, y1=0.0, x2=10.0, y2=60.0):
    return dict(sample_token=sample, cam="CAM_FRONT", ann_token=ann, instance_token=f"i{ann}",
                scene_token="s", category="human.pedestrian.adult", group=group,
                x1=x1, y1=y1, x2=x2, y2=y2, dist_m=dist, in_corridor=True,
                num_lidar_pts=pts)


def objects(rows):
    return pd.DataFrame(rows, columns=list(AEB_OBJECTS))


def det_row(sample, score, label=1, group="vru", box=(0.0, 0.0, 10.0, 10.0)):
    return dict(judge="JA", sample_token=sample, cam="CAM_FRONT", coco_label=label,
                group=group, score=score, x1=box[0], y1=box[1], x2=box[2], y2=box[3])


def dets(rows):
    return pd.DataFrame(rows)


@pytest.mark.parametrize("ja_label,jb_label,group", [
    (1, 0, "vru"), (2, 1, "vru"), (4, 3, "vru"),
    (3, 2, "vehicle"), (6, 5, "vehicle"), (8, 7, "vehicle"),
    (7, 6, None),
])
def test_group_mapping_by_name(ja_label, jb_label, group):
    frames = frame_df(["a.jpg"])
    ja = run_judge("JA", frames, predictor=fake_predictor(
        {"a.jpg": [[ja_label, 0.9, 0, 0, 10, 10]]}))
    jb = run_judge("JB", frames, predictor=fake_predictor(
        {"a.jpg": [[jb_label, 0.9, 0, 0, 10, 10]]}))
    if group is None:
        assert ja.empty and jb.empty
    else:
        assert ja.group.tolist() == jb.group.tolist() == [group]
        assert ja.coco_label.tolist() == [ja_label]
        assert jb.coco_label.tolist() == [jb_label]


def test_low_score_dropped_and_versions_attached():
    frames = frame_df(["a.jpg", "b.jpg"])
    got = run_judge("JA", frames, batch=1, predictor=fake_predictor(
        {"a.jpg": [[1, 0.04, 0, 0, 10, 10]], "b.jpg": [[1, 0.50, 0, 0, 10, 10]]}))
    assert got.sample_token.tolist() == ["f1"]
    assert got.attrs["versions"]["judge"] == "JA"


def test_struggle_iou_boundary():
    objs = objects([object_row(y2=10.0)])
    full = dets([det_row("f", 0.40, box=(0, 0, 10, 10))])
    st = struggle_table(full, objs, 0.50, iou_thr=0.5)
    assert st.best_iou.iloc[0] == pytest.approx(1.0)
    assert bool(st.struggle.iloc[0]) is True
    assert st.unc.iloc[0] == pytest.approx(0.60, abs=1e-6)
    edge = dets([det_row("f", 0.40, box=(0, 0, 10, 5))])  # IoU đúng 0.5
    assert struggle_table(edge, objs, 0.50, iou_thr=0.5).best_iou.iloc[0] == pytest.approx(0.5)
    below = dets([det_row("f", 0.40, box=(0, 0, 10, 4.9))])  # IoU 0.49 < 0.5
    st = struggle_table(below, objs, 0.50, iou_thr=0.5)
    assert st.best_iou.iloc[0] == 0.0 and st.best_score.iloc[0] == 0.0
    assert st.unc.iloc[0] == pytest.approx(1.0)


def test_struggle_score_boundary_and_group():
    objs = objects([object_row(y2=10.0)])
    exact = dets([det_row("f", 0.50)])
    st = struggle_table(exact, objs, 0.50)
    assert bool(st.struggle.iloc[0]) is False  # score == τ không phải struggle
    assert st.unc.iloc[0] == pytest.approx(0.5)
    below = dets([det_row("f", 0.49)])
    assert bool(struggle_table(below, objs, 0.50).struggle.iloc[0]) is True
    wrong_group = dets([det_row("f", 0.99, group="vehicle")])
    st = struggle_table(wrong_group, objs, 0.50)
    assert st.best_score.iloc[0] == 0.0 and bool(st.struggle.iloc[0]) is True


def test_oom_reduces_batch_to_one_then_gpu_oom():
    frames = frame_df(["a.jpg", "b.jpg"])
    calls = []

    def fake(paths, batch):
        calls.append(batch)
        raise RuntimeError("CUDA out of memory")

    with pytest.raises(BenchGateError, match="GPU_OOM"):
        run_judge("JA", frames, batch=4, predictor=fake)
    assert calls == [4, 2, 1]


def test_oom_reduces_batch_and_completes():
    frames = frame_df(["a.jpg", "b.jpg"])

    def fake(paths, batch):
        if batch > 1:
            raise RuntimeError("out of memory")
        return [np.asarray([[1, 0.5, 0, 0, 10, 10]], np.float32) for _ in paths]

    assert len(run_judge("JA", frames, batch=2, predictor=fake)) == 2


def easy_objects(n=10):
    return objects([object_row(sample=f"e{i}", ann=f"a{i}") for i in range(n)])


def test_calibrate_tau_picks_largest_on_grid():
    objs = easy_objects(10)
    scores = [0.90] + [round(0.91 + 0.01 * i, 2) for i in range(9)]
    det = dets([det_row(f"e{i}", score, box=(0, 0, 10, 60)) for i, score in enumerate(scores)])
    cal = calibrate_tau(det, objs)
    assert cal["found"] is True
    assert cal["iou_thr"] == pytest.approx(0.5)
    assert cal["tau"] == pytest.approx(0.91)
    assert cal["recall_easy"] == pytest.approx(0.9)
    assert cal["n_det"] == 9 and cal["n_obj"] == 10
    assert cal["precision"] == pytest.approx(1.0)


def test_calibrate_tau_falls_back_to_lower_iou():
    objs = easy_objects(10)
    scores = [0.90] + [round(0.91 + 0.01 * i, 2) for i in range(9)]
    det = dets([det_row(f"e{i}", score, box=(0, 0, 10, 27)) for i, score in enumerate(scores)])
    cal = calibrate_tau(det, objs)
    assert cal["found"] is True
    assert cal["iou_thr"] == pytest.approx(0.4)  # IoU 0.45: 0.5 trượt, 0.4 đạt
    assert cal["tau"] == pytest.approx(0.91)


def struggle_rows(entries):
    return pd.DataFrame([
        dict(judge="JA", sample_token=sample, ann_token=ann, instance_token=f"i{ann}",
             scene_token="s", group="vru", best_iou=1.0, best_score=score,
             struggle=bool(bad), unc=1.0 - score)
        for sample, ann, bad, score in entries])


def v2_objects():
    easy = [object_row(sample=f"e{i}", ann=f"a{i}") for i in range(10)]
    hard = [object_row(sample=f"h{i}", ann=f"b{i}", dist=35.0) for i in range(10)]
    return objects(easy + hard)


def test_validity_v2_monotonicity():
    entries = [(f"e{i}", f"a{i}", i < 1, 0.1 if i < 1 else 0.9) for i in range(10)]
    entries += [(f"h{i}", f"b{i}", i < 5, 0.1 if i < 5 else 0.9) for i in range(10)]
    got = validity(struggle_rows(entries), objs=v2_objects(), calibration={"found": True})
    assert got["struggle_rate_easy"] == pytest.approx(0.1)
    assert got["struggle_rate_hard"] == pytest.approx(0.5)
    assert got["v2_ratio"] == pytest.approx(5.0)
    assert got["v2_ok"] is True and got["ok"] is True
    assert got["auroc_unc_vs_miss"] == pytest.approx(1.0)
    assert got["recall_easy"] == pytest.approx(0.9)


def test_validity_v2_rejects_non_monotone_judge():
    entries = [(f"e{i}", f"a{i}", i < 5, 0.1 if i < 5 else 0.9) for i in range(10)]
    entries += [(f"h{i}", f"b{i}", i < 6, 0.1 if i < 6 else 0.9) for i in range(10)]
    got = validity(struggle_rows(entries), objs=v2_objects(), calibration={"found": True})
    assert got["v1_calibration"] is True
    assert got["v2_ratio"] == pytest.approx(1.2)
    assert got["v2_ok"] is False and got["ok"] is False


def frozen_job(tmp_path):
    bench = tmp_path / "bench"
    (bench / "judge").mkdir(parents=True)
    (bench / "bench_split.parquet").write_bytes(b"frozen split")
    (bench / "prereg.txt").write_bytes(b"preregistered\n")
    digest = sha256(bench / "prereg.txt")
    (bench / "prereg_sha256.txt").write_text(digest)
    sels = dict(schema="bench-selections/1", dataset="pandaset", B=1, n_pool=10,
                prereg_sha256=digest, split_sha256=sha256(bench / "bench_split.parquet"),
                repo_sha="abc", created_at="2026-10-17T00:00:00Z", methods={})
    freeze_selections(tmp_path, sels)
    return bench


def test_cli_pool_without_calib_exits_3(tmp_path, capsys):
    bench = frozen_job(tmp_path)
    assert main(["judge", "--split", "pool", "--job-dir", str(tmp_path)]) == 3
    result = json.loads(capsys.readouterr().out)
    assert result["error"] == "ORDER_VIOLATION"
    assert not (bench / "pool_opened.json").exists()
    assert not (bench / "judge/judge_det_JA_pool.parquet").exists()
