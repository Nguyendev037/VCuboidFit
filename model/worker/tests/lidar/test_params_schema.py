"""Panel "Tham số nâng cao" hiển thị lời thường, không ký hiệu toán (người dùng 2026-10-08)."""
import re

from c4.lidar import load_lidar_config
from c4.lidar.params import params_schema

MATH = re.compile(r"[αβγλσμ]|\bk\b|\bm\b|MMR|quota|Tier|tier|scene|Novelty|Rarity|Uncertainty")


def _texts(schema):
    for f in schema["fields"]:
        yield from (f.get(k) for k in ("label", "help", "minLabel", "maxLabel", "unit"))
        for o in f.get("options", []):
            yield from (o.get("label"), o.get("hint"), o.get("disabledReason"))
    for g in schema["groups"].values():
        yield from g.values()


def test_labels_are_plain_vietnamese_without_math_symbols():
    for avail in ([0], [0, 1]):
        bad = [t for t in _texts(params_schema(load_lidar_config(), avail)) if t and MATH.search(t)]
        assert not bad, bad


def test_schema_keeps_contract_keys_and_choice_options():
    s = params_schema(load_lidar_config(), [0])
    keys = [f["key"] for f in s["fields"]]
    assert keys == ["tier", "k", "lam", "maxPerScene", "quotaOff", "alpha", "beta", "gamma"]
    for f in s["fields"]:
        assert {"key", "label", "type", "min", "max", "step", "default", "display"} <= set(f)
    tier = s["fields"][0]
    assert [o["value"] for o in tier["options"]] == [0, 1]
    assert tier["options"][1]["disabledReason"]  # chưa có model ⇒ lý do khoá
    assert params_schema(load_lidar_config(), [0, 1])["fields"][0]["options"][1][
        "disabledReason"] is None
