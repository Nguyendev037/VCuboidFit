"""M1 · chia S/V/P/T theo SCENE (PDF §2.3). Tất định theo seed; không scene nào ở hai tập."""
import math

import numpy as np
import pandas as pd

from c4.lidar import nusc_splits


def plan_splits(scene_names, cfg: dict) -> dict[str, str]:
    """scene_name → S/V/P/T. Dataset không phải nuScenes chuẩn ⇒ mọi scene là `pool`."""
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
