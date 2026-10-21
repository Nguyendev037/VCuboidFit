"""Phân tích lô rare_v24; nhãn chỉ dùng ở bước chấm in-sample."""
import json
import logging
import os
from collections import Counter
from pathlib import Path

import numpy as np
import pandas as pd

from c4.data.nusc import NuscTables
from c4.rare.config import load_rare_def
from c4.rare.eval import (
    captured,
    metrics,
    oracle_instance,
    random_selector,
    target_frames,
    topk_selector,
)
from c4.rare.gt_rhcio import fit_reference, frame_context, label_gt, load_boxes

logger = logging.getLogger(__name__)
TAGS = ("R1", "R2", "R3", "H", "C", "I")
CLASSES = ("pedestrian", "bicycle", "motorcycle", "vru_unknown", "other")
AXES = ("r1_class", "r2_combo", "r3_behavior", "i_conflict", "h_hard")


def _pool(index: pd.DataFrame, frames: pd.DataFrame) -> list[str]:
    valid = frames.loc[frames["gate"] == "valid", "sample_token"]
    return index.loc[index["sample_token"].isin(valid), "sample_token"].tolist()


def label_free(index: pd.DataFrame, frames: pd.DataFrame, objects: pd.DataFrame,
               selected: list[str]) -> dict:
    """Tổng hợp dự đoán thuần trong bộ nhớ, không đọc nhãn hay file."""
    pool = _pool(index, frames)
    f = frames.set_index("sample_token")
    tags = {t: set(str(v).split("|")) if pd.notna(v) else set()
            for t, v in f["pred_tags"].items()}
    p_obj = objects[objects["sample_token"].isin(pool)]
    s_obj = objects[objects["sample_token"].isin(selected)]

    def summary(tokens, obj):
        return dict(frames=len(tokens), scenes=int(index.loc[
            index["sample_token"].isin(tokens), "scene_token"].nunique()),
            objects=len(obj), vru=int(obj["cls_pred"].isin(CLASSES[:4]).sum()),
            taggedRare=sum(bool(tags[t] & set(TAGS[:3])) for t in tokens))

    rates = []
    for tag in TAGS:
        n = sum(tag in tags[t] for t in selected)
        sp = n / max(len(selected), 1)
        pp = sum(tag in tags[t] for t in pool) / max(len(pool), 1)
        rates.append(dict(tag=tag, selected=n, selectedPct=round(sp, 4),
                          poolPct=round(pp, 4), lift=round(sp / pp, 4) if pp else None))
    reasons = Counter()
    obj_by_id = objects.drop_duplicates(["sample_token", "object_id"]).set_index(
        ["sample_token", "object_id"])
    for t in selected:
        raw = f.loc[t, "evidence"]
        ev = json.loads(raw) if isinstance(raw, str) and raw else {}
        key = (t, ev.get("top_object"))
        words = str(obj_by_id.loc[key, "reasons"]).split() if key in obj_by_id.index else []
        code = words[0] if words else "none"
        reasons[code if code in ("slice", "vru", "shape", "unc", "sem", "concept") else "none"] += 1

    def distances(obj):
        values = obj.loc[obj["cls_pred"].isin(CLASSES[:4]), "dist_m"].dropna()
        return np.histogram(values, bins=[0, 10, 20, 30, 40, 50, np.inf])[0].tolist()

    eligible_index = index[index["sample_token"].isin(pool)]
    scenes = [dict(scene=str(scene), order=i, pool=len(group),
                   selected=int(group["sample_token"].isin(selected).sum()))
              for i, (scene, group) in enumerate(
                  eligible_index.groupby("scene_token", sort=False), 1)]
    counts, edges = np.histogram(f.loc[pool, "s_frame"], bins=np.linspace(0, 1, 21))
    return dict(version=1, pool={**summary(pool, p_obj), "frames": len(index),
                                "eligible": len(pool)}, selected=summary(selected, s_obj),
                tagRates=rates,
                reasons=[dict(code=k, frames=v) for k, v in sorted(
                    reasons.items(), key=lambda item: (-item[1], item[0]))],
                classMix=[dict(cls=c, selected=int((s_obj["cls_pred"] == c).sum()),
                               pool=int((p_obj["cls_pred"] == c).sum())) for c in CLASSES],
                distance=dict(edges=[0, 10, 20, 30, 40, 50],
                              selected=distances(s_obj), pool=distances(p_obj)),
                scenes=scenes, scoreHistogram=dict(edges=edges.tolist(), counts=counts.tolist(),
                    threshold=float(f.loc[selected, "s_frame"].min()) if selected else 0))


def evaluate_in_sample(data_root: Path, index: pd.DataFrame, frames: pd.DataFrame,
                       selected: list[str]) -> tuple[dict | None, str]:
    """Chấm theo nhãn trên chính pool, dùng các hàm đánh giá sẵn có."""
    tables = NuscTables.load(data_root)
    if not tables.has_annotations:
        return None, "no_annotations"
    pool = _pool(index, frames)
    if len(pool) > 5000:
        return None, "too_large"
    cfg, _ = load_rare_def()
    ref = fit_reference(load_boxes(tables, pool), frame_context(tables, pool), cfg)
    gt_frame, gt_inst = label_gt(tables, pool, ref, cfg)
    tf = target_frames(gt_inst, "r2_combo", capture="any")
    if not tf:
        return None, "no_targets"
    b = len(selected)
    f = frames.set_index("sample_token")
    random = [random_selector(seed)(pool, b) for seed in range(100)]

    def row(key, tokens):
        m = metrics(tokens, gt_frame, tf)
        return dict(key=key, iy=round(m["iy"], 4), iyStd=None,
                    nInstances=m["n_instances"], irecall=round(m["irecall"], 4))

    rows = [row("ours", selected), row("score_only", topk_selector(f["s_frame"])(pool, b)),
            row("crowd", topk_selector(f["crowd"] + 1e-6 * f["s_frame"])(pool, b))]
    rand_metrics = [metrics(tokens, gt_frame, tf) for tokens in random]
    rows.append(dict(key="random", iy=round(float(np.mean([m["iy"] for m in rand_metrics])), 4),
        iyStd=round(float(np.std([m["iy"] for m in rand_metrics], ddof=0)), 4),
        nInstances=round(float(np.mean([m["n_instances"] for m in rand_metrics])), 4),
        irecall=round(float(np.mean([m["irecall"] for m in rand_metrics])), 4)))
    rows.append(row("oracle", oracle_instance(pool, b, tf)))
    by_axis = []
    for axis in AXES:
        tfa = target_frames(gt_inst, axis)
        by_axis.append(dict(axis=axis, targets=len(tfa), ours=len(captured(selected, tfa)),
            randomMean=round(float(np.mean([len(captured(tokens, tfa)) for tokens in random])), 4)))
    return dict(axis="r2_combo", inSample=True, B=b, nTargets=len(tf),
                rows=rows, byAxis=by_axis), "ok"


def build(job: Path, data_root: Path, sid: str, index: pd.DataFrame, frames: pd.DataFrame,
          objects: pd.DataFrame, selected: list[str]) -> dict | None:
    """Đọc cache theo sid, cô lập lỗi và ghi nguyên tử."""
    path = job / "engines" / "rare_v24" / sid / "rare_analysis.json"
    try:
        if path.is_file():
            return json.loads(path.read_text(encoding="utf-8"))
        analysis = label_free(index, frames, objects, selected)
    except Exception:
        logger.exception("Không tính được phân tích không nhãn")
        return None
    try:
        evaluation, reason = evaluate_in_sample(data_root, index, frames, selected)
    except Exception:
        logger.exception("Không chấm được lô theo nhãn")
        evaluation, reason = None, "error"
    analysis.update(evaluation=evaluation, evaluationReason=reason)
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp = path.with_suffix(path.suffix + ".tmp")
        tmp.write_text(json.dumps(analysis, ensure_ascii=False, allow_nan=False), encoding="utf-8")
        os.replace(tmp, path)
    except Exception:
        logger.exception("Không lưu được cache phân tích")
    return analysis
