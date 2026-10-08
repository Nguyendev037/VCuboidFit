import numpy as np

from c4.mining.novelty import novelty_knn


def unit(x):
    x = np.asarray(x, dtype=np.float32)
    return x / np.linalg.norm(x, axis=-1, keepdims=True)


def test_novelty_excludes_same_scene():
    a = np.tile(unit([1, 0, 0]), (5, 1))
    b = unit(np.array([[0, 1, 0], [0, 1, 0.1], [0, 1, -0.1], [0, 0.9, 0.2], [0.1, 1, 0]]))
    Z = np.vstack([a, b])
    scene = np.array([0] * 5 + [1] * 5)
    out = novelty_knn(Z, scene, np.tile(np.arange(5), 2), k=3)
    assert (out[:5] > 0.5).all()


def test_novelty_outlier_highest():
    rng = np.random.default_rng(0)
    Z = unit(np.array([1, 0, 0, 0]) + 0.05 * rng.normal(size=(20, 4)))
    Z[7] = unit([0, 0, 0, 1])
    out = novelty_knn(Z, np.arange(20), np.zeros(20, int), k=5)
    assert int(np.argmax(out)) == 7


def test_novelty_single_scene_fallback():
    Z = np.zeros((20, 3), np.float32)
    Z[:, 1] = 1.0
    Z[0:4] = unit([1, 0, 0])  # frame 0 giống hệt frame 1-3 (quá gần) và khác các frame còn lại
    out = novelty_knn(Z, np.zeros(20, int), np.arange(20), k=3, min_gap=4)
    assert not np.isnan(out).any()
    assert out.max() > 0
    assert out[0] > 0.5


def test_novelty_k_larger_than_candidates():
    Z = unit(np.eye(3))
    out = novelty_knn(Z, np.arange(3), np.zeros(3, int), k=10)
    assert np.allclose(out, 1.0)
