"""CPU/mock coverage for SPEC-P05; no downloaded weights."""
import json
from pathlib import Path
from types import SimpleNamespace

import pandas as pd
import pytest

from c4.bench import train_sel as train
from c4.bench.gate import BenchGateError
from c4.cli import bench_judge as cli


@pytest.mark.parametrize("budget,steps", [(1, 12), (8, 72), (70, 636), (123, 1116)])
def test_fixed_steps(budget, steps):
    assert train.training_steps(budget) == steps
    assert train.RECIPE["lr"] == 0.005


def _object(ann, x, *, cam="C", scene="s"):
    return dict(sample_token="f", cam=cam, scene_token=scene, ann_token=ann,
                instance_token=f"instance-{ann}", group="vru", x1=x, y1=0, x2=x + 10, y2=20)


def _detection(x, score, *, cam="C", scene="s"):
    return dict(sample_token="f", cam=cam, scene_token=scene, group="vru",
                score=score, x1=x, y1=0, x2=x + 10, y2=20)


def test_ap50_hand_example_two_gt_three_detections_one_ignore():
    gt = pd.DataFrame([_object("a", 0), _object("b", 20), _object("ignored", 40)])
    det = pd.DataFrame([_detection(0, 0.9), _detection(40, 0.8), _detection(20, 0.7)])
    events = train._events(det, gt, ["s"], "vru", gt.iloc[:2])["s"]
    assert events == dict(tp=[1, 1], fp=[0, 0], scores=[0.9, 0.7], n_gt=2)
    assert train._merged_ap([events]) == pytest.approx(1.0)


def test_ap101_false_positive_and_duplicate_matching():
    gt = pd.DataFrame([_object("a", 0), _object("b", 20)])
    det = pd.DataFrame([_detection(0, 0.9), _detection(0, 0.8), _detection(20, 0.7)])
    events = train._events(det, gt, ["s"], "vru", gt)["s"]
    assert events["tp"] == [1, 0, 1]
    assert events["fp"] == [0, 1, 0]
    assert train._merged_ap([events]) == pytest.approx((51 + 50 * (2 / 3)) / 101)


def test_unmatched_on_empty_image_is_false_positive():
    gt = pd.DataFrame([_object("a", 0)])
    det = pd.DataFrame([_detection(0, 0.9, cam="OTHER")])
    events = train._events(det, gt, ["s", "empty"], "vru", gt)
    assert events["s"]["fp"] == [1]
    assert events["empty"]["n_gt"] == 0
    assert train._merged_ap(list(events.values())) == 0
    assert train.ap101([], [], [], 0) is None


def _metrics(ap=1.0):
    return dict(ap50_vru=ap, ap50_vehicle=None, ap50_vru_hard=ap, n_obj=2,
                per_scene={"a": dict(tp=[1], fp=[0], scores=[0.9], n_gt=1),
                           "b": dict(tp=[0], fp=[1], scores=[0.7], n_gt=1)})


def test_bootstrap_is_deterministic_and_recomputes_ap():
    left = _metrics(0.5)
    right = _metrics(0.0)
    right["per_scene"]["a"]["tp"] = [0]
    right["per_scene"]["a"]["fp"] = [1]
    first = train.bootstrap_delta([left] * 3, [right] * 3, n_boot=40)
    assert first == train.bootstrap_delta([left] * 3, [right] * 3, n_boot=40)
    assert first["delta"] == 0.5
    assert first["lo"] == 0 and first["hi"] == 1
    assert first["n_valid"] == 40


def test_bootstrap_rejects_mismatched_scenes():
    right = _metrics()
    del right["per_scene"]["b"]
    with pytest.raises(BenchGateError, match="inconsistent EVAL scenes"):
        train.bootstrap_delta([_metrics()], [right])


def test_build_train_set_all_cameras_height_and_coco_mapping(monkeypatch, tmp_path):
    frames = pd.DataFrame(dict(sample_token=["f", "f"], cam=["A", "B"],
                               img_path=["a.jpg", "b.jpg"]))
    gt = pd.DataFrame([
        dict(sample_token="f", cam="A", category=category, x1=0, y1=0, x2=10, y2=height)
        for category, height in [("human.pedestrian.adult", 8), ("vehicle.bicycle", 20),
                                  ("vehicle.car", 7), ("vehicle.bus.rigid", 20),
                                  ("animal", 20)]])
    monkeypatch.setattr(train, "_frames", lambda *a: frames)
    monkeypatch.setattr(train, "require", lambda p: p)
    monkeypatch.setattr(train, "read_table", lambda *a: gt)
    result = train.build_train_set(tmp_path, ["f"])
    assert result.labels.tolist() == [[1, 2, 6], []]
    assert result.boxes.iloc[1] == []


def test_finetune_cpu_terminal_checkpoint_and_seed(monkeypatch, tmp_path):
    import torch

    class Tiny(torch.nn.Module):
        def __init__(self):
            super().__init__()
            self.weight = torch.nn.Parameter(torch.rand(()))

        def forward(self, images, targets):
            assert len(images) == len(targets) == 8
            return {"loss": (self.weight - 1).square()}

    monkeypatch.setattr(torch.cuda, "is_available", lambda: False)
    monkeypatch.setattr(train, "build_train_set", lambda *a: pd.DataFrame([
        dict(img_path="unused", boxes=[], labels=[])]))
    monkeypatch.setattr(train, "_load_rgb", lambda p: None)
    monkeypatch.setattr(train, "_to_tensor", lambda p: torch.zeros(3, 8, 8))
    paths = [train.finetune(tmp_path, ["f"], 2, tmp_path / name, model_factory=Tiny)
             for name in ["first", "second"]]
    states = [torch.load(path, weights_only=True) for path in paths]
    assert states[0]["steps"] == 12
    assert torch.equal(states[0]["model"]["weight"], states[1]["model"]["weight"])
    lines = [json.loads(line) for line in (paths[0].parent / "train_log.jsonl").read_text()
             .splitlines()]
    assert len(lines) == 12 and lines[-1]["step"] == 12
    assert lines[0]["lr"] == pytest.approx(0.005 / 200)
    assert not (paths[0].parent / "done.json").exists()


def _mock_job(monkeypatch, tmp_path):
    sels = dict(B=2, methods={"OURS": dict(tokens=["f", "g", "extra"]),
                              "X0": dict(seeds={str(s): ["g", "f"] for s in range(3)})})
    monkeypatch.setattr(train, "check_selections", lambda job: sels)
    monkeypatch.setattr(train, "require", lambda p: p)
    monkeypatch.setattr(train, "read_table", lambda p, name: (
        pd.DataFrame(dict(bench_split=["POOL"], scene_token=["pool"]))
        if name == "bench_split" else
        pd.DataFrame(dict(sample_token=["f", "g"], scene_token=["pool", "pool"]))))
    return sels


def test_resume_skips_done_pairs_and_x0_seed_pairing(monkeypatch, tmp_path):
    sels = _mock_job(monkeypatch, tmp_path)
    trained, evaluated, gates = [], [], []

    def finetune(job, tokens, seed, out):
        trained.append((tokens, seed))
        return out / "ckpt.pt"

    def evaluate(job, ckpt):
        assert gates  # Marker callback has run before ANY evaluation.
        evaluated.append(ckpt)
        return _metrics()

    monkeypatch.setattr(train, "finetune", finetune)
    monkeypatch.setattr(train, "eval_ap", evaluate)
    done = tmp_path / "bench/train/OURS_s0/done.json"
    train._write_json(done, dict(seed=0, tokens=["f", "g"], recipe=train.RECIPE,
                                 failed=False, metrics=_metrics()))
    kwargs = dict(methods=["OURS", "X0"], seeds=[0, 1, 2], open_eval=lambda: gates.append(1))
    train.run_train_eval(tmp_path, **kwargs)
    assert len(trained) == 5
    assert trained[-3:] == [(sels["methods"]["X0"]["seeds"][str(s)], s) for s in range(3)]
    assert len(evaluated) == 6  # Five new checkpoints plus original JA.
    train.run_train_eval(tmp_path, **kwargs)
    assert len(trained) == 5 and len(evaluated) == 6
    assert len(gates) == 2
    report = json.loads((tmp_path / "bench/report/report_train.json").read_text())
    assert report["methods"]["OURS"]["n_success"] == 3
    assert report["methods"]["OURS"]["seed_std"] == 0
    assert report["strong_win"] is False


def test_nan_loss_stops_after_two_failed_pairs(monkeypatch, tmp_path):
    _mock_job(monkeypatch, tmp_path)

    def fail(*args):
        raise BenchGateError("NAN_LOSS", "injected loss")

    monkeypatch.setattr(train, "finetune", fail)
    with pytest.raises(BenchGateError, match="TRAIN_FAILED"):
        train.run_train_eval(tmp_path, ["OURS", "X0"], [0, 1, 2])
    done = list((tmp_path / "bench/train").glob("*/done.json"))
    assert len(done) == 2
    assert all(json.loads(p.read_text())["failed"] for p in done)
    assert not (tmp_path / "bench/eval_opened.json").exists()


def test_second_eval_without_exploratory_exits_three(monkeypatch, tmp_path, capsys):
    bench = tmp_path / "bench"
    bench.mkdir()
    (bench / "eval_opened.json").write_text("{}")
    (bench / "report").mkdir()
    (bench / "report" / "report_train.json").write_text("{}")  # EVAL đã dùng xong
    monkeypatch.setattr(cli, "check_selections", lambda job: {})
    monkeypatch.setattr(cli, "_late", lambda name: SimpleNamespace(run_train_eval=lambda *a, **k: {}))
    code = cli.main(["train-eval", "--job-dir", str(tmp_path)])
    assert code == 3
    assert json.loads(capsys.readouterr().out)["error"] == "ALREADY_OPENED"
    assert (bench / "eval_opened.json").read_text() == "{}"


def test_cli_passes_methods_seeds_and_exploratory(monkeypatch, tmp_path):
    monkeypatch.setattr(cli, "check_selections", lambda job: {})
    calls = []

    def run(job, methods, seeds, **kwargs):
        calls.append((job, methods, seeds, kwargs))
        return dict(report="mock")

    monkeypatch.setattr(cli, "_late", lambda name: SimpleNamespace(run_train_eval=run))
    args = SimpleNamespace(job_dir=tmp_path, methods="OURS,X0", seeds="0,1,2",
                           data_root=Path("dataset"), exploratory=True)
    assert cli._train_eval(args)["report"] == "mock"
    assert calls[0][1:3] == (["OURS", "X0"], [0, 1, 2])
    assert calls[0][3]["data_root"] == Path("dataset")
    assert calls[0][3]["exploratory"] is True


def test_eval_hard_slice_uses_original_ja(monkeypatch, tmp_path):
    valid = pd.DataFrame([_object("a", 0), _object("b", 20)])
    gt = pd.concat([valid, pd.DataFrame([_object("ignored", 40)])], ignore_index=True)
    monkeypatch.setattr(train, "_eval_data", lambda *a: (pd.DataFrame(), gt, valid, ["s"]))
    calls = []

    def predict(frames, ckpt, model_factory):
        calls.append(ckpt)
        return pd.DataFrame([_detection(0, 0.9)] if ckpt is None else
                            [_detection(0, 0.9), _detection(20, 0.8), _detection(40, 0.7)])

    monkeypatch.setattr(train, "_predict", predict)
    calib = tmp_path / "calib.json"
    calib.write_text(json.dumps(dict(JA=dict(tau=0.5, iou_thr=0.5))))
    result = train.eval_ap(tmp_path, Path("fine.pt"), tau_file=calib)
    assert calls == [None, Path("fine.pt")]
    assert result["ap50_vru"] == 1
    assert result["ap50_vru_hard"] == 1
    assert result["n_obj_hard"] == 1
    assert result["per_scene"]["s"]["vru_hard"]["n_gt"] == 1


def test_resume_after_disconnect_is_allowed_without_exploratory(monkeypatch, tmp_path, capsys):
    """Colab ngắt giữa Pha 4: marker có, report_train chưa có ⇒ chạy tiếp, không cần --exploratory."""
    bench = tmp_path / "bench"
    bench.mkdir()
    (bench / "eval_opened.json").write_text("{}")
    calls = []
    monkeypatch.setattr(cli, "check_selections", lambda job: {})
    monkeypatch.setattr(cli, "_late", lambda name: SimpleNamespace(
        run_train_eval=lambda *a, **k: calls.append(k) or {}))
    code = cli.main(["train-eval", "--job-dir", str(tmp_path)])
    assert code == 0 and calls and calls[0]["exploratory"] is False
    assert (bench / "eval_opened.json").read_text() == "{}"
