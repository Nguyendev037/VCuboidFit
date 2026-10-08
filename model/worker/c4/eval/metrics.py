# c4/eval/metrics.py · sáu metric của mục 6.1, không cần model
from collections.abc import Callable

import numpy as np
import pandas as pd

GROUP_COLS = {"A": ["A_night", "A_rain"], "B": ["B_rare_class"],
              "C": ["C_crowd", "C_low_vis", "C_far"]}
FINE_GROUPS = [c for cols in GROUP_COLS.values() for c in cols]


def recall(sel, rare):  # sel, rare: set các sample_token
    return len(sel & rare) / max(len(rare), 1)


def precision(sel, rare):
    return len(sel & rare) / max(len(sel), 1)


def uplift(sel, rare, n_pool):  # 1 = không hơn random
    return recall(sel, rare) / (len(sel) / n_pool) if sel else 0.0


def coverage(sel, groups):  # groups: dict tên nhóm -> set sample_token
    return sum(bool(sel & g) for g in groups.values()) / max(len(groups), 1)


def coverage_gain(sel, random_sels, groups):
    return coverage(sel, groups) - float(np.mean([coverage(r, groups) for r in random_sels]))


def redundancy(Z_sel, theta=0.9):  # Z_sel (B, d): embedding các frame đã chọn
    if len(Z_sel) < 2:
        return 0.0
    Z = np.asarray(Z_sel, np.float32)
    sim = Z @ Z.T
    iu = np.triu_indices(len(Z), k=1)
    return float((sim[iu] > theta).mean())


def evaluate(selections: dict, budget_B: int, n_pool: int, gt: pd.DataFrame | None,
             Z_frame_by_token: Callable[[list[str]], np.ndarray], theta: float = 0.9):
    """Chấm mọi tập chọn tại ngân sách budget_B. Không có nhãn thì trả None."""
    if gt is None:
        return None
    tok = gt["sample_token"].to_numpy()
    rare = set(tok[gt["is_rare"].to_numpy(bool)])
    by_letter = {g: set(tok[gt[cols].any(axis=1).to_numpy(bool)])
                 for g, cols in GROUP_COLS.items()}
    fine = {c: set(tok[gt[c].to_numpy(bool)]) for c in FINE_GROUPS if gt[c].any()}
    picks = {k: v.loc[v["rank"] <= budget_B, "sample_token"].tolist()
             for k, v in selections.items()}
    rand_keys = [k for k in picks if k.startswith("random_")]
    rand_sets = [set(picks[k]) for k in rand_keys]

    def metrics(tokens):
        s = set(tokens)
        return dict(recall=recall(s, rare), uplift=uplift(s, rare, n_pool),
                    precision=precision(s, rare), coverage=coverage(s, fine),
                    coverageGain=coverage_gain(s, rand_sets, fine) if rand_sets else 0.0,
                    redundancy=redundancy(Z_frame_by_token(list(tokens)), theta),
                    byGroup={g: recall(s, members) for g, members in by_letter.items()})

    rand = [metrics(picks[k]) for k in rand_keys]

    def agg(fn):
        out = {k: float(fn([m[k] for m in rand])) for k in rand[0] if k != "byGroup"}
        out["byGroup"] = {g: float(fn([m["byGroup"][g] for m in rand])) for g in GROUP_COLS}
        return out

    return dict(
        hybrid=metrics(picks["hybrid"]),
        random=dict(mean=agg(np.mean), std=agg(np.std)) if rand else None,
        ablation={k: metrics(v) for k, v in picks.items()
                  if k != "hybrid" and not k.startswith("random_")})
