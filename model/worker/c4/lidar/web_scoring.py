"""Chấm tập chọn của web bằng nhãn (vùng chấm điểm, cùng nhóm `gt`/`evaluation`). Chỉ chạy SAU khi
`web_selection.select_for_web` đã chọn xong; không đưa gì ngược lại vào bước chọn."""
from pathlib import Path

from c4.contracts import read_table
from c4.lidar import evaluation as ev
from c4.lidar.web_selection import WebSelection


def _web_metrics(m: dict) -> dict:
    keys = ["recall", "nRecall", "uplift", "precision", "sceneRecall", "coverage",
            "coverageGain", "redundancy", "nBoxes"]
    return {**{k: float(m.get(k, 0.0)) for k in keys}, "byGroup": m["byGroup"]}


def _count_pct(n, total):
    return {"count": int(n), "pct": round(float(n) / max(total, 1), 6)}


def attach_truth(sel: WebSelection, job: Path) -> dict:
    """Thêm metrics, đếm rare GT và tag "Rare GT …" vào result nếu job có nhãn; không thì giữ nguyên."""
    result = sel.result
    gt_path = Path(job) / "gt" / "gt_rare_lidar.parquet"
    if not gt_path.is_file():
        return result
    pool_index = sel.index[sel.in_pool].reset_index(drop=True)
    truth = ev.Truth(read_table(str(gt_path), "gt_rare_lidar"), pool_index)
    res = ev.evaluate_runs(sel.runs, truth, sel.B, ev.redundancy_window_s())
    result["metrics"] = dict(
        hybrid=_web_metrics(res["runs"]["hybrid"]),
        random=({k: _web_metrics(v) for k, v in res["random"].items()} if res["random"] else None),
        ablation={k: _web_metrics(v) for k, v in res["runs"].items() if k != "hybrid"},
        ci95=None)
    n = len(pool_index)
    rare_gt = {"total": _count_pct(len(truth.rare), n)}
    rare_gt.update({g: _count_pct(len(v), n) for g, v in truth.groups.items()})
    result["analysis"]["pool"]["rareGt"] = rare_gt
    # tag máy đọc được, khớp chip lọc "Rare GT A/B/C" của web; "rare (cell)" = đúng định nghĩa rare
    # của PDF §5.1, các tag nhóm chỉ nói frame thuộc nhóm nào
    tags = result["analysis"]["tags"]
    for tok in tags:
        hit = [f"Rare GT {g}" for g, v in truth.groups.items() if tok in v]
        if tok in truth.rare:
            hit.insert(0, "rare (cell)")
        tags[tok] = tags[tok] + hit
    for row in result["preview"]:
        row["tags"] = tags.get(row["sampleToken"], [])
    return result
