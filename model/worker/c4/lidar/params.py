"""Tham số chọn của pipeline LiDAR (01-CONTRACTS §3) và lược đồ cho panel ẩn của web."""
from dataclasses import dataclass


@dataclass
class LidarParams:
    budget: float = 0.05
    preset: str = "balanced"
    diversity: str = "medium"
    tier: int | None = None
    k: int | None = None
    lam: float | None = None
    max_per_scene: int | None = None
    quota_off: bool = False
    alpha: float | None = None
    beta: float | None = None
    gamma: float | None = None


@dataclass(frozen=True)
class LidarResolved:
    budget: float
    tier: int
    k: int
    lam: float
    m: int | None
    alpha: float
    beta: float
    gamma: float


def resolve(p: LidarParams, cfg: dict, tier_available: list[int]) -> tuple[LidarResolved, list]:
    d = cfg["defaults"]
    warnings = []
    tier = p.tier if p.tier is not None else max(tier_available)
    if tier not in tier_available:
        raise ValueError(f"tier_unavailable: tầng {tier} chưa có (cần chạy model seed)")
    if p.preset not in cfg["presets"]:
        raise ValueError(f"Chiến lược không hợp lệ: {p.preset}")
    if p.diversity not in cfg["diversity"]:
        raise ValueError(f"Mức đa dạng không hợp lệ: {p.diversity}")
    if any(v is not None for v in (p.alpha, p.beta, p.gamma)):
        w = [float(v or 0) for v in (p.alpha, p.beta, p.gamma)]
        if min(w) < 0 or sum(w) <= 0:
            raise ValueError("Trọng số α, β, γ phải không âm và có tổng lớn hơn 0")
    elif tier == 1:
        w = list(cfg["presets"][p.preset])
    else:
        w = [d["alpha"], d["beta"], d["gamma"]]
    if tier == 0 and (w[1] > 0 or w[2] > 0):
        warnings.append("Tầng 0 chỉ dùng Rarity: β, γ được đặt về 0")
        w = [1.0, 0.0, 0.0]
    s = sum(w)
    lam = p.lam if p.lam is not None else cfg["diversity"][p.diversity]
    if not 0 <= lam <= 1:
        raise ValueError("λ phải trong [0, 1]")
    k = int(p.k if p.k is not None else d["k"])
    if not 3 <= k <= 50:
        raise ValueError("k phải trong [3, 50]")
    m = None if p.quota_off else int(p.max_per_scene or d["m"])
    return LidarResolved(budget=min(max(p.budget, 0.01), 0.10), tier=tier, k=k, lam=float(lam),
                         m=m, alpha=w[0] / s, beta=w[1] / s, gamma=w[2] / s), warnings


def params_schema(cfg: dict, tier_available: list[int]) -> dict:
    """Lược đồ cho panel "Tham số nâng cao" của web. Hợp đồng (01-CONTRACTS §4) giữ `key`, `type`,
    `min`, `max`, `step`, `default`; các trường hiển thị là lời thường cho người dùng, KHÔNG dùng ký
    hiệu toán (người dùng 2026-10-08): `label`, `help`, `minLabel`/`maxLabel` (hai đầu thanh trượt),
    `display` ("choice" | "count" | "percent" | "toggle"), `unit`, `options` (lựa chọn rời rạc),
    `group` (trường cùng nhóm hiển thị chung)."""
    d = cfg["defaults"]
    basic_only = tier_available == [0]
    f = [
        dict(key="tier", label="Cách đánh giá frame", type="int", min=0, max=1, step=1,
             default=max(tier_available), display="choice",
             help="Cơ bản chỉ nhìn hình dạng point cloud, chạy nhanh, không cần model. Nâng cao "
                  "dùng thêm model AI đã học để tìm frame model còn lạ hoặc chưa chắc chắn.",
             options=[
                 dict(value=0, label="Cơ bản", hint="Hình dạng point cloud"),
                 dict(value=1, label="Nâng cao", hint="Có thêm model AI",
                      disabledReason=("Chưa có model đã huấn luyện cho dữ liệu này"
                                      if basic_only else None)),
             ]),
        dict(key="k", label="Số frame giống nhất để so sánh độ hiếm", type="int", min=3, max=50,
             step=1, default=d["k"], display="count", unit="frame",
             minLabel="So sát (nhạy với khác biệt nhỏ)", maxLabel="So rộng (ổn định hơn)",
             help="Một frame được coi là hiếm khi nó khác xa những frame giống nó nhất ở các cảnh "
                  "khác. Con số này là số frame giống nhất được dùng để so sánh."),
        dict(key="lam", label="Ưu tiên khi chọn", type="float", min=0, max=1, step=0.05,
             default=d["lam"], display="percent", minLabel="Đa dạng nhất",
             maxLabel="Hiếm nhất",
             help="Kéo về phía Hiếm nhất để lấy những frame hiếm nhất dù có thể giống nhau; kéo "
                  "về phía Đa dạng nhất để tránh chọn nhiều frame na ná nhau."),
        dict(key="maxPerScene", label="Tối đa số frame lấy từ mỗi cảnh", type="int", min=1,
             max=50, step=1, default=d["m"], display="count", unit="frame",
             help="Giới hạn để tập chọn không dồn quá nhiều frame vào một đoạn đường."),
        dict(key="quotaOff", label="Không giới hạn số frame mỗi cảnh", type="bool", min=None,
             max=None, step=None, default=False, display="toggle"),
        dict(key="alpha", label="Hiếm trong dữ liệu", type="float", min=0, max=1, step=0.05,
             default=d["alpha"], display="percent", group="weights",
             help="Frame có hình dạng ít gặp so với phần còn lại của bộ dữ liệu."),
        dict(key="beta", label="Lạ với model", type="float", min=0, max=1, step=0.05,
             default=d["beta"], display="percent", group="weights",
             help="Frame khác với những gì model đã được học (cần chế độ Nâng cao)."),
        dict(key="gamma", label="Model chưa chắc chắn", type="float", min=0, max=1, step=0.05,
             default=d["gamma"], display="percent", group="weights",
             help="Frame mà model đoán dao động hoặc thiếu tự tin (cần chế độ Nâng cao)."),
    ]
    groups = dict(weights=dict(
        label="Mức quan trọng của từng tiêu chí",
        help="Tự quy đổi để tổng luôn là 100%.",
        basicNote="Chế độ Cơ bản chỉ dùng tiêu chí Hiếm trong dữ liệu."))
    return dict(fields=f, groups=groups, tierAvailable=tier_available)
