import pytest

from tests.fixtures.make_fixture import make_fixture, write_job_dir


@pytest.fixture
def fx():
    return make_fixture()


@pytest.fixture
def job_dir(tmp_path, fx):
    return write_job_dir(fx, tmp_path / "job")
