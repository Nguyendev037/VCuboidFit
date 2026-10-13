import numpy as np
import pytest
import yaml

from c4.context import clip_axes
from c4.context.clip_axes import ContextConfigError, axis_probs, encode_axes, load_axes
from c4.extract.fake import fake_embed


class _FakeEnc:
    """Như FakeTextEncoder nhưng không import c4.extract.clip (torch) — venv CPU chạy được."""
    logit_scale = 100.0

    def encode(self, texts):
        return fake_embed(list(texts), 512, seed=7)


def test_axes_softmax_per_axis_with_logit_scale():
    enc = _FakeEnc()
    T = encode_axes(load_axes(), enc)
    assert set(T) == {"illum", "glare", "lens", "weather"}
    C = np.stack([T["illum"][2], T["glare"][1], T["lens"][0], T["weather"][1]])
    p = axis_probs(C, T, enc.logit_scale)
    for k, v in p.items():
        assert v.shape == (4, 3)
        np.testing.assert_allclose(v.sum(axis=1), 1.0, atol=1e-5)
    for row, (axis, cls) in enumerate([("illum", 2), ("glare", 1), ("lens", 0), ("weather", 1)]):
        assert p[axis][row].argmax() == cls and p[axis][row].max() > 0.9


def test_bad_yaml_raises_context_config_error(tmp_path):
    d = yaml.safe_load(clip_axes.AXES_PATH.read_text("utf-8"))
    d["axes"][0]["prompts"]["day"].pop()  # chỉ còn 2 prompt
    f = tmp_path / "axes.yaml"
    f.write_text(yaml.safe_dump(d), encoding="utf-8")
    with pytest.raises(ContextConfigError):
        load_axes(f)
