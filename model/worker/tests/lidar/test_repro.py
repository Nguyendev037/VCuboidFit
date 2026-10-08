"""set_determinism trả đủ khoá và đặt đúng cờ (CPU, không cần GPU) — SPEC-P01 §3."""
import os

import pytest

torch = pytest.importorskip("torch")

from c4.lidar.tier1.repro import set_determinism  # noqa: E402


def test_set_determinism_keys_and_flags():
    d = set_determinism(0)
    assert set(d) == {"seed", "PYTHONHASHSEED", "CUBLAS_WORKSPACE_CONFIG",
                      "cudnn_deterministic", "cudnn_benchmark"}
    assert d["seed"] == 0 and os.environ["PYTHONHASHSEED"] == "0"
    assert os.environ["CUBLAS_WORKSPACE_CONFIG"] == ":4096:8"
    assert torch.backends.cudnn.deterministic is True
    assert torch.backends.cudnn.benchmark is False
