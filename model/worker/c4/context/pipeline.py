"""C3: chạy tầng bối cảnh trên một job: quality_cv + sun + OpenCLIP 4 trục + luật ghép → context_frame.

Đầu vào có sẵn: index/frames.parquet, cache/clip_img.npy (CẤM gọi encoder ảnh — B4). Chỉ text encoder
chạy ở đây (CPU, nạp lười để import module không kéo torch). Contract: planning/11 · 01-CONTRACTS §1/§8.
"""
from pathlib import Path

import numpy as np
import pandas as pd
import yaml

from c4.context.clip_axes import axis_probs, encode_axes, load_axes
from c4.context.fuse import CONTEXT_VERSION, fuse
from c4.context.quality_cv import extract_quality_cv, load_frames
from c4.context.sun import sun_elevation_deg
from c4.contracts import CONTEXT_FRAME, ContractError, read_table, write_table
from c4.context.thresholds import (ThresholdsNotFrozen, fit_thresholds, load_thresholds,
                                   save_thresholds, v_tokens)
from c4.data.nusc import NuscTables

LOCATIONS_PATH = Path(__file__).resolve().parent.parent.parent / "configs" / "locations.yaml"
THRESHOLDS_NAME = "context_thresholds_v1.json"


class ClipCacheMissing(FileNotFoundError):
    """Thiếu cache/clip_img.npy (01 §8). Pipeline này KHÔNG tự chạy encoder ảnh; caller chạy extract_clip."""


def default_text_encoder():
    """OpenClipTextEncoder nạp lười (chỉ lúc gọi; torch không bị import khi import module này)."""
    from c4.extract.clip import OpenClipTextEncoder
    return OpenClipTextEncoder()


def thresholds_default_path(job_dir) -> Path:
    return Path(job_dir) / "cache" / THRESHOLDS_NAME


def load_locations(path: Path | None = None) -> dict[str, tuple[float, float]]:
    data = yaml.safe_load(Path(path or LOCATIONS_PATH).read_text(encoding="utf-8")) or {}
    return {k: (float(v["lat"]), float(v["lon"])) for k, v in data.items()}


def compute_sun(frames: pd.DataFrame, data_root) -> pd.Series:
    """Độ cao mặt trời theo hàng `frames` (timestamp µs + log.location); NaN khi location lạ/thiếu log."""
    t = NuscTables.load(data_root)
    loc = load_locations()
    scene_loc = {}
    for tok, sc in t.scene.items():
        lg = t.log.get(sc.get("log_token", ""), {})
        scene_loc[tok] = loc.get(lg.get("location", ""))
    vals = []
    for sc, ts in zip(frames["scene_token"], frames["timestamp"]):
        ll = scene_loc.get(sc)
        vals.append(np.nan if ll is None else sun_elevation_deg(int(ts), ll[0], ll[1]))
    return pd.Series(np.asarray(vals, float), index=frames.index)


def _load_clip(job_dir: Path, n_expected: int) -> np.ndarray:
    p = job_dir / "cache" / "clip_img.npy"
    if not p.is_file():
        raise ClipCacheMissing(f"thiếu {p} (chạy c4.cli.extract_clip trước)")
    C = np.load(p, mmap_mode="r")
    if C.ndim != 2 or C.shape[0] != n_expected:
        raise ContractError(f"clip_img.npy {C.shape} lệch số hàng frames ({n_expected})")
    return C


def _quality(job_dir: Path, data_root, frames: pd.DataFrame) -> pd.DataFrame:
    p = job_dir / "cache" / "quality_cv.parquet"
    if p.is_file():
        q = read_table(p, "quality_cv")
        if (len(q) == len(frames) and (q["sample_token"].to_numpy() == frames["sample_token"].to_numpy()).all()
                and (q["cam"].to_numpy() == frames["cam"].to_numpy()).all()):
            return q
    return extract_quality_cv(job_dir, Path(data_root))


def _probs(C: np.ndarray, encoder) -> dict[str, np.ndarray]:
    T = encode_axes(load_axes(), encoder)
    return axis_probs(np.asarray(C, np.float32), T, float(encoder.logit_scale))


def run_context(job_dir, data_root, *, profile: str = "multisensor", thresholds_path=None,
                encoder=None) -> pd.DataFrame:
    """Sinh + ghi cache/context_frame.parquet. `lidar_only` ⇒ bỏ qua tầng (trả bảng rỗng, không ghi).

    Chưa có ngưỡng đóng băng ⇒ tag null, review False, manifest ghi warning_codes=["CONTEXT_NOT_FROZEN"]."""
    job = Path(job_dir)
    if profile == "lidar_only":
        return pd.DataFrame({c: pd.Series(dtype="object") for c in CONTEXT_FRAME})
    frames = load_frames(job)
    C = _load_clip(job, len(frames))
    qcv = _quality(job, data_root, frames)
    sun = compute_sun(frames, data_root)
    probs = _probs(C, encoder if encoder is not None else default_text_encoder())
    tpath = Path(thresholds_path) if thresholds_path else thresholds_default_path(job)
    try:
        thr, sha = load_thresholds(tpath)
    except ThresholdsNotFrozen:
        thr, sha = None, ""
    df = fuse(qcv, probs, sun, thr)
    write_table(df, job / "cache" / "context_frame.parquet", "context_frame",
                context_version=CONTEXT_VERSION, thresholds_sha256=sha,
                warning_codes=list(df.attrs.get("warningCodes", [])))
    return df


def fit_context(job_dir, split: str, manifest_path, *, data_root=None, encoder=None, out=None) -> tuple[dict, str, Path]:
    """Fit ngưỡng trên V: đọc quality_cv + clip_img.npy, chọn hàng thuộc V theo manifest, ghi JSON.
    `data_root` (tuỳ chọn) cho `sun_elev_deg` ⇒ fit `night_v_mean`; thiếu ⇒ NIGHT_CV tắt (ngưỡng 0.0)."""
    job = Path(job_dir)
    mp = Path(manifest_path)
    if not mp.is_file():
        raise FileNotFoundError(f"thiếu split manifest {mp}")
    manifest = pd.read_csv(mp)
    frames = load_frames(job)
    C = _load_clip(job, len(frames))
    qp = job / "cache" / "quality_cv.parquet"
    if not qp.is_file():
        raise FileNotFoundError(f"thiếu {qp} (chạy c4.cli.context cv trước)")
    qcv = read_table(qp, "quality_cv")
    if len(qcv) != len(frames):
        raise ContractError("quality_cv lệch số hàng với frames")
    if data_root is not None:
        qcv = qcv.assign(sun_elev_deg=compute_sun(frames, data_root).to_numpy())
    if split == "V":  # split khác "V" để fit_thresholds tự từ chối
        v_set = v_tokens(manifest, frames)
        sel = qcv["sample_token"].astype(str).isin(v_set).to_numpy()
    else:
        sel = np.ones(len(qcv), bool)
    if not sel.any():
        raise ValueError("không có frame nào thuộc V trong job")
    probs = _probs(np.asarray(C)[sel], encoder if encoder is not None else default_text_encoder())
    thr = fit_thresholds(qcv[sel].reset_index(drop=True), probs, split, manifest, frames=frames)
    path = Path(out) if out else thresholds_default_path(job)
    return thr, save_thresholds(thr, path), path
