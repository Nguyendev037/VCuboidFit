# c4/analysis/overview.py · bảng phân tích tổng quan (spec mục 3)
import numpy as np
import pandas as pd

from c4.eval.metrics import FINE_GROUPS, GROUP_COLS


def duplicate_groups(Zf: np.ndarray, theta: float = 0.95, chunk: int = 2048) -> np.ndarray:
    """Mã nhóm cho mỗi frame: union-find trên các cặp có cosine > theta."""
    Z = np.ascontiguousarray(Zf, dtype=np.float32)
    parent = np.arange(len(Z))

    def find(i):
        while parent[i] != i:
            parent[i] = parent[parent[i]]
            i = parent[i]
        return i

    for s in range(0, len(Z), chunk):
        sim = Z[s:s + chunk] @ Z.T
        ii, jj = np.nonzero(sim > theta)
        ii = ii + s
        keep = ii < jj
        for i, j in zip(ii[keep], jj[keep]):
            ri, rj = find(i), find(j)
            if ri != rj:
                parent[max(ri, rj)] = min(ri, rj)
    return np.array([find(i) for i in range(len(Z))])


def _cp(n, total):
    return {"count": int(n), "pct": round(float(n) / max(total, 1), 6)}


def _reason_kind(text: str) -> str:
    for k in ("novelty", "uncertainty", "query"):
        if text.startswith(k):
            return k
    return "other"


def analyze(fs: pd.DataFrame, feat: pd.DataFrame, Zf: np.ndarray, selected: pd.DataFrame,
            budget_B: int, gt: pd.DataFrame | None, r, cfg,
            groups: np.ndarray | None = None) -> dict:
    """groups: mã nhóm trùng lặp theo dòng Zf, truyền vào khi đã cache sẵn."""
    N = len(fs)
    fs = fs.reset_index(drop=True)
    if groups is None:
        groups = duplicate_groups(Zf, cfg.analysis["dup_theta"])
    grp = groups[fs["frame_emb_row"].to_numpy()]
    n_groups_dup = int(sum(c > 1 for c in np.unique(grp, return_counts=True)[1]))

    # các chỉ số "an toàn / dễ / giá trị cao" chỉ có nghĩa trên frame được chấm điểm
    elig = fs["q_ok"].to_numpy(bool)
    too_safe = elig & (fs["r_nov"] <= 0.3) & (fs["r_qry"] <= 0.3)
    easy = elig & (fs["r_unc"] <= 0.2) & (fs["det_n_conf_best"] >= 1)
    S = fs["S_hybrid"].to_numpy(np.float64)
    n_high = int((S[elig] >= np.percentile(S[elig], 90)).sum()) if elig.any() else 0

    # không gán nhãn được = không ảnh nào của frame đạt chất lượng, bất kể bộ lọc camera;
    # frame có ảnh tốt nhưng bị loại chỉ vì bộ lọc camera đếm riêng
    img_ok = ((feat["q_bright"] >= r.min_luma) & (feat["q_blur"] >= r.min_blur_var)
              & (feat["det_n"] >= 1))
    frame_has_ok = img_ok.groupby(feat["sample_token"]).any()
    has_ok = fs["sample_token"].map(frame_has_ok).fillna(False).to_numpy(bool)
    bad = fs[~elig & ~has_ok]
    n_cam_excluded = int((~elig & has_ok).sum())
    best_img = feat.set_index("emb_row").loc[bad["emb_row_best"].to_numpy()]
    dark = best_img["q_bright"] < r.min_luma
    blurry = ~dark & (best_img["q_blur"] < r.min_blur_var)
    no_obj = ~dark & ~blurry & (best_img["det_n"] == 0)

    rare_gt = None
    gt_tags = {}
    if gt is not None:
        g = gt.set_index("sample_token")
        rare_gt = {"total": _cp(int(g["is_rare"].sum()), N)}
        rare_gt.update({k: _cp(g[cols].any(axis=1).sum(), N) for k, cols in GROUP_COLS.items()})
        hits = g[FINE_GROUPS]
        gt_tags = {t: "Rare GT: " + "|".join(c for c in FINE_GROUPS if row[c])
                   for t, row in hits.iterrows() if row.any()}

    ranked = selected.sort_values("rank")  # tới B_max: slider ngân sách cần tag cho mọi dòng
    top = ranked[ranked["rank"] <= budget_B]
    info = fs.set_index("sample_token")
    grp_of = dict(zip(fs["sample_token"], grp))
    first_rank_in_group: dict = {}
    tags, dup_in_sel = {}, 0
    for row in ranked.itertuples():
        f = info.loc[row.sample_token]
        t = []
        if f["r_nov"] >= 0.8:
            t.append("Hiếm")
        if f["r_unc"] >= 0.8:
            t.append("Khó")
        if f["r_qry"] >= 0.8:
            t.append(f"Kịch bản: {f['qry_best']}")
        gid = grp_of[row.sample_token]
        if gid in first_rank_in_group:
            t.append(f"Trùng với #{first_rank_in_group[gid]}")
            dup_in_sel += int(row.rank <= budget_B)
        else:
            first_rank_in_group[gid] = int(row.rank)
        if row.sample_token in gt_tags:
            t.append(gt_tags[row.sample_token])
        tags[row.sample_token] = t

    reasons = {"novelty": 0, "uncertainty": 0, "query": 0, "other": 0}
    for text in top["reason"]:
        reasons[_reason_kind(str(text))] += 1
    counts, bins = np.histogram(S, bins=np.linspace(0.0, 1.0, 21))
    at_b = top.loc[top["rank"] == budget_B, "S"]
    threshold = float(at_b.iloc[0]) if len(at_b) else float(top["S"].min() if len(top) else 0.0)

    return {
        "pool": {
            "scenes": int(fs["scene_token"].nunique()), "frames": N, "images": len(feat),
            "imagesByCam": {k: int(v) for k, v in feat["cam"].value_counts().sort_index().items()},
            "duplicates": {"frames": _cp(N - len(np.unique(grp)), N), "groups": n_groups_dup},
            "tooSafe": _cp(too_safe.sum(), N), "easy": _cp(easy.sum(), N),
            "unlabelable": {"total": _cp(len(bad), N), "dark": int(dark.sum()),
                            "blurry": int(blurry.sum()), "noObjects": int(no_obj.sum())},
            "excludedByCamera": _cp(n_cam_excluded, N),
            "highValue": _cp(n_high, N),
            "rareGt": rare_gt,
        },
        "selected": {"scenesCovered": int(info.loc[top["sample_token"], "scene_token"].nunique())
                     if len(top) else 0,
                     "reasons": reasons, "duplicatesInSelection": dup_in_sel},
        "histogram": {"bins": [round(float(b), 6) for b in bins],
                      "counts": [int(c) for c in counts], "budgetThreshold": round(threshold, 6)},
        "tags": tags,
    }
