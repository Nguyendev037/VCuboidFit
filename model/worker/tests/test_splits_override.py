"""Legacy split snapshots and external override failures (no engine branch rewrites)."""
import json
import math

import numpy as np
import pandas as pd
import pytest

from c4.contracts import ContractError
from c4.lidar import load_lidar_config, nusc_splits
from c4.lidar.splits import plan_splits


def legacy_snapshot(scene_names, cfg):
    """Frozen pre-H03 implementation, HEAD 16fa20f; serialize to detect ordering changes."""
    names = sorted(set(scene_names))
    sp = cfg["splits"]
    rng = np.random.default_rng(sp["seed"])
    mini = set(nusc_splits.MINI_TRAIN) | set(nusc_splits.MINI_VAL)
    if set(names) <= mini:
        test = [n for n in names if n in sp["mini"]["T"]]
        train = [n for n in names if n not in test]
        n_s, n_v = sp["mini"]["S"], sp["mini"]["V"]
    elif set(names) <= set(nusc_splits.TRAIN) | set(nusc_splits.VAL):
        test = [n for n in names if n in set(nusc_splits.VAL)]
        train = [n for n in names if n not in set(test)]
        n_s = math.ceil(sp["S_frac"] * len(train))
        n_v = min(sp["V_scenes"], max(len(train) - n_s - 1, 0))
    else:
        return {n: "pool" for n in names}
    train = list(rng.permutation(train))
    out = {n: "T" for n in test}
    out.update({n: "S" for n in train[:n_s]})
    out.update({n: "V" for n in train[n_s:n_s + n_v]})
    out.update({n: "P" for n in train[n_s + n_v:]})
    return out


@pytest.mark.parametrize("names", [sorted(set(nusc_splits.MINI_TRAIN) | set(nusc_splits.MINI_VAL)),
    sorted(set(nusc_splits.TRAIN))[:120] + sorted(set(nusc_splits.VAL))[:12],
    ["pandaset-001", "av2-log-0"]])
def test_legacy_snapshot_byte_identical(names):
    cfg = load_lidar_config()
    expected = json.dumps(legacy_snapshot(names, cfg)).encode()
    assert json.dumps(plan_splits(names, cfg)).encode() == expected
    cfg["splits"]["override_file"] = None
    assert json.dumps(plan_splits(names, cfg)).encode() == expected


def test_override_exact_mapping(tmp_path):
    path = tmp_path / "split.parquet"
    pd.DataFrame(dict(scene_name=["a", "b", "c"], engine_split=["V", "T", "P"])).to_parquet(path)
    assert plan_splits(["c", "b", "a"], {"splits": {"override_file": path}}) == {"a": "V", "b": "T", "c": "P"}


@pytest.mark.parametrize("data", [dict(scene_name=["a"], engine_split=["T"]),
    dict(scene_name=["a", "a"], engine_split=["V", "T"]),
    dict(scene_name=["a", "b"], engine_split=["V", "CAL"]),
    dict(scene_name=["a", "b"], engine_split=["V", None]), dict(other=[1])])
def test_override_contract_errors(tmp_path, data):
    path = tmp_path / "split.parquet"
    pd.DataFrame(data).to_parquet(path)
    with pytest.raises(ContractError):
        plan_splits(["a", "b"], {"splits": {"override_file": path}})


def test_override_missing_file(tmp_path):
    with pytest.raises(ContractError):
        plan_splits(["a"], {"splits": {"override_file": tmp_path / "missing.parquet"}})
