import importlib.util

import pytest

from tests.fixtures.make_fixture import make_fixture, write_job_dir


@pytest.fixture
def fx():
    return make_fixture()


@pytest.fixture
def job_dir(tmp_path, fx):
    return write_job_dir(fx, tmp_path / "job")


# Bản CPU (không cài `.[gpu]`): pipeline LiDAR không cần torch; chỉ các module test của pipeline
# camera cũ import torch lúc nạp ⇒ không thu thập chúng (runner LiDAR đã có test_lidar e2e).
if importlib.util.find_spec("torch") is None:
    collect_ignore = ["test_runner.py", "legacy_camera/test_extract_base.py",
                      "legacy_camera/test_stage_clip.py", "legacy_camera/test_stage_det.py",
                      "legacy_camera/test_stage_dino.py"]
