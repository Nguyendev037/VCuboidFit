from pathlib import Path
from types import SimpleNamespace

import yaml

CONFIG_DIR = Path(__file__).resolve().parent.parent / "configs"


def _merge(base: dict, over: dict) -> dict:
    out = dict(base)
    for k, v in over.items():
        out[k] = _merge(out[k], v) if isinstance(v, dict) and isinstance(out.get(k), dict) else v
    return out


def load_config(profile: str | None = None, profiles_dir: Path | None = None) -> SimpleNamespace:
    """base.yaml trộn với profiles/<profile>.yaml. Truy cập: cfg.budget, cfg.mmr["lambda"]."""
    data = yaml.safe_load((CONFIG_DIR / "base.yaml").read_text(encoding="utf-8"))
    if profile:
        pdir = profiles_dir or CONFIG_DIR / "profiles"
        data = _merge(data, yaml.safe_load((pdir / f"{profile}.yaml").read_text("utf-8")) or {})
    return SimpleNamespace(**data)


def load_queries() -> list[dict]:
    """Tập query mặc định: [{id, text}]."""
    return yaml.safe_load((CONFIG_DIR / "queries.yaml").read_text(encoding="utf-8"))["queries"]
