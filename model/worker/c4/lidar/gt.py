"""M2 · ground truth "rare" theo cell (PDF §5.1). MODULE DUY NHẤT của pipeline LiDAR được đọc
annotation và scene.description. Kết quả chỉ `c4.lidar.evaluation` được đọc
(test_no_leakage_lidar)."""
import math

import numpy as np
import pandas as pd

from c4.contracts import validate
from c4.data.nusc import NuscTables
from c4.lidar.index import lidar_keyframes


def _bin(x: float, edges) -> int:
    return int(np.clip(np.searchsorted(np.asarray(edges, float), x, side="right") - 1,
                       0, len(edges) - 2))


def frame_boxes(t: NuscTables, index: pd.DataFrame, gcfg: dict) -> dict[str, list[dict]]:
    """sample_token → [{cls, dist, pts, vis}] chỉ cho box có lớp trong class_map."""
    cmap = gcfg["class_map"]
    lid = lidar_keyframes(t)
    ego = {}
    for tok in index["sample_token"]:
        ego[tok] = t.ego_pose[lid[tok]["ego_pose_token"]]["translation"]
    out: dict[str, list[dict]] = {tok: [] for tok in index["sample_token"]}
    for a in t.sample_annotation.values():
        tok = a["sample_token"]
        if tok not in out:
            continue
        cat = t.category[t.instance[a["instance_token"]]["category_token"]]["name"]
        cls = cmap.get(cat)
        if cls is None:
            continue
        e = ego[tok]
        out[tok].append(dict(cls=cls, dist=math.hypot(a["translation"][0] - e[0],
                                                      a["translation"][1] - e[1]),
                             pts=int(a["num_lidar_pts"]), vis=str(a.get("visibility_token", ""))))
    return out


def cell_of(b: dict, gcfg: dict) -> str:
    return (f'{b["cls"]}|d{_bin(b["dist"], gcfg["distance_bins_m"])}'
            f'|p{_bin(b["pts"], gcfg["points_bins"])}')


def build_gt(t: NuscTables, index: pd.DataFrame, gcfg: dict) -> tuple[pd.DataFrame, pd.DataFrame]:
    """(gt_rare_lidar, cell_freq). Tần suất cell tính RIÊNG cho từng split (tập đang chấm)."""
    boxes = frame_boxes(t, index, gcfg)
    desc = {tok: t.scene[sc]["description"].lower()
            for tok, sc in zip(index["sample_token"], index["scene_token"])}
    few, med, c = set(gcfg["few"]), set(gcfg["medium"]), gcfg["C"]
    cells = {tok: sorted({cell_of(b, gcfg) for b in bs}) for tok, bs in boxes.items()}
    freq_rows, rows = [], []
    for split, part in index.groupby("split", sort=True):
        toks = part["sample_token"].tolist()
        counts: dict[str, int] = {}
        for tok in toks:
            for cell in cells[tok]:
                counts[cell] = counts.get(cell, 0) + 1
        freq = {cell: n / len(toks) for cell, n in counts.items()}
        freq_rows += [dict(split=split, cell=k, n_frames=n, freq=round(freq[k], 6))
                      for k, n in sorted(counts.items())]
        for tok in toks:
            bs = boxes[tok]
            rare_cells = [cell for cell in cells[tok] if freq[cell] < gcfg["tau"]]
            rows.append(dict(
                sample_token=tok, is_rare=bool(rare_cells),
                A_env=any(k in desc[tok] for k in gcfg["A_keywords"]),
                B_few=any(b["cls"] in few for b in bs),
                Bp_medium=any(b["cls"] in med for b in bs),
                C_sensor=any((b["pts"] <= c["max_pts"] and b["dist"] > c["min_dist_m"])
                             or b["vis"] == str(c["low_vis"]) for b in bs),
                n_boxes=len(bs), rare_cells="|".join(rare_cells)))
    gt = pd.DataFrame(rows).set_index("sample_token").loc[index["sample_token"]].reset_index()
    return validate(gt, "gt_rare_lidar"), pd.DataFrame(freq_rows)


def g1_table(t: NuscTables, index: pd.DataFrame, gcfg: dict, taus=(0.005, 0.01, 0.02, 0.05),
             variants: dict | None = None) -> pd.DataFrame:
    """Bảng đếm cho cổng G1 (PDF §8.4 Q3): mỗi split × τ → số frame rare; mỗi split × định nghĩa
    nhóm C → tỉ lệ frame thuộc C. Chỉ đọc nhãn — đúng chỗ trong gt.py, kết quả để NGƯỜI chốt."""
    boxes = frame_boxes(t, index, gcfg)
    cells = {tok: {cell_of(b, gcfg) for b in bs} for tok, bs in boxes.items()}
    variants = variants or {
        "pts<=5&dist>40|vis1": lambda b, c: (b["pts"] <= 5 and b["dist"] > 40) or b["vis"] == "1",
        "pts<=5&dist>40": lambda b, c: b["pts"] <= 5 and b["dist"] > 40,
        "pts<=2&dist>30": lambda b, c: b["pts"] <= 2 and b["dist"] > 30,
        "vis1": lambda b, c: b["vis"] == "1"}
    far = lambda b: b["pts"] <= 5 and b["dist"] > 40  # noqa: E731 — box khó nhìn bằng LiDAR
    count_rules = {f"far_low_pts>={n}": n for n in (3, 5, 10)}  # nhóm C theo SỐ LƯỢNG box khó
    rows = []
    for split, part in index.groupby("split", sort=True):
        toks = part["sample_token"].tolist()
        n = len(toks)
        cnt: dict[str, int] = {}
        for tok in toks:
            for cell in cells[tok]:
                cnt[cell] = cnt.get(cell, 0) + 1
        for tau in taus:
            rare = sum(any(cnt[c] / n < tau for c in cells[tok]) for tok in toks)
            rows.append(dict(split=split, kind="tau", value=tau, frames=n, hit=rare,
                             pct=round(rare / n, 4), B=max(1, int(np.ceil(0.05 * n)))))
        for name, fn in variants.items():
            hit = sum(any(fn(b, gcfg["C"]) for b in boxes[tok]) for tok in toks)
            rows.append(dict(split=split, kind="C", value=name, frames=n, hit=hit,
                             pct=round(hit / n, 4), B=max(1, int(np.ceil(0.05 * n)))))
        for name, k in count_rules.items():
            hit = sum(sum(far(b) for b in boxes[tok]) >= k for tok in toks)
            rows.append(dict(split=split, kind="C", value=name, frames=n, hit=hit,
                             pct=round(hit / n, 4), B=max(1, int(np.ceil(0.05 * n)))))
    return pd.DataFrame(rows)
