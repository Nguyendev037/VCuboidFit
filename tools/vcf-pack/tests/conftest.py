"""Dùng bộ sinh nuScenes giả của worker (sys.path + importlib, không sao chép)."""
import importlib.util
import sys
from pathlib import Path

import pytest

_WORKER = Path(__file__).resolve().parents[3] / "model" / "worker"
_FIXTURE = _WORKER / "tests" / "fixtures" / "make_nuscenes.py"


def _load_make_nuscenes():
    if str(_WORKER) not in sys.path:
        sys.path.insert(0, str(_WORKER))  # make_nuscenes imports c4.contracts
    spec = importlib.util.spec_from_file_location("vcf_fixture_make_nuscenes", _FIXTURE)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod.make_nuscenes


@pytest.fixture(scope="session")
def make_nuscenes():
    return _load_make_nuscenes()


@pytest.fixture
def nus_root(tmp_path, make_nuscenes):
    """nuScenes giả (2 scene x 6 frame): thư mục gốc chứa v1.0-mini/ và samples/."""
    return make_nuscenes(tmp_path / "src")
