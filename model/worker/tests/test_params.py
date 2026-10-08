import pytest

from c4.config import load_config
from c4.params import SelectParams, resolve


def test_resolve_preset_and_override():
    cfg = load_config()
    r = resolve(SelectParams(preset="rare_first"), cfg)
    assert (r.alpha, r.beta, r.gamma) == pytest.approx((0.6, 0.2, 0.2))
    r = resolve(SelectParams(alpha=2, beta=1, gamma=1), cfg)
    assert (r.alpha, r.beta, r.gamma) == pytest.approx((0.5, 0.25, 0.25))
    assert resolve(SelectParams(diversity="high"), cfg).lam == 0.5
    assert resolve(SelectParams(budget=0.5), cfg).budget == 0.10
    r = resolve(SelectParams(), cfg)
    assert (r.lam, r.m, r.min_gap, r.budget_max) == (0.7, 3, 4, 0.10)
    assert (r.min_luma, r.min_blur_var) == (8, 15)


def test_resolve_rejects_bad_values():
    cfg = load_config()
    with pytest.raises(ValueError):
        resolve(SelectParams(preset="nope"), cfg)
    with pytest.raises(ValueError):
        resolve(SelectParams(diversity="max"), cfg)
    with pytest.raises(ValueError):
        resolve(SelectParams(alpha=0, beta=0, gamma=0), cfg)
