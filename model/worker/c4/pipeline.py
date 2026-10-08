# c4/pipeline.py · S5 score -> S6 select -> S7 evaluate -> analysis, gọi mỗi lần tinh chỉnh
import hashlib
import json
import os
import re
import time
import uuid
from dataclasses import asdict
from pathlib import Path

import numpy as np
import pandas as pd

from c4.analysis.overview import analyze, duplicate_groups
from c4.config import load_config, load_queries
from c4.contracts import read_table, write_table
from c4.eval.metrics import evaluate
from c4.mining.query import TextEncoder, apply_queries
from c4.mining.score import apply_quality, frame_embeddings, frame_scores
from c4.mining.select import run_all
from c4.params import SelectParams, resolve

PREVIEW_N = 12


def _resolve_queries(texts: list[str] | None) -> tuple[list[dict], bool]:
    """Trả (tập query, có phải tập mặc định đã tính sẵn ở S3 không)."""
    default = load_queries()
    if texts is None or [q["text"] for q in default] == list(texts):
        return default, True
    by_text = {q["text"]: q["id"] for q in default}
    out = []
    for t in texts:
        qid = by_text.get(t) or re.sub(r"[^a-z0-9]+", "_", t.lower()).strip("_")[:32] or "query"
        out.append({"id": qid, "text": t})
    return out, False


def _atomic_json(obj, path: Path) -> None:
    tmp = path.with_name(f"{path.name}.{uuid.uuid4().hex[:8]}.tmp")  # tên riêng mỗi lần ghi
    tmp.write_text(json.dumps(obj, ensure_ascii=False, indent=1), encoding="utf-8")
    for attempt in range(20):
        try:
            os.replace(tmp, path)
            return
        except PermissionError:  # Windows: có người đang mở file đích để đọc
            if attempt == 19:
                raise
            time.sleep(0.05)


def _fingerprint(job_dir: Path) -> str:
    """Dấu vân tay của cache đặc trưng: đổi pool hoặc trích lại thì mọi kết quả cũ hết hiệu lực."""
    parts = []
    for name in ("features_cache.parquet", "dino_cls.npy"):
        st = (job_dir / "cache" / name).stat()  # thiếu file -> FileNotFoundError (mã thoát 4)
        parts.append(f"{name}:{st.st_size}:{st.st_mtime_ns}")
    return "|".join(parts)


def _dup_groups_cached(job_dir: Path, Zf: np.ndarray, cameras, theta: float,
                       fingerprint: str) -> np.ndarray:
    """Nhóm trùng lặp chỉ phụ thuộc embedding frame (theo bộ camera), không phụ thuộc trọng số:
    tính một lần cho mỗi job rồi dùng lại."""
    key = hashlib.sha1(f"{','.join(cameras)}|{theta}|{fingerprint}".encode()).hexdigest()[:10]
    path = job_dir / "out" / f"dup_groups_{key}.npy"
    if path.exists():
        g = np.load(path)
        if len(g) == len(Zf):
            return g
    g = duplicate_groups(Zf, theta)
    path.parent.mkdir(parents=True, exist_ok=True)
    np.save(path, g)
    return g


def run_selection(job_dir: Path, params: SelectParams, cfg=None,
                  encoder: TextEncoder | None = None) -> dict:
    job_dir = Path(job_dir)
    cfg = cfg or load_config()
    r = resolve(params, cfg)
    queries, is_default = _resolve_queries(params.queries)
    fp = _fingerprint(job_dir)
    sig = "|".join([json.dumps(asdict(r), sort_keys=True), "\n".join(q["text"] for q in queries),
                    json.dumps(cfg.eval, sort_keys=True), json.dumps(cfg.analysis, sort_keys=True),
                    fp])
    sel_id = hashlib.sha1(sig.encode("utf-8")).hexdigest()[:12]
    out_dir = job_dir / "out" / "selections" / sel_id
    if (out_dir / "result.json").exists():
        return json.loads((out_dir / "result.json").read_text(encoding="utf-8"))

    feat = read_table(job_dir / "cache" / "features_cache.parquet", "features_cache")
    Z_img = np.load(job_dir / "cache" / "dino_cls.npy", mmap_mode="r")
    if not is_default:
        if encoder is None:
            raise ValueError("Cần text encoder để dùng query mới")
        C_img = np.load(job_dir / "cache" / "clip_img.npy", mmap_mode="r")
        feat = apply_queries(feat, C_img, queries, encoder)
    feat = apply_quality(feat, r.min_luma, r.min_blur_var)

    fs = frame_scores(feat, r.alpha, r.beta, r.gamma, r.cameras)
    Zf, tokens = frame_embeddings(Z_img, feat, r.cameras)
    sels, warnings = run_all(fs, Zf, r, cfg.eval["random_seeds"])
    B = int(sels["hybrid"]["budget_B"].iloc[0]) if len(sels["hybrid"]) else int(
        np.ceil(r.budget * len(fs)))
    row_of = {t: i for i, t in enumerate(tokens)}

    def z_by_token(ts):
        return Zf[[row_of[t] for t in ts]]

    gt_path = job_dir / "gt" / "gt_rare.parquet"
    gt = read_table(gt_path, "gt_rare") if gt_path.exists() else None
    metrics = evaluate(sels, B, len(fs), gt, z_by_token, cfg.eval["dup_theta"])
    groups = _dup_groups_cached(job_dir, Zf, r.cameras, cfg.analysis["dup_theta"], fp)
    analysis = analyze(fs, feat, Zf, sels["hybrid"], B, gt, r, cfg, groups=groups)

    head = sels["hybrid"].sort_values("rank").head(PREVIEW_N)
    sub = feat[feat["sample_token"].isin(set(head["sample_token"]))]
    cams_of = {t: list(g) for t, g in sub.groupby("sample_token")["cam"]}
    info = fs.set_index("sample_token")
    preview = []
    for row in head.itertuples():
        f = info.loc[row.sample_token]
        preview.append(dict(
            rank=int(row.rank), sampleToken=row.sample_token, sceneToken=row.scene_token,
            frameIdx=int(f["frame_idx"]), bestCam=row.best_cam, S=round(float(row.S), 6),
            rNov=round(float(f["r_nov"]), 6), rUnc=round(float(f["r_unc"]), 6),
            rQry=round(float(f["r_qry"]), 6), qryBest=str(f["qry_best"]), reason=row.reason,
            tags=analysis["tags"].get(row.sample_token, []),
            camsAvailable=cams_of[row.sample_token]))

    result = dict(selectionId=sel_id, params={**asdict(r), "cameras": list(r.cameras),
                                              "queries": queries},
                  poolSize=len(fs), budgetB=B, warnings=warnings, metrics=metrics,
                  preview=preview, analysis=analysis)
    out_dir.mkdir(parents=True, exist_ok=True)
    write_table(fs, str(out_dir / "frame_scores.csv"), "frame_scores", selection_id=sel_id)
    write_table(pd.concat(sels.values(), ignore_index=True), str(out_dir / "selected.csv"),
                "selected", selection_id=sel_id)
    _atomic_json(result, out_dir / "result.json")
    return result
