# c4/params.py · tham số tinh chỉnh từ UI -> giá trị cụ thể cho score và MMR
from dataclasses import dataclass, field

from c4.contracts import CAMS

PRESETS = {
    "balanced": (0.4, 0.3, 0.3),
    "rare_first": (0.6, 0.2, 0.2),
    "hard_for_model": (0.2, 0.6, 0.2),
    "safety_scenarios": (0.2, 0.2, 0.6),
}
DIVERSITY = {"low": 0.9, "medium": 0.7, "high": 0.5}


@dataclass
class SelectParams:
    budget: float = 0.05
    preset: str = "balanced"
    diversity: str = "medium"
    queries: list[str] | None = None
    alpha: float | None = None
    beta: float | None = None
    gamma: float | None = None
    max_per_scene: int | None = None
    min_gap: int | None = None
    cameras: list[str] | None = None
    min_luma: float | None = None
    min_blur_var: float | None = None


@dataclass(frozen=True)
class Resolved:
    budget: float
    alpha: float
    beta: float
    gamma: float
    lam: float
    m: int
    min_gap: int
    cameras: tuple = field(default=tuple(CAMS))
    min_luma: float = 8
    min_blur_var: float = 15
    budget_max: float = 0.10


def resolve(p: SelectParams, cfg) -> Resolved:
    if p.preset not in PRESETS:
        raise ValueError(f"Chiến lược không hợp lệ: {p.preset}")
    if p.diversity not in DIVERSITY:
        raise ValueError(f"Mức đa dạng không hợp lệ: {p.diversity}")
    a, b, g = PRESETS[p.preset]
    if any(v is not None for v in (p.alpha, p.beta, p.gamma)):
        a, b, g = (float(v or 0) for v in (p.alpha, p.beta, p.gamma))
        if min(a, b, g) < 0 or a + b + g <= 0:
            raise ValueError("Trọng số α, β, γ phải không âm và có tổng lớn hơn 0")
        s = a + b + g
        a, b, g = a / s, b / s, g / s
    cams = tuple(c for c in CAMS if c in (p.cameras or CAMS))
    if not cams:
        raise ValueError("Cần chọn ít nhất một camera")
    return Resolved(
        budget=min(max(p.budget, 0.01), cfg.budget_max), alpha=a, beta=b, gamma=g,
        lam=DIVERSITY[p.diversity],
        m=int(p.max_per_scene or cfg.mmr["max_per_scene"]),
        min_gap=int(p.min_gap or cfg.mmr["min_gap"]), cameras=cams,
        min_luma=p.min_luma if p.min_luma is not None else cfg.quality["min_luma"],
        min_blur_var=(p.min_blur_var if p.min_blur_var is not None
                      else cfg.quality["min_blur_var"]),
        budget_max=cfg.budget_max)
