"""run_lidar_selection trên job dựng bằng CLI lidar_index + lidar_t0."""
import copy
import json

import numpy as np
import pytest

from c4.cli import lidar_index, lidar_t0
from c4.contracts import read_table, write_table
from c4.lidar import load_lidar_config
from c4.lidar.params import LidarParams
from c4.lidar.t1_signals import compute_t1_signals
from c4.lidar.web_run import run_lidar_selection
from c4.lidar.web_selection import available_tiers, params_schema_for_job
from tests.fixtures.make_nuscenes import make_nuscenes


@pytest.fixture
def job(tmp_path, monkeypatch):
    c = copy.deepcopy(load_lidar_config())
    c["filter"]["min_points"] = 50
    monkeypatch.setattr(lidar_t0, "load_lidar_config", lambda: c)
    root = make_nuscenes(tmp_path, n_scenes=4, frames_per_scene=8, with_annotations=True)
    j = tmp_path / "job"
    assert lidar_index.main(["--data-root", str(root), "--job-dir", str(j)]) == 0
    assert lidar_t0.main(["--data-root", str(root), "--job-dir", str(j)]) == 0
    return j


def test_tier0_result_shape(job):
    assert available_tiers(job) == [0]
    assert params_schema_for_job(job)["tierAvailable"] == [0]
    r = run_lidar_selection(job, LidarParams())
    assert r["pipeline"] == "lidar" and r["tierAvailable"] == [0]
    assert r["budgetB"] >= 1 and r["poolSize"] == 32
    assert r["preview"] and all("rRar" in p for p in r["preview"])
    assert all(p["rNov"] == 0 and p["rUnc"] == 0 for p in r["preview"])
    assert r["params"]["tier"] == 0 and r["params"]["m"] == 4
    assert r["metrics"] is not None  # job có GT


def test_cache_returns_same_selection_without_rewrite(job):
    r1 = run_lidar_selection(job, LidarParams())
    res = job / "out" / "selections" / r1["selectionId"] / "result.json"
    m1 = res.stat().st_mtime_ns
    r2 = run_lidar_selection(job, LidarParams())
    assert r2["selectionId"] == r1["selectionId"] and r2 == r1
    assert res.stat().st_mtime_ns == m1
    assert json.loads(res.read_text(encoding="utf-8")) == r1


@pytest.mark.parametrize("kw", [dict(k=2), dict(lam=1.5), dict(alpha=-1)])
def test_out_of_domain_params_raise(job, kw):
    with pytest.raises(ValueError):
        run_lidar_selection(job, LidarParams(**kw))


def test_tier1_unavailable(job):
    with pytest.raises(ValueError, match="^tier_unavailable"):
        run_lidar_selection(job, LidarParams(tier=1))


def test_quota_off_gives_m_none(job):
    r = run_lidar_selection(job, LidarParams(quota_off=True))
    assert r["params"]["m"] is None and r["params"]["quotaOff"] is True


def test_tier1_with_signals(job):
    index = read_table(job / "lidar" / "index.parquet", "lidar_index")
    rng = np.random.default_rng(1)
    z1 = rng.normal(size=(len(index), 8)).astype(np.float32)
    preds = [dict(sample_token=t, boxes=rng.uniform(-9, 9, (2, 7)).astype(np.float32),
                  labels=np.array([0, 1], np.int32), scores=np.array([0.5, 0.9], np.float32))
             for t in index["sample_token"]]
    sig = compute_t1_signals(index, preds, preds, z1, (index["frame_idx"] == 0).to_numpy(),
                  load_lidar_config())
    (job / "t1").mkdir()
    write_table(sig, str(job / "t1" / "signals.parquet"), "t1_signals")
    assert available_tiers(job) == [0, 1]
    r = run_lidar_selection(job, LidarParams())  # tier mặc định = 1
    assert r["params"]["tier"] == 1 and r["tierAvailable"] == [0, 1]
    assert any(p["rNov"] > 0 or p["rUnc"] > 0 for p in r["preview"])
