import math
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

from c4.params import SelectParams
from c4.pipeline import run_selection
from tests.fixtures.make_fixture import make_fixture, write_job_dir

KEYS = {"selectionId", "params", "poolSize", "budgetB", "warnings", "metrics", "preview",
        "analysis"}
SUMMARY = {"rank", "sampleToken", "sceneToken", "frameIdx", "bestCam", "S", "rNov", "rUnc",
           "rQry", "qryBest", "reason", "tags", "camsAvailable"}


@pytest.fixture
def big_job(tmp_path):
    return write_job_dir(make_fixture(n_scenes=20, frames_per_scene=20), tmp_path / "job")


def test_run_selection_end_to_end(big_job):
    res = run_selection(big_job, SelectParams())
    assert set(res) == KEYS
    assert res["poolSize"] == 400 and res["budgetB"] == math.ceil(0.05 * 400)
    assert res["metrics"]["hybrid"]["uplift"] > 1
    assert len(res["preview"]) == 12 and set(res["preview"][0]) == SUMMARY
    d = big_job / "out" / "selections" / res["selectionId"]
    for name in ["frame_scores.csv", "selected.csv", "result.json"]:
        assert (d / name).exists(), name


def test_run_selection_idempotent_cache(big_job):
    a = run_selection(big_job, SelectParams())
    p = big_job / "out" / "selections" / a["selectionId"] / "result.json"
    mtime = p.stat().st_mtime_ns
    b = run_selection(big_job, SelectParams())
    assert a["selectionId"] == b["selectionId"] and p.stat().st_mtime_ns == mtime
    c = run_selection(big_job, SelectParams(preset="rare_first"))
    assert c["selectionId"] != a["selectionId"]


def test_run_selection_without_gt(big_job):
    shutil.rmtree(big_job / "gt")
    res = run_selection(big_job, SelectParams())
    assert res["metrics"] is None
    assert res["analysis"]["pool"]["rareGt"] is None


def test_new_queries_require_encoder(big_job):
    with pytest.raises(ValueError, match="text encoder"):
        run_selection(big_job, SelectParams(queries=["a red truck"]))


def test_deterministic_selected_csv(tmp_path):
    fx = make_fixture(n_scenes=20, frames_per_scene=20)
    a, b = write_job_dir(fx, tmp_path / "a"), write_job_dir(fx, tmp_path / "b")
    ra, rb = run_selection(a, SelectParams()), run_selection(b, SelectParams())
    fa = a / "out/selections" / ra["selectionId"] / "selected.csv"
    fb = b / "out/selections" / rb["selectionId"] / "selected.csv"
    assert fa.read_bytes() == fb.read_bytes()


def test_cli_exit_code_missing_input(tmp_path):
    worker = Path(__file__).resolve().parent.parent
    p = subprocess.run([sys.executable, "-m", "c4.cli.select", "--job-dir", str(tmp_path)],
                       cwd=worker, capture_output=True, text=True, check=False)
    assert p.returncode == 4, p.stderr


def test_cli_prints_result_path(big_job):
    worker = Path(__file__).resolve().parent.parent
    p = subprocess.run([sys.executable, "-m", "c4.cli.select", "--job-dir", str(big_job),
                        "--preset", "hard_for_model"],
                       cwd=worker, capture_output=True, text=True, check=False)
    assert p.returncode == 0, p.stderr
    assert Path(p.stdout.strip()).name == "result.json"


def test_cache_invalidated_by_config_change(big_job):
    from c4.config import load_config
    a = run_selection(big_job, SelectParams())
    cfg = load_config()
    cfg.eval = {**cfg.eval, "random_seeds": [7, 8, 9]}
    b = run_selection(big_job, SelectParams(), cfg=cfg)
    assert a["selectionId"] != b["selectionId"]


def test_cache_invalidated_by_new_features(tmp_path):
    job = write_job_dir(make_fixture(n_scenes=6, frames_per_scene=20), tmp_path / "job")
    a = run_selection(job, SelectParams())
    write_job_dir(make_fixture(n_scenes=8, frames_per_scene=20), job)
    b = run_selection(job, SelectParams())
    assert a["selectionId"] != b["selectionId"] and b["poolSize"] == 160
    assert b["analysis"]["pool"]["frames"] == 160


def test_all_bad_end_to_end(tmp_path):
    fx = make_fixture(n_scenes=6, frames_per_scene=20)
    fx.feat["q_bright"] = 0.0
    res = run_selection(write_job_dir(fx, tmp_path / "job"), SelectParams())
    assert res["warnings"] and res["preview"] == []
    assert res["analysis"]["pool"]["unlabelable"]["total"]["count"] == 120
    assert res["analysis"]["pool"]["highValue"]["count"] == 0


def test_atomic_json_is_thread_safe(tmp_path):
    import json
    import threading

    from c4.pipeline import _atomic_json
    target, errors = tmp_path / "r.json", []

    def work(i):
        try:
            for _ in range(40):
                _atomic_json({"i": i, "pad": "x" * 5000}, target)
        except Exception as e:  # noqa: BLE001
            errors.append(e)

    threads = [threading.Thread(target=work, args=(i,)) for i in range(4)]
    [t.start() for t in threads]
    [t.join() for t in threads]
    assert not errors, errors[:1]
    assert json.loads(target.read_text(encoding="utf-8"))["pad"] == "x" * 5000


def test_cli_invalid_preset_exit_2_and_utf8_stderr(big_job):
    worker = Path(__file__).resolve().parent.parent
    env = {k: v for k, v in __import__("os").environ.items() if k != "PYTHONIOENCODING"}
    p = subprocess.run([sys.executable, "-m", "c4.cli.select", "--job-dir", str(big_job),
                        "--preset", "nope"], cwd=worker, capture_output=True, check=False, env=env)
    assert p.returncode == 2
    assert "Chiến lược không hợp lệ" in p.stderr.decode("utf-8")


def test_camera_filter_end_to_end(big_job):
    from c4.contracts import read_table
    res = run_selection(big_job, SelectParams(cameras=["CAM_FRONT"]))
    feat = read_table(big_job / "cache" / "features_cache.parquet", "features_cache")
    has_front = set(feat.loc[feat["cam"] == "CAM_FRONT", "sample_token"])
    sel = __import__("pandas").read_csv(
        big_job / "out" / "selections" / res["selectionId"] / "selected.csv")
    hybrid = sel[sel["method"] == "hybrid"]
    assert len(hybrid) > 0 and set(hybrid["sample_token"]) <= has_front
    assert res["analysis"]["pool"]["excludedByCamera"]["count"] > 0


def test_text_cache_is_lru_bounded():
    import numpy as np
    import pandas as pd

    from c4.mining import query as q

    class Enc:
        def encode(self, texts):
            return np.ones((len(texts), 4), np.float32)

    q._TEXT_CACHE.clear()
    feat = pd.DataFrame(dict(emb_row=[0, 1]))
    C = np.ones((2, 4), np.float32)
    for i in range(q.TEXT_CACHE_MAX + 10):
        q.apply_queries(feat, C, [{"id": "a", "text": f"query {i}"}], Enc())
    assert len(q._TEXT_CACHE) == q.TEXT_CACHE_MAX == 32
