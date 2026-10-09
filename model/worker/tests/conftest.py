import importlib.util
import os

import pytest

from tests.fixtures.make_fixture import make_fixture, write_job_dir


@pytest.fixture(scope="session", autouse=True)
def _clean_vcf_env():
    """Máy dev có thể đặt sẵn VCF_T1_EXP/VCF_REMOTE_TOKEN/VCF_PORT trong env người dùng. Xoá ở mức
    session (trước cả fixture scope=module chạy job); test nào cần thì tự đặt bằng monkeypatch."""
    old = {k: os.environ.pop(k) for k in ("VCF_T1_EXP", "VCF_REMOTE_TOKEN", "VCF_PORT")
           if k in os.environ}
    yield
    os.environ.update(old)


@pytest.fixture
def fx():
    return make_fixture()


@pytest.fixture
def job_dir(tmp_path, fx):
    return write_job_dir(fx, tmp_path / "job")


# Bản CPU (không cài `.[gpu]`): pipeline LiDAR không cần torch; chỉ các module test của pipeline
# camera cũ import torch lúc nạp ⇒ không thu thập chúng (runner LiDAR đã có test_lidar e2e).
if importlib.util.find_spec("torch") is None:
    collect_ignore = ["test_extract_base.py", "test_runner.py", "test_stage_clip.py",
                      "test_stage_det.py", "test_stage_dino.py"]
