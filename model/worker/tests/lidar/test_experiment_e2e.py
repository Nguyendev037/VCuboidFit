"""E2E experiment: prepare + run_split trên nuScenes giả, tín hiệu Tầng 1 giả, cổng CLI P."""
import copy
import json

import numpy as np
import pandas as pd
import pytest

from c4.cli import lidar_experiment
from c4.contracts import read_table, write_table
from c4.lidar import evaluation as ev
from c4.lidar import load_gt_config, load_lidar_config
from c4.lidar.experiment import prepare, run_split
from c4.lidar.selectors import budget
from c4.lidar.t1_signals import compute_t1_signals
from tests.fixtures.make_nuscenes import make_nuscenes

N_SCENES, FRAMES = 4, 8
N = N_SCENES * FRAMES


def _quiet(*_):
    return None


@pytest.fixture(scope="module")
def cfg():
    c = copy.deepcopy(load_lidar_config())
    c["filter"]["min_points"] = 50
    return c


@pytest.fixture(scope="module")
def env(tmp_path_factory, cfg):
    base = tmp_path_factory.mktemp("exp")
    root = make_nuscenes(base, n_scenes=N_SCENES, frames_per_scene=FRAMES, with_annotations=True)
    out = base / "runs"
    prepare(root, out, cfg, load_gt_config(), n_jobs=1, log=_quiet)
    return root, out


def _fake_t1(out, cfg):
    index = read_table(str(out / "index.parquet"), "lidar_index")
    rng = np.random.default_rng(7)

    def preds():
        res = []
        for tok in index["sample_token"]:
            n = int(rng.integers(0, 4))
            res.append(dict(sample_token=tok,
                            boxes=rng.uniform(-20, 20, (n, 7)).astype(np.float32),
                            labels=rng.integers(0, 3, n).astype(np.int32),
                            scores=rng.uniform(0.1, 0.99, n).astype(np.float32)))
        return res
    z1 = rng.normal(size=(len(index), 16)).astype(np.float32)
    seed = index["frame_idx"].to_numpy() == 0
    sig = compute_t1_signals(index, preds(), preds(), z1, seed, cfg)
    (out / "t1").mkdir(exist_ok=True)
    write_table(sig, str(out / "t1" / "signals.parquet"), "t1_signals")
    np.save(out / "t1" / "z1.npy", z1)


def test_prepare_writes_artifacts(env):
    _, out = env
    assert (out / "index.parquet").is_file()
    assert (out / "features" / "desc_raw.npz").is_file()
    gt = read_table(str(out / "gt" / "gt_rare_lidar.parquet"), "gt_rare_lidar")
    assert len(gt) == N
    index = read_table(str(out / "index.parquet"), "lidar_index")
    assert (index["split"] == "pool").all()


def test_run_split_tier0_matrix_and_determinism(env, cfg):
    _, out = env
    r1 = run_split(out, "pool", cfg, None, do_tune=True, boot_n=5, log=_quiet)
    B = budget(N, cfg["defaults"]["budget"])
    assert r1["B"] == B
    sdir = out / "pool"
    for f in ("metrics.json", "report_selection.md"):
        assert (sdir / f).is_file()
    runs = [d for d in sdir.iterdir() if d.is_dir()]
    names = {d.name for d in runs}
    assert {"random_0", "random_quota_9", "coreset_z0", "t0_rar_topk", "t0_rar_mmr",
            "oracle_label"} <= names
    assert not names & {"hybrid_mmr", "t1_nov_mmr", "t1_unc_mmr", "entropy_only"}
    for d in runs:
        sel = pd.read_csv(d / "selected_5pct.csv")
        assert len(sel) == B, d.name
        assert (d / "config.yaml").is_file()
    m = json.loads((sdir / "metrics.json").read_text(encoding="utf-8"))
    ci = m["ci95_t0"]
    assert ci is not None and 0 <= ci["low"] <= ci["high"] <= 1
    assert len(m["tune"]) == 48 and r1["B"] >= 2
    before = {d.name: pd.read_csv(d / "selected_5pct.csv")["sample_token"].tolist()
              for d in runs}
    run_split(out, "pool", cfg, None, do_tune=True, boot_n=5, log=_quiet)
    after = {d.name: pd.read_csv(d / "selected_5pct.csv")["sample_token"].tolist()
             for d in runs}
    assert before == after


def test_run_split_with_tier1_adds_runs(env, cfg):
    _, out = env
    _fake_t1(out, cfg)
    run_split(out, "pool", cfg, None, do_tune=True, boot_n=0, log=_quiet)
    names = {d.name for d in (out / "pool").iterdir() if d.is_dir()}
    assert {"hybrid_mmr", "t1_nov_mmr", "t1_unc_mmr", "entropy_only", "t1_rar_mmr"} <= names
    B = budget(N, cfg["defaults"]["budget"])
    for n in ("hybrid_mmr", "entropy_only"):
        assert len(pd.read_csv(out / "pool" / n / "selected_5pct.csv")) == B


def test_cli_p_gate_without_final_yaml(env, tmp_path, monkeypatch):
    root, out = env
    monkeypatch.setattr(lidar_experiment, "CONFIG_DIR", tmp_path)  # không có final.yaml
    argv = ["--data-root", str(root), "--out", str(out), "--split", "P"]
    assert lidar_experiment.main(argv) == 3


def test_cli_p_refuses_second_scoring(env, tmp_path, monkeypatch):
    root, _ = env
    (tmp_path / "final.yaml").write_text(
        "params: {k: 10, lam: 0.7, m: 4, weights: [1.0, 0.0, 0.0]}\n", encoding="utf-8")
    monkeypatch.setattr(lidar_experiment, "CONFIG_DIR", tmp_path)
    o = tmp_path / "o"
    (o / "P").mkdir(parents=True)
    (o / "P" / "metrics.json").write_text("{}", encoding="utf-8")
    argv = ["--data-root", str(root), "--out", str(o), "--split", "P"]
    assert lidar_experiment.main(argv) == 3
    assert not (o / "index.parquet").exists()  # từ chối TRƯỚC khi chạy prepare


def test_bootstrap_ci_bounds(env):
    _, out = env
    index = read_table(str(out / "index.parquet"), "lidar_index")
    gt = read_table(str(out / "gt" / "gt_rare_lidar.parquet"), "gt_rare_lidar")
    rng = np.random.default_rng(0)

    def run_fn(sub):
        n = budget(len(sub), 0.05)
        return list(sub["sample_token"].iloc[rng.permutation(len(sub))[:n]])
    ci = ev.bootstrap_ci(run_fn, index, lambda s: ev.Truth(gt, s), 0.05, 2.0, 20, 0)
    assert 0 <= ci["low"] <= ci["high"] <= 1
