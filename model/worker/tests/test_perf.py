import time

import pytest

from c4.params import SelectParams
from c4.pipeline import run_selection
from tests.fixtures.make_fixture import make_fixture, write_job_dir


@pytest.mark.perf
def test_perf_10k_frames(tmp_path):
    fx = make_fixture(n_scenes=1667, frames_per_scene=6, d=768, seed=1)
    job = write_job_dir(fx, tmp_path / "job")
    run_selection(job, SelectParams())  # lần đầu: làm nóng cache theo job (nhóm trùng lặp)
    t = time.perf_counter()
    res = run_selection(job, SelectParams(preset="rare_first", diversity="high"))
    elapsed = time.perf_counter() - t
    assert res["poolSize"] >= 10_000
    assert elapsed < 3.0, f"{elapsed:.2f}s"
