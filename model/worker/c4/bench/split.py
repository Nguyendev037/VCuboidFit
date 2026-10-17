"""Chia chuỗi tất định, chỉ dựa vào tên."""
import hashlib
import math


def plan_bench_split(scene_names: list[str], seed: int = 20261017,
                     frac: dict = {"CAL": 0.20, "POOL": 0.55, "EVAL": 0.25}) -> dict[str, str]:
    if set(frac) != {"CAL", "POOL", "EVAL"} or any(v < 0 for v in frac.values()):
        raise ValueError("CAL/POOL/EVAL fractions required")
    if not math.isclose(sum(frac.values()), 1.0) or len(set(scene_names)) != len(scene_names):
        raise ValueError("fractions must sum to one; names must be unique")
    names = sorted(scene_names, key=lambda n: (hashlib.sha1(f"{n}|{seed}".encode()).hexdigest(), n))
    nc, ne = round(len(names) * frac["CAL"]), round(len(names) * frac["EVAL"])
    return {n: "CAL" if i < nc else "EVAL" if i >= len(names) - ne else "POOL"
            for i, n in enumerate(names)}
