"""Thống kê độc lập cho notebook thẩm định — không nạp bất kỳ gói nào của dự án.

Notebook `vcf_judge_bench_review.ipynb` nhúng nguyên văn file này vào ô 4. Chuyên
gia bên ngoài có thể đọc và chạy lại toàn bộ công thức mà không cần cài `c4`.

Thuật toán rút mẫu (SPEC-P04 §3.6, sửa 2026-10-17):
  - names = sorted(scene_token duy nhất của POOL)
  - nsel_m[k] = số sample_token của bên m thuộc scene names[k]
  - cap_m[k]  = số instance i ∈ captured(Sel_m, tf) có scene(i) = names[k]
  - rng = numpy.random.default_rng(seed), MỘT rng cho mọi lượt và mọi bên
  - lượt b: idx = rng.integers(0, len(names), size=len(names))
            SY_b[m] = cap_m[idx].sum() / max(nsel_m[idx].sum(), 1.0)
            (scene lặp ⇒ đếm lặp, không khử trùng)
  - Xbest_b = max(SY_b[X1], SY_b[X2], SY_b[X3], SY_b[Xext nếu có]) mỗi lượt
  - D_b = SY_b[OURS] − Xbest_b; CI = numpy.percentile(D_b, [2.5, 97.5])
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

import numpy as np
import pandas as pd


# ─── Chuyển bảng struggle thành ánh xạ instance → frame ──────────────────────

def tf_from_struggle(struggle_df: pd.DataFrame) -> dict[str, set[str]]:
    """Trả về {instance_token: {sample_token struggle}}.

    Mỗi instance chỉ được thuộc một scene (SPEC-P04 §3.5); vi phạm ⇒ ValueError.
    """
    needed = {"struggle", "instance_token", "sample_token", "scene_token"}
    if not needed <= set(struggle_df.columns):
        raise ValueError(f"struggle thiếu cột {sorted(needed - set(struggle_df.columns))}")
    ok = struggle_df[struggle_df["struggle"]]
    if ok.empty:
        return {}
    span = ok.groupby("instance_token")["scene_token"].nunique()
    if bool((span > 1).any()):
        bad = span[span > 1].index.tolist()
        raise ValueError(f"instance spans more than one scene: {bad}")
    return ok.groupby("instance_token")["sample_token"].agg(set).to_dict()


# ─── Chỉ mục scene và hai mảng nsel/cap ──────────────────────────────────────

def _scene_lookup(pool_frames: pd.DataFrame) -> tuple[dict[str, str], list[str], dict[str, int]]:
    """Bản đồ sample_token → scene_token, danh sách scene đã sắp, và vị trí."""
    needed = {"sample_token", "scene_token"}
    if not needed <= set(pool_frames.columns):
        raise ValueError(f"pool_frames thiếu cột {sorted(needed - set(pool_frames.columns))}")
    frame = pool_frames[["sample_token", "scene_token"]].drop_duplicates()
    if frame.empty:
        raise ValueError("pool_frames rỗng")
    if bool(frame["sample_token"].duplicated().any()):
        raise ValueError("pool_frames có sample_token trùng")
    scene_of = dict(zip(frame["sample_token"], frame["scene_token"]))
    names = sorted(set(scene_of.values()))
    if not names:
        raise ValueError("POOL không có scene")
    return scene_of, names, {name: i for i, name in enumerate(names)}


def _scene_arrays(
    sel: list[str],
    tf: dict[str, set[str]],
    scene_of: dict[str, str],
    names: list[str],
    pos: dict[str, int],
) -> tuple[np.ndarray, np.ndarray]:
    """Dựng nsel[k] và cap[k] cho một bên theo SPEC-P04 §3.6."""
    nsel = np.zeros(len(names), dtype=np.int64)
    cap = np.zeros(len(names), dtype=np.int64)
    sel_set = set(sel)

    for tok in sel:
        scene = scene_of.get(tok)
        if scene is None:
            raise ValueError(f"selection token không thuộc POOL: {tok}")
        nsel[pos[scene]] += 1

    for frames in tf.values():
        if not (frames & sel_set):
            continue
        anchor = next(iter(frames))
        scene = scene_of.get(anchor)
        if scene is None:
            raise ValueError(f"struggle frame không thuộc POOL: {anchor}")
        cap[pos[scene]] += 1

    return nsel, cap


# ─── Bootstrap cụm scene, lô chọn cố định ───────────────────────────────────

def bootstrap_fixed_independent(
    sels: dict[str, list[str]],
    pool_frames: pd.DataFrame,
    tf: dict[str, set[str]],
    n_boot: int = 2000,
    seed: int = 20261017,
) -> pd.DataFrame:
    """SY_b cho mọi bên, đúng từng bước SPEC-P04 §3.6.

    `tf` là ánh xạ instance_token → tập sample_token struggle của MỘT giám khảo.
    Trả về DataFrame (n_boot, n_bên); cột theo đúng thứ tự `sels`.
    """
    if n_boot < 1:
        raise ValueError("n_boot phải dương")
    methods = list(sels)
    if not methods:
        raise ValueError("sels rỗng")
    scene_of, names, pos = _scene_lookup(pool_frames)
    arrays = {m: _scene_arrays(sels[m], tf, scene_of, names, pos) for m in methods}

    rng = np.random.default_rng(seed)
    out = np.empty((n_boot, len(methods)), dtype=np.float64)
    for b in range(n_boot):
        idx = rng.integers(0, len(names), size=len(names))
        for j, method in enumerate(methods):
            nsel, cap = arrays[method]
            out[b, j] = cap[idx].sum() / max(float(nsel[idx].sum()), 1.0)
    return pd.DataFrame(out, columns=methods)


# ─── SY điểm và hiệu chỉnh Holm ─────────────────────────────────────────────

def compute_sy(sel: list[str], tf: dict[str, set[str]]) -> float:
    """SY = |captured(sel, tf)| / |sel|; instance capture nếu có frame trong sel."""
    if not sel:
        return 0.0
    sel_set = set(sel)
    captured = sum(1 for frames in tf.values() if frames & sel_set)
    return captured / len(sel)


def holm_correction(p_values: list[float]) -> list[float]:
    """Hiệu chỉnh Holm, trả về đúng thứ tự đầu vào."""
    n = len(p_values)
    out = [0.0] * n
    running = 0.0
    for rank, i in enumerate(sorted(range(n), key=p_values.__getitem__)):
        running = max(running, min(1.0, (n - rank) * p_values[i]))
        out[i] = running
    return out


def _bootstrap_p(delta_boot: np.ndarray) -> float:
    return float(min(
        1.0,
        2.0 * min(float((delta_boot <= 0).mean()), float((delta_boot >= 0).mean())),
    ))


# ─── Đối chiếu primary + secondary + Holm ────────────────────────────────────

def contrasts(
    sels: dict[str, list[str]],
    pool_frames: pd.DataFrame,
    tf: dict[str, set[str]],
    judge: str,
    n_boot: int = 2000,
    seed: int = 20261017,
    rivals: list[str] | None = None,
) -> list[dict]:
    """Đối chiếu primary (OURS − Xbest lấy lại mỗi lượt), secondary và Holm.

    Họ secondary đúng prereg, theo từng giám khảo:
      OURS − X0, OURS − N1, OURS − N2, OURS − X1, OURS − X2, OURS − X3,
      OURS − M1, M2 − M1.
    """
    if rivals is None:
        rivals = [m for m in ("X1", "X2", "X3", "Xext") if m in sels]
    if not rivals:
        raise ValueError("không có bên thứ ba X1/X2/X3/Xext")

    boot = bootstrap_fixed_independent(sels, pool_frames, tf, n_boot=n_boot, seed=seed)
    values = {m: compute_sy(sels[m], tf) for m in sels}

    x0_cols = [m for m in sels if m.startswith("X0_s")]
    if len(x0_cols) != 100:
        raise ValueError(f"cần đúng 100 lô X0, nhận {len(x0_cols)}")
    values["X0"] = float(np.mean([values[m] for m in x0_cols]))
    boot["X0"] = boot[x0_cols].mean(axis=1)

    if "OURS" not in boot.columns:
        raise ValueError("thiếu bên OURS")
    missing = [m for m in rivals if m not in boot.columns]
    if missing:
        raise ValueError(f"thiếu bên thứ ba: {missing}")
    boot["Xbest"] = boot[rivals].max(axis=1)
    values["Xbest"] = max(values[m] for m in rivals)

    def make(a: str, b: str) -> dict:
        delta_boot = boot[a].to_numpy() - boot[b].to_numpy()
        lo, hi = np.percentile(delta_boot, [2.5, 97.5])
        return dict(
            a=a,
            b=b,
            judge=judge,
            delta=float(values[a] - values[b]),
            lo=float(lo),
            hi=float(hi),
            p=_bootstrap_p(delta_boot),
            p_holm=None,
        )

    main = make("OURS", "Xbest")

    pairs = [(a, b) for a, b in
             [("OURS", m) for m in ("X0", "N1", "N2", "X1", "X2", "X3", "M1")]
             + [("M2", "M1")]]
    absent = [m for a, b in pairs for m in (a, b) if m not in boot.columns]
    if absent:
        raise ValueError(f"thiếu bên bắt buộc: {sorted(set(absent))}")
    secondary = [make(a, b) for a, b in pairs]
    for row, adjusted in zip(secondary, holm_correction([r["p"] for r in secondary])):
        row["p_holm"] = float(adjusted)

    return [main, *secondary]


# ─── Luật thắng của prereg ───────────────────────────────────────────────────

def verdict(
    primary_contrasts: dict[str, dict],
    secondary_contrasts_per_judge: dict[str, list[dict]],
    label: str,
    valid_judges: list[str],
) -> dict:
    """`win` = confirmatory, ≥2 giám khảo hợp lệ, mọi giám khảo hợp lệ đạt:
    CI95 dưới của D_j > 0 VÀ OURS thắng X0/N1/N2 sau Holm (p_holm < 0.05).
    """
    if label != "confirmatory" or len(valid_judges) < 2:
        return {"win": False}
    for judge in valid_judges:
        primary = primary_contrasts.get(judge)
        if not primary or float(primary.get("lo", float("-inf"))) <= 0.0:
            return {"win": False}
        rows = [
            r for r in secondary_contrasts_per_judge.get(judge, [])
            if r.get("a") == "OURS" and r.get("b") in {"X0", "N1", "N2"}
        ]
        if not all(float(r.get("delta", -1.0)) > 0.0
                   and float(r.get("p_holm", 1.0)) < 0.05 for r in rows):
            return {"win": False}
    return {"win": True}


# ─── SHA256 ─────────────────────────────────────────────────────────────────

def sha256_file(path: str | Path) -> str:
    """SHA256 hex của một file."""
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


# ─── Tính lại và so với report_judge.json ───────────────────────────────────

def _tokens_for_frac(entry: dict, budget: int) -> list[str] | None:
    """Lô chọn tại frac 0.05, theo đúng cách `c4.bench.metrics._prefixes` đọc."""
    if "by_frac" in entry:
        tokens = entry["by_frac"].get("0.05")
        return None if tokens is None else list(tokens)
    tokens = entry.get("tokens")
    return None if tokens is None else list(tokens)[:budget]


def verify_against_report(
    report_path: str | Path,
    selections_path: str | Path,
    struggle_ja: pd.DataFrame,
    struggle_jb: pd.DataFrame,
    pool_frames: pd.DataFrame,
    n_boot: int = 2000,
    seed: int = 20261017,
    tol: float = 1e-9,
) -> dict:
    """Tính lại và so MỌI số với report_judge.json (dung sai `tol`).

    So khớp:
      - `methods.*.SY_JA` / `methods.*.SY_JB`
      - `contrasts[*].{delta, lo, hi, p_holm}`
      - `verdict.win`
    Trả về {"ok": bool, "details": {khoá: {expected, computed, ok}}, "mismatches": [...]}.
    """
    report = json.loads(Path(report_path).read_text(encoding="utf-8"))
    selections = json.loads(Path(selections_path).read_text(encoding="utf-8"))
    details: dict[str, dict] = {}
    mismatches: list[str] = []

    def same(key: str, expected, computed, numeric: bool = True) -> None:
        if numeric:
            try:
                ok = (
                    expected is not None
                    and computed is not None
                    and np.isfinite(float(expected))
                    and np.isfinite(float(computed))
                    and abs(float(computed) - float(expected)) <= tol
                )
            except (TypeError, ValueError):
                ok = False
        else:
            ok = expected is not None and bool(expected) == bool(computed)
        details[key] = {"expected": expected, "computed": computed, "ok": bool(ok)}
        if not ok:
            mismatches.append(key)

    def stop(reason: str) -> dict:
        mismatches.append(reason)
        return {"ok": False, "details": details, "mismatches": mismatches}

    budget = report.get("B")
    if not isinstance(budget, int) or budget <= 0:
        return stop("B")
    methods_sel = selections.get("methods", {})
    if "OURS" not in methods_sel:
        return stop("selections.methods.OURS")

    sels: dict[str, list[str]] = {}
    for name, entry in methods_sel.items():
        if not isinstance(entry, dict):
            return stop(f"selections.methods.{name}")
        if name == "X0":
            seeds = entry.get("seeds", {})
            if set(seeds) != {str(i) for i in range(100)}:
                return stop("selections.methods.X0.seeds")
            for key, tokens in seeds.items():
                sels[f"X0_s{key}"] = list(tokens)[:budget]
        else:
            tokens = _tokens_for_frac(entry, budget)
            if tokens is None:
                return stop(f"selections.methods.{name}.tokens")
            sels[name] = tokens
    if len([m for m in sels if m.startswith("X0_s")]) != 100:
        return stop("selections.methods.X0.seeds")

    try:
        tf_ja = tf_from_struggle(struggle_ja)
        tf_jb = tf_from_struggle(struggle_jb)
    except ValueError as exc:
        return stop(f"struggle: {exc}")

    by_judge: dict[str, list[dict]] = {}
    for judge, tf in (("JA", tf_ja), ("JB", tf_jb)):
        try:
            by_judge[judge] = contrasts(
                sels, pool_frames, tf, judge=judge, n_boot=n_boot, seed=seed
            )
        except ValueError as exc:
            mismatches.append(f"contrasts.{judge}.error")
            details[f"contrasts.{judge}.error"] = {
                "expected": "tính lại được", "computed": str(exc), "ok": False,
            }
            by_judge[judge] = []

    rep_methods = report.get("methods", {})
    for method, entry in rep_methods.items():
        if not isinstance(entry, dict):
            continue
        for key, expected in entry.items():
            if not key.startswith("SY_"):
                continue
            judge = key[3:]
            tf = tf_ja if judge == "JA" else tf_jb if judge == "JB" else None
            if tf is None or method not in sels:
                mismatches.append(f"methods.{method}.{key}")
                details[f"methods.{method}.{key}"] = {
                    "expected": expected, "computed": None, "ok": False,
                }
                continue
            same(f"methods.{method}.{key}", expected, compute_sy(sels[method], tf))

    # Báo cáo phải có đủ SY_JA/SY_JB cho mọi bên đã chọn (không được bỏ hàng).
    for method in sels:
        if method.startswith("X0_s"):
            continue
        entry = rep_methods.get(method)
        for judge in ("JA", "JB"):
            key = f"SY_{judge}"
            if isinstance(entry, dict) and key in entry:
                continue
            label = f"methods.{method}.{key}"
            if label not in mismatches:
                mismatches.append(label)
                details[label] = {"expected": "có trong report", "computed": None, "ok": False}

    computed = {
        (row["a"], row["b"], judge): row
        for judge, rows in by_judge.items() for row in rows
    }
    seen: set[tuple] = set()
    for row in report.get("contrasts", []):
        key = (row.get("a"), row.get("b"), row.get("judge"))
        label = f"contrasts[{key[0]}-{key[1]}-{key[2]}]"
        if key in seen:
            mismatches.append(f"{label}.duplicate")
            continue
        seen.add(key)
        mine = computed.get(key)
        if mine is None:
            mismatches.append(label)
            details[label] = {"expected": row, "computed": None, "ok": False}
            continue
        for field in ("delta", "lo", "hi"):
            same(f"{label}.{field}", row.get(field), mine.get(field))
        expected_holm = row.get("p_holm")
        computed_holm = mine.get("p_holm")
        if "p_holm" not in row:
            mismatches.append(f"{label}.p_holm")
            details[f"{label}.p_holm"] = {
                "expected": None, "computed": computed_holm, "ok": False,
            }
        elif expected_holm is None and computed_holm is None:
            details[f"{label}.p_holm"] = {
                "expected": None, "computed": None, "ok": True,
            }
        elif expected_holm is None or computed_holm is None:
            mismatches.append(f"{label}.p_holm")
            details[f"{label}.p_holm"] = {
                "expected": expected_holm, "computed": computed_holm, "ok": False,
            }
        else:
            same(f"{label}.p_holm", expected_holm, computed_holm)

    for key in computed:
        if key not in seen:
            label = f"contrasts[{key[0]}-{key[1]}-{key[2]}].missing_in_report"
            mismatches.append(label)
            details[label] = {"expected": None, "computed": computed[key], "ok": False}

    primary = {
        judge: next((r for r in rows if r["b"] == "Xbest"), None)
        for judge, rows in by_judge.items()
    }
    secondary = {
        judge: [r for r in rows if r["b"] != "Xbest"]
        for judge, rows in by_judge.items()
    }
    label = report.get("label", "exploratory")
    valid = [
        judge for judge, info in report.get("judges", {}).items()
        if isinstance(info, dict) and info.get("validity", {}).get("ok") is True
    ]
    expected_win = report.get("verdict", {}).get("win")
    same("verdict.win", expected_win, verdict(primary, secondary, label, valid)["win"],
         numeric=False)

    return {"ok": not mismatches, "details": details, "mismatches": mismatches}
