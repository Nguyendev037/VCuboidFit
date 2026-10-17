"""M1 · chia S/V/P/T theo SCENE (PDF §2.3). Tất định theo seed; không scene nào ở hai tập."""
import math

import numpy as np
import pandas as pd

from c4.lidar import nusc_splits


def plan_splits(scene_names, cfg: dict) -> dict[str, str]:
    """scene_name → S/V/P/T. Dataset không phải nuScenes chuẩn ⇒ mọi scene là `pool`."""
    if cfg["splits"].get("override_file"):
        from c4.contracts import ContractError

        try:
            override = pd.read_parquet(cfg["splits"]["override_file"])
        except (OSError, ValueError) as exc:
            raise ContractError(f"cannot read split override: {exc}") from exc
        if not {"scene_name", "engine_split"} <= set(override.columns):
            raise ContractError("split override requires scene_name, engine_split")
        if override[["scene_name", "engine_split"]].isna().any().any():
            raise ContractError("split override contains null values")
        if override.scene_name.duplicated().any() or not override.engine_split.isin(["S", "V", "P", "T"]).all():
            raise ContractError("split override contains duplicate scenes or invalid splits")
        mapping = dict(zip(override.scene_name, override.engine_split))
        names = sorted(set(scene_names))
        missing = [name for name in names if name not in mapping]
        if missing:
            raise ContractError(f"split override missing scenes: {missing}")
        return {name: mapping[name] for name in names}
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


def assign_splits(index: pd.DataFrame, cfg: dict) -> pd.DataFrame:
    m = plan_splits(index["scene_name"], cfg)
    return index.assign(split=index["scene_name"].map(m).astype("string"))
