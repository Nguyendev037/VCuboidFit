"""Nạp `configs/rare_def_v24.yaml` (planning/10 SPEC-P01 §3) và
`configs/candidates_v1.yaml` (planning/13) kèm sha256 để ghi vào manifest."""
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


@dataclass(frozen=True)
class CandidateCfg:
    version: str = "cand-v1"
    ego_exclusion: tuple[float, float, float, float] = (-1.5, 3.5, -1.2, 1.2)
    pp_min_score: float = 0.3


def load_candidate_cfg(path: Path | None = None) -> tuple[CandidateCfg, str]:
    p = Path(path) if path else CONFIG_DIR / "candidates_v1.yaml"
    raw = p.read_bytes()
    d = yaml.safe_load(raw.decode("utf-8"))
    try:
        ego_exclusion = tuple(float(d["ego_exclusion"][k])
                              for k in ("x_min", "x_max", "y_min", "y_max"))
    except (KeyError, TypeError, ValueError) as e:
        raise ValueError(f"{p.name}: ego_exclusion cần x_min, x_max, y_min, y_max dạng số") from e
    try:
        pp_min_score = float(d["pp_min_score"])
    except (KeyError, TypeError, ValueError) as e:
        raise ValueError(f"{p.name}: pp_min_score cần giá trị dạng số") from e
    return CandidateCfg(version=str(d["version"]), ego_exclusion=ego_exclusion,
                        pp_min_score=pp_min_score), hashlib.sha256(raw).hexdigest()
