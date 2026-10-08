"""S2: YOLO11m detections (pixel gốc 1600×900) + uncertainty theo từng ảnh.

Chạy theo chunk 256 ảnh; mỗi chunk ghi cache/det_shards/chunk_XXXXX.parquet nguyên tử để resume.
predictor(img_paths, batch) -> list[ndarray (n, 6) = cls, conf, x1, y1, x2, y2] theo thứ tự đầu vào.
"""
import os
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import torch

from c4.config import load_config
from c4.extract.base import Progress
from c4.extract.dino import (
    load_frames,
    missing_weights,
    prepare_shard_dir,
    signature,
    weights_dir,
    write_parquet_atomic,
)
from c4.extract.fake import fake_detect, fake_models_enabled
from c4.mining.uncertainty import uncertainty

CONF_MIN = 0.05
CHUNK = 256
DET_DTYPES = dict(cls="int16", conf="float32", x1="float32", y1="float32", x2="float32",
                  y2="float32")


def _norm(p) -> str:
    return os.path.normcase(os.path.normpath(str(p)))


def align_results(paths, results) -> list[np.ndarray]:
    """Ghép kết quả Ultralytics về đúng thứ tự `paths` theo `result.path`.

    Ảnh không đọc được bị Ultralytics bỏ qua (kết quả ngắn hơn đầu vào) → ghép theo vị trí sẽ lệch
    mọi ảnh sau đó; ghép theo đường dẫn thì ảnh hỏng chỉ có 0 detection.
    """
    by_path = {_norm(r.path): r for r in results}
    out = []
    for p in paths:
        r = by_path.get(_norm(p))
        if r is None or r.boxes.cls.shape[0] == 0:
            out.append(np.zeros((0, 6), np.float32))
            continue
        b = r.boxes
        out.append(np.column_stack([b.cls.cpu().numpy(), b.conf.cpu().numpy(),
                                    b.xyxy.cpu().numpy()]).astype(np.float32))
    return out


def _fake_predictor(paths, batch):
    return [np.asarray(d, np.float32).reshape(-1, 6) for d in fake_detect(paths)]


def _real_predictor(root: Path, name: str, imgsz: int, device: str):
    pt = weights_dir() / name
    if not pt.is_file():
        raise missing_weights(f"YOLO ({name})")
    from ultralytics import YOLO  # nạp muộn: test CPU không cần ultralytics

    model = YOLO(str(pt))
    dev = "cpu" if device == "cpu" else "cuda:0"

    def predict(paths, batch):
        full = [str(root / p) for p in paths]
        res = model.predict(full, imgsz=imgsz, conf=CONF_MIN, half=dev != "cpu", batch=batch,
                            device=dev, verbose=False)
        return align_results(full, res)

    return predict


def _chunk_frame(rows_per_image: list[np.ndarray], lo: int) -> pd.DataFrame:
    rows = [np.full(len(a), lo + i, np.int32) for i, a in enumerate(rows_per_image)]
    arr = np.concatenate(rows_per_image) if rows_per_image else np.zeros((0, 6), np.float32)
    df = pd.DataFrame(arr, columns=list(DET_DTYPES)).astype(DET_DTYPES)
    df.insert(0, "row", np.concatenate(rows) if rows else np.zeros(0, np.int32))
    return df


def extract_det(job_dir, data_root, *, profile="local-4060", resume=False, limit=None,
                device="cuda", chunk=CHUNK, predictor=None) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Ghi cache/detections.parquet + cache/feat_det.parquet; trả (detections, feat_det)."""
    job = Path(job_dir)
    cfg = load_config(profile)
    frames = load_frames(job, limit)
    fake = fake_models_enabled()
    name, imgsz = cfg.det["model"], cfg.det["imgsz"]
    if predictor is None:
        predictor = _fake_predictor if fake else _real_predictor(Path(data_root), name, imgsz,
                                                                 device)
    shard_dir = job / "cache" / "det_shards"
    prepare_shard_dir(shard_dir, signature("det", fake, name, imgsz, chunk,
                                           *frames["img_path"]), resume)
    n = len(frames)
    paths = frames["img_path"].tolist()
    progress = Progress(job, "det", n)
    batch = cfg.det["batch"]
    for k in range(-(-n // chunk)):
        lo, hi = k * chunk, min(n, (k + 1) * chunk)
        out = shard_dir / f"chunk_{k:05d}.parquet"
        if not out.is_file():
            while True:
                try:
                    with torch.inference_mode():
                        per_image = predictor(paths[lo:hi], batch)
                    break
                except torch.cuda.OutOfMemoryError:
                    if batch == 1:
                        sys.exit(3)
                    batch = max(1, batch // 2)
                    if torch.cuda.is_available():
                        torch.cuda.empty_cache()
            write_parquet_atomic(_chunk_frame(per_image, lo), out)
        progress.advance(hi - lo)
    progress.flush()

    parts = [pd.read_parquet(p) for p in sorted(shard_dir.glob("chunk_*.parquet"))]
    raw = pd.concat(parts, ignore_index=True) if parts else _chunk_frame([], 0)
    rows = raw["row"].to_numpy()
    det = pd.DataFrame(dict(
        sample_token=frames["sample_token"].to_numpy()[rows],
        cam=frames["cam"].to_numpy()[rows])).astype("string")
    for c in DET_DTYPES:
        det[c] = raw[c].to_numpy()
    unc = uncertainty(det[["sample_token", "cam", "conf"]],
                      frames[["sample_token", "cam", "scene_token", "frame_idx"]])
    feat = unc[["sample_token", "cam", "det_n", "det_n_conf", "det_ent", "det_tmp", "unc"]]
    write_parquet_atomic(det, job / "cache" / "detections.parquet")
    write_parquet_atomic(feat, job / "cache" / "feat_det.parquet")
    return det, feat
