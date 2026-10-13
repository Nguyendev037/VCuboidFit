"""Nạp `configs/rare_def_v24.yaml` (planning/10 SPEC-P01 §3) kèm sha256 để ghi vào manifest."""
import hashlib
from dataclasses import dataclass
from pathlib import Path

import yaml

from c4.config import CONFIG_DIR


@dataclass(frozen=True)
class RareDefV24:
    version: str = "rare_v24"
    alpha: float = 0.10
    corridor_x_max: float = 20.0
    corridor_y_abs: float = 4.0
    v_min: float = 0.5
    min_pts: int = 1
    hard_far_m: float = 30.0
    hard_few_pts: int = 10
    base_rate_cap: float = 0.10
    min_support_scenes: int = 3


def load_rare_def(path: Path | None = None) -> tuple[RareDefV24, str]:
    p = Path(path) if path else CONFIG_DIR / "rare_def_v24.yaml"
    raw = p.read_bytes()
    d = yaml.safe_load(raw.decode("utf-8"))
    cfg = RareDefV24(
        version=d["version"], alpha=float(d["alpha"]),
        corridor_x_max=float(d["corridor"]["x_max"]), corridor_y_abs=float(d["corridor"]["y_abs"]),
        v_min=float(d["v_min"]), min_pts=int(d["min_pts"]),
        hard_far_m=float(d["hard"]["far_m"]), hard_few_pts=int(d["hard"]["few_pts"]),
        base_rate_cap=float(d["base_rate_cap"]), min_support_scenes=int(d["min_support_scenes"]))
    return cfg, hashlib.sha256(raw).hexdigest()
