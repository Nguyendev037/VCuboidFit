import pytest

from c4.bench.gate import BenchGateError
from c4.bench.registry import FAMILIES, assert_independent


def test_declared_independent():
    assert_independent(["OURS", "M1", "M2", "X0", "X1", "X2", "X3", "N1", "N2"], ["JA", "JB"])


def test_shared_fasterrcnn_rejected(monkeypatch):
    monkeypatch.setitem(FAMILIES, "bad", {"fasterrcnn"})
    with pytest.raises(BenchGateError, match="NOT_INDEPENDENT"):
        assert_independent(["bad"], ["JA", "JB"])


def test_undeclared_external_fails_closed():
    with pytest.raises(BenchGateError, match="NOT_INDEPENDENT"):
        assert_independent(["Xext"], ["JA"])
