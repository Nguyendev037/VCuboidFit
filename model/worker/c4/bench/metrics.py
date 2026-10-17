"""SY theo instance và bootstrap scene với lô chọn cố định."""
import numpy as np
import pandas as pd

from c4.contracts import ContractError
from c4.rare.eval import (
    bootstrap_fixed, budget, captured, evaluate, normalized_yield, oracle_instance, paired_ci,
)


def _check_instances(st):
    if st.groupby("instance_token")["scene_token"].nunique().gt(1).any():
        raise ContractError("instance spans more than one scene")


def struggle_frames(st: pd.DataFrame) -> dict[str, set[str]]:
    _check_instances(st)
    return st.loc[st.struggle].groupby("instance_token")["sample_token"].agg(set).to_dict()


def sy(sel: list[str], tf: dict[str, set[str]]) -> float:
    return len(captured(sel, tf)) / len(sel) if sel else 0.0


def unc_at_b(sel: list[str], st: pd.DataFrame) -> float:
    sub = st.loc[st.sample_token.isin(sel), "unc"]
    return float(sub.mean()) if len(sub) else 0.0


def empty_rate(sel: list[str], objs: pd.DataFrame) -> float:
    return sum(t not in set(objs.sample_token) for t in sel) / len(sel) if sel else 0.0


def cohen_kappa(st_a: pd.DataFrame, st_b: pd.DataFrame) -> float:
    keys = ["sample_token", "ann_token"]
    if st_a.duplicated(keys).any() or st_b.duplicated(keys).any():
        raise ContractError("duplicate struggle labels")
    both = st_a[keys + ["struggle"]].merge(st_b[keys + ["struggle"]], on=keys)
    if both.empty:
        return 0.0
    a, b = both.struggle_x.astype(bool), both.struggle_y.astype(bool)
    observed = float((a == b).mean())
    expected = float(a.mean() * b.mean() + (1 - a.mean()) * (1 - b.mean()))
    return (observed - expected) / (1 - expected) if expected < 1 else 1.0


def holm(p_values: list[float]) -> list[float]:
    """Hiệu chỉnh Holm, trả về đúng thứ tự đầu vào."""
    out = [0.0] * len(p_values)
    prev = 0.0
    for rank, i in enumerate(sorted(range(len(out)), key=p_values.__getitem__)):
        prev = max(prev, min(1.0, (len(out) - rank) * p_values[i]))
        out[i] = prev
    return out


def _contrast(boot, values, a, b, judge):
    ci = paired_ci(boot, a, b)
    d = boot[a] - boot[b]
    p = min(1.0, 2 * min(float((d <= 0).mean()), float((d >= 0).mean())))
    return dict(a=a, b=b, judge=judge, delta=values[a] - values[b],
                lo=ci["lo"], hi=ci["hi"], p=p)


def _prefixes(methods, frac, n):
    count = budget(n, frac)
    fixed = {}
    for name, entry in methods.items():
        if name == "X0":
            if set(entry["seeds"]) != {str(i) for i in range(100)}:
                raise ContractError("X0 requires seeds 0..99")
            fixed.update({f"X0_s{k}": list(v[:count]) for k, v in entry["seeds"].items()})
        else:
            fixed[name] = list(entry["by_frac"][f"{frac:.2f}"] if "by_frac" in entry
                               else entry["tokens"][:count])
    return fixed


def bench_report(sels: dict, st: dict[str, pd.DataFrame], objs: pd.DataFrame,
                 frames: pd.DataFrame, n_boot: int = 2000, seed: int = 20261017) -> dict:
    _check_instances(objs)
    if n_boot < 1:
        raise ContractError("n_boot must be positive")
    all_st = pd.concat(list(st.values()), ignore_index=True)
    _check_instances(all_st)
    pool_frame = frames[["sample_token", "scene_token"]].drop_duplicates()
    if pool_frame.sample_token.duplicated().any() or pool_frame.empty:
        raise ContractError("POOL must have unique frames and at least one scene")
    pool = pool_frame.sample_token.tolist()
    if sels["n_pool"] != len(pool) or sels["B"] != budget(len(pool), 0.05):
        raise ContractError("POOL size/budget mismatch")
    joined = all_st.merge(pool_frame, on="sample_token", suffixes=("", "_pool"), how="left")
    if joined.scene_token_pool.isna().any() or (
            joined.scene_token != joined.scene_token_pool).any():
        raise ContractError("struggle outside POOL or wrong scene")
    out = {k: sels.get(k) for k in ("dataset", "prereg_sha256", "split_sha256", "repo_sha",
                                   "B", "n_pool", "selections_sha256")}
    label = {"nuscenes-pilot": "pilot", "pandaset": "preliminary",
             "av2": "confirmatory", "av2-sensor-val": "confirmatory"}.get(sels["dataset"])
    if label is None:
        raise ContractError("unknown dataset")
    out.update(schema="bench-report/1", label="exploratory" if sels.get("exploratory") else label,
               judges=sels.get("judges", {}), curve={})
    out["kappa_JA_JB"] = cohen_kappa(st["JA"], st["JB"]) if {"JA", "JB"} <= st.keys() else None
    primary = {}
    for frac in (0.01, 0.02, 0.05, 0.10):
        fixed = _prefixes(sels["methods"], frac, len(pool))
        for name, tokens in fixed.items():
            if len(tokens) != len(set(tokens)) or not set(tokens) <= set(pool):
                raise ContractError(f"invalid selection: {name}")
            if len(tokens) != budget(len(pool), frac) and not sels["methods"].get(
                    name, {}).get("short", False):
                raise ContractError(f"selection budget mismatch: {name}")
        methods = {m: {"empty_rate": empty_rate(v, objs), "IY_internal": None}
                   for m, v in fixed.items() if not m.startswith("X0_s")}
        if "internal_gt" in frames.attrs:
            gt_frame, gt_inst = frames.attrs["internal_gt"]
            selectors = {m: (lambda pool, b, tokens=v: tokens)
                         for m, v in fixed.items() if m in methods}
            internal = evaluate(selectors, gt_frame, gt_inst, frac=frac, axis="r2_combo",
                                capture="rare_form")
            for m in methods:
                methods[m]["IY_internal"] = internal["methods"][m]["iy"]
        random, oracle, contrasts = {}, {}, []
        for judge, table in st.items():
            tf = struggle_frames(table)
            values = {m: sy(v, tf) for m, v in fixed.items()}
            boot = bootstrap_fixed(fixed, pool_frame, tf, n_boot=n_boot, seed=seed, capture="any")
            random_cols = [m for m in fixed if m.startswith("X0_s")]
            if len(random_cols) != 100:
                raise ContractError("100 random selections required")
            values["X0"] = float(np.mean([values[m] for m in random_cols]))
            boot["X0"] = boot[random_cols].mean(axis=1)
            random[f"SY_{judge}_mean"] = values["X0"]
            random[f"SY_{judge}_p95"] = float(np.percentile([values[m] for m in random_cols], 95))
            oracle[f"SY_{judge}"] = sy(oracle_instance(pool, budget(len(pool), frac), tf), tf)
            for m in methods:
                methods[m].update({f"SY_{judge}": values[m],
                                   f"UNC_{judge}": unc_at_b(fixed[m], table),
                                   f"NY_{judge}": normalized_yield(values[m], values["X0"],
                                                                  oracle[f"SY_{judge}"])})
            rivals = [m for m in ("X1", "X2", "X3", "Xext") if m in fixed]
            if "OURS" not in fixed or not {"X1", "X2", "X3", "N1", "N2", "M1", "M2"} <= fixed.keys():
                raise ContractError("mandatory selectors missing")
            boot["Xbest"] = boot[rivals].max(axis=1)
            values["Xbest"] = max(values[m] for m in rivals)
            main = _contrast(boot, values, "OURS", "Xbest", judge)
            main["p_holm"] = None  # đối chiếu chính không thuộc họ secondary
            secondary = [_contrast(boot, values, a, b, judge) for a, b in
                         [("OURS", b) for b in ("X0", "N1", "N2", "X1", "X2", "X3", "M1")]
                         + [("M2", "M1")]]
            for row, adjusted in zip(secondary, holm([r["p"] for r in secondary])):
                row["p_holm"] = adjusted
            contrasts.extend([main, *secondary])
            if frac == 0.05:
                primary[judge] = main
        current = dict(methods=methods, random=random, oracle=oracle, contrasts=contrasts)
        out["curve"][f"{frac:.2f}"] = current
        if frac == 0.05:
            out.update(current)
    valid = [j for j in st if out["judges"].get(j, {}).get("validity", {}).get("ok") is True]
    win = out["label"] == "confirmatory" and len(valid) >= 2 and all(
        primary[j]["lo"] > 0 and all(r["delta"] > 0 and r["p_holm"] < 0.05
                                    for r in out["contrasts"] if r["judge"] == j
                                    and r["a"] == "OURS" and r["b"] in {"X0", "N1", "N2"})
        for j in valid)
    numbers = "; ".join(f"{j}: {r['delta']:.4f} [{r['lo']:.4f}; {r['hi']:.4f}]"
                        for j, r in primary.items())
    text = ("Trên Argoverse 2 (zero-shot), lô ảnh VCuboidFIT làm cả hai giám khảo AEB độc lập "
            "bỏ sót/không chắc nhiều đối tượng thật hơn bên thứ 3 mạnh nhất: " + numbers) if win else (
                "Chưa chứng minh vượt bên thứ 3 ở cỡ mẫu này: Δ = " + numbers)
    if out["label"] == "pilot":
        text = "Chạy khô pipeline, không phải kết quả."
    elif out["label"] == "preliminary":
        text = "Sơ bộ — " + text
    invalid = [j for j in st if j not in valid]
    if invalid:
        text += f" Giám khảo bị loại hoặc chưa đủ kiểm hợp lệ: {invalid}."
    if any(out["methods"][n][f"SY_{j}"] >= out["methods"]["OURS"][f"SY_{j}"]
           for n in ("N1", "N2") for j in st):
        text += " Độ khó trong lô chủ yếu đến từ chất lượng ảnh; engine chưa thêm giá trị so với heuristic rẻ."
    out["verdict"] = dict(win=bool(win), text=text)
    out["power"] = sels.get("power")
    if out["power"] is not None:
        out["verdict"]["text"] += f" MDE: {out['power'].get('mde')}."
    out["limitations"] = ([] if "internal_gt" in frames.attrs else
                          ["IY_internal chưa cung cấp; không thay bằng metric khác."])
    return out
