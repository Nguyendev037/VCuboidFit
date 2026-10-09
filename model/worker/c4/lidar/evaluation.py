"""M8 · chấm tập chọn bằng nhãn (PDF §5.2–5.3). MỘT script chấm cho mọi cấu hình.

Module DUY NHẤT (cùng `gt`) được đọc `gt_rare_lidar`. Định nghĩa đã chốt ở SPEC-P01 §6:
- redundancy = tỉ lệ frame đã chọn có một frame đã chọn KHÁC cùng scene cách ≤ delta_t_s giây;
- coverage = tỉ lệ cell hiếm của pool có ≥ 1 frame được chọn;
- byGroup[g] = recall trong nhóm g (A, B, Bp, C).
"""
import numpy as np
import pandas as pd


def redundancy_window_s() -> float:
    """Δt (giây) của Redundancy — chốt trong configs/gt.yaml (thuộc định nghĩa metric, PDF §4.5)."""
    from c4.lidar import load_gt_config

    return float(load_gt_config()["delta_t_s"])


GROUPS = {"A": "A_env", "B": "B_few", "Bp": "Bp_medium", "C": "C_sensor"}
KEYS = ["recall", "nRecall", "uplift", "precision", "sceneRecall", "coverage", "redundancy",
        "nBoxes"]


class Truth:
    """Nhãn của MỘT pool (một split) đã sắp theo thứ tự index."""

    def __init__(self, gt: pd.DataFrame, index: pd.DataFrame):
        g = gt.set_index("sample_token").loc[index["sample_token"]]
        self.tokens = index["sample_token"].to_numpy()
        self.N = len(self.tokens)
        self.rare = set(self.tokens[g["is_rare"].to_numpy(bool)])
        self.groups = {k: set(self.tokens[g[c].to_numpy(bool)]) for k, c in GROUPS.items()}
        self.n_boxes = dict(zip(self.tokens, g["n_boxes"].to_numpy()))
        self.scene = dict(zip(self.tokens, index["scene_token"].to_numpy()))
        self.time_s = dict(zip(self.tokens, index["timestamp"].to_numpy() / 1e6))
        self.env_scenes = {self.scene[t] for t in self.groups["A"]}
        self.cells_of = {t: [c for c in s.split("|") if c]
                         for t, s in zip(self.tokens, g["rare_cells"].to_numpy())}
        self.all_cells = {c for cs in self.cells_of.values() for c in cs}


def _redundancy(tokens, truth: Truth, dt: float) -> float:
    if len(tokens) < 2:
        return 0.0
    by_scene: dict[str, list[float]] = {}
    for t in tokens:
        by_scene.setdefault(truth.scene[t], []).append(truth.time_s[t])
    near = 0
    for ts in by_scene.values():
        ts = np.sort(ts)
        if len(ts) < 2:
            continue
        gap = np.diff(ts) <= dt
        near += int((np.r_[False, gap] | np.r_[gap, False]).sum())
    return near / len(tokens)


def metrics(tokens, truth: Truth, B: int, dt: float) -> dict:
    s = set(tokens)
    hit = len(s & truth.rare)
    R = len(truth.rare)
    recall = hit / R if R else 0.0
    covered = {c for t in s for c in truth.cells_of.get(t, [])}
    return dict(
        recall=recall, nRecall=hit / min(B, R) if R else 0.0,
        uplift=recall / (B / truth.N) if truth.N else 0.0, precision=hit / max(len(s), 1),
        sceneRecall=(len({truth.scene[t] for t in s} & truth.env_scenes) / len(truth.env_scenes)
                     if truth.env_scenes else 0.0),
        coverage=len(covered) / len(truth.all_cells) if truth.all_cells else 0.0,
        redundancy=_redundancy(list(s), truth, dt),
        nBoxes=int(sum(truth.n_boxes.get(t, 0) for t in s)),
        byGroup={k: (len(s & g) / len(g) if g else 0.0) for k, g in truth.groups.items()})


def top_b_tokens(sel: pd.DataFrame, B: int) -> list[str]:
    return sel.sort_values("rank").loc[lambda d: d["rank"] <= B, "sample_token"].tolist()


def aggregate(ms: list[dict]) -> dict:
    out = {}
    for fn_name, fn in (("mean", np.mean), ("std", np.std)):
        agg = {k: float(fn([m[k] for m in ms])) for k in KEYS}
        agg["byGroup"] = {g: float(fn([m["byGroup"][g] for m in ms])) for g in GROUPS}
        out[fn_name] = agg
    return out


def evaluate_runs(runs: dict[str, pd.DataFrame], truth: Truth, B: int, dt: float) -> dict:
    """runs: tên → lidar_selected. Các run `random_<seed>` / `random_quota_<seed>` gộp mean±std.
    coverageGain của mỗi run = coverage − coverage trung bình của random."""
    per = {k: metrics(top_b_tokens(v, B), truth, B, dt) for k, v in runs.items()}
    rand = [m for k, m in per.items() if k.startswith("random_") and "quota" not in k]
    rq = [m for k, m in per.items() if k.startswith("random_quota_")]
    base_cov = float(np.mean([m["coverage"] for m in rand])) if rand else 0.0
    for m in per.values():
        m["coverageGain"] = m["coverage"] - base_cov
    out = dict(runs={k: m for k, m in per.items() if not k.startswith("random")},
               random=aggregate(rand) if rand else None,
               randomQuota=aggregate(rq) if rq else None,
               expectedRandomRecall=B / truth.N if truth.N else 0.0,
               pool=dict(N=truth.N, B=B, rare=len(truth.rare),
                         groups={k: len(v) for k, v in truth.groups.items()},
                         rareCells=len(truth.all_cells)))
    return out


def oracle(truth: Truth, B: int, seed: int = 0) -> list[str]:
    """Cận trên tham chiếu: frame rare trước (nhiều cell hiếm trước), thiếu thì random."""
    rng = np.random.default_rng(seed)
    rare = sorted(truth.rare, key=lambda t: (-len(truth.cells_of[t]), t))
    rest = [t for t in truth.tokens if t not in truth.rare]
    rest = [rest[i] for i in rng.permutation(len(rest))]
    return (rare + rest)[:B]


def bootstrap_ci(run_fn, index: pd.DataFrame, truth_fn, B_frac: float, dt: float,
                 n: int, seed: int, frac: float = 0.8) -> dict:
    """CI 95% cho recall bằng lấy mẫu lại scene KHÔNG hoàn lại (m-out-of-n, 80% scene) — lặp
    lại scene sẽ tạo láng giềng khoảng cách 0 làm hỏng Rarity, nên không dùng có hoàn lại.
    run_fn(sub_index) → list token đã chọn; truth_fn(sub_index) → Truth."""
    from c4.lidar.selectors import budget

    rng = np.random.default_rng(seed)
    scenes = index["scene_token"].unique()
    k = max(2, int(round(frac * len(scenes))))
    vals = []
    for _ in range(n):
        pick = set(rng.choice(scenes, size=k, replace=False))
        sub = index[index["scene_token"].isin(pick)].reset_index(drop=True)
        B = budget(len(sub), B_frac)
        vals.append(metrics(run_fn(sub)[:B], truth_fn(sub), B, dt)["recall"])
    lo, hi = np.percentile(vals, [2.5, 97.5])
    return dict(low=float(lo), high=float(hi), n=n, frac=frac)
