import numpy as np
import pytest

from c4.mining.query import apply_queries, query_scores


class FakeEncoder:
    def __init__(self, dim):
        self.dim, self.calls = dim, 0

    def encode(self, texts):
        self.calls += 1
        T = np.zeros((len(texts), self.dim), np.float32)
        for i in range(len(texts)):
            T[i, i % self.dim] = 1.0
        return T


def test_query_max_and_best():
    C = np.array([[0, 1, 0], [1, 0, 0]], np.float32)
    T = np.array([[1, 0, 0], [0, 1, 0]], np.float32)
    mx, best = query_scores(C, T, ["q1", "q2"])
    assert list(best) == ["q2", "q1"]
    assert np.allclose(mx, 1.0)
    assert mx.dtype == np.float32


def test_apply_queries_uses_cache(fx):
    enc = FakeEncoder(fx.C_img.shape[1])
    qs = [{"id": "a", "text": "night"}, {"id": "b", "text": "rain"}]
    out1 = apply_queries(fx.feat, fx.C_img, qs, enc)
    out2 = apply_queries(fx.feat, fx.C_img, qs, enc)
    assert enc.calls == 1
    assert set(out1["qry_best"]) <= {"a", "b"}
    assert (out1["qry_max"] == out2["qry_max"]).all()


def test_empty_query_list_raises_valueerror(fx):
    with pytest.raises(ValueError):
        apply_queries(fx.feat, fx.C_img, [], FakeEncoder(16))
