"""Bọc engine đóng băng, cô lập M1 khỏi nhãn và các split khác."""
import json
import tempfile
import time
from pathlib import Path

import numpy as np

from c4.bench.gate import BenchGateError, require, sha256
from c4.contracts import read_table, write_table
from c4.rare.eval import budget

FROZEN_SHA = "e4cdde328dff3efa0cd5049d9761dd68b582914a42ede8d64164687fe427a783"


def select_ours(method: str, job: Path, root: Path, final_config: Path,
                pool_tokens: list[str], pool_split: str = "T", ref_split: str = "V") -> dict:
    """pool_split/ref_split = "V"/"V" chỉ dùng cho select CAL exploratory (power, in-sample)."""
    start = time.monotonic()
    digest = sha256(require(Path(final_config)))
    if digest != FROZEN_SHA:
        raise BenchGateError("PREREG_MISMATCH", str(final_config))
    config = json.loads(Path(final_config).read_text(encoding="utf-8"))
    # final_config (hồ sơ 11 Đ46) = DEFAULT_SCORING + quota_m + candidate_frame, không có khoá scoring
    if config.get("engine") != "rare_v24" or config.get("candidate_frame") != "ego" \
            or "quota_m" not in config:
        raise BenchGateError("MISSING_INPUT", "final_config: engine/quota_m/candidate_frame")
    scoring = {"quota_m": config["quota_m"]}
    job = Path(job)
    bmax = budget(len(pool_tokens), 0.10)
    if method == "M1":
        from c4.lidar.params import LidarParams
        from c4.lidar.pipeline import run_selection_lidar

        index = read_table(job / "lidar/index.parquet", "lidar_index")
        mask = index.sample_token.isin(pool_tokens).to_numpy()
        with tempfile.TemporaryDirectory(prefix="bench-m1-") as tmp:
            isolated = Path(tmp)
            (isolated / "lidar").mkdir()
            write_table(index.loc[mask], isolated / "lidar/index.parquet", "lidar_index")
            z = np.load(require(job / "lidar/z0.npy"))
            np.save(isolated / "lidar/z0.npy", z[mask])
            filt = read_table(require(job / "lidar/filter.parquet"), "lidar_filter")
            write_table(filt.loc[filt.sample_token.isin(pool_tokens)],
                        isolated / "lidar/filter.parquet", "lidar_filter")
            result = run_selection_lidar(isolated, LidarParams(tier=0, budget=0.10))
            out = isolated / "out/selections" / result["selectionId"]
            selected = read_table(out / "selected.csv", "lidar_selected")
            tokens = selected.loc[selected.method == "hybrid"].sort_values("rank").sample_token.tolist()
            used_dir = job / "bench" / "engine" / ("M1" if pool_split == "T" else f"M1_{pool_split}")
            used_dir.mkdir(parents=True, exist_ok=True)
            used = used_dir / "config_used.json"
            used.write_text(json.dumps(result["params"], sort_keys=True, indent=1), encoding="utf-8")
    elif method in {"OURS", "M2"}:
        from c4.rare.pipeline import run_rare_v24

        result = run_rare_v24(job, root, profile="multisensor" if method == "OURS" else "lidar_only",
                              pool_split=pool_split, ref_split=ref_split, budget_frac=0.10, scoring=scoring)
        tokens = result["ranking"][:bmax]
        used = Path(result["selection_dir"]) / "config_used.json"
    else:
        raise BenchGateError("MISSING_INPUT", f"unknown engine {method}")
    if len(tokens) != len(set(tokens)) or not set(tokens) <= set(pool_tokens):
        raise BenchGateError("ORDER_VIOLATION", f"{method} returned non-POOL tokens")
    return dict(tokens=tokens, config_sha256=sha256(require(used)),
                frozen_config_sha256=digest, config_used=str(used),
                elapsed_s=time.monotonic() - start, warnings=result.get("warnings", []),
                short=len(tokens) < bmax)
