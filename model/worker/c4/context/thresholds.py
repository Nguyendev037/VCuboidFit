"""C3: fit / nạp ngưỡng bối cảnh `context_thresholds_v1.json` (CHỈ nhận split V — bất biến B3).

Contract: planning/11 · 01-CONTRACTS §4/§6, SPEC-P01 §4, SPEC-P02 §4. File sinh bởi máy, CẤM sửa tay.
"""
import hashlib
import json
from pathlib import Path

import numpy as np
import pandas as pd

from c4.context.fuse import fuse

VERSION = "ctx_v1"
SUN = {"night_deg": -6.0, "lowlight_deg": 6.0}  # hằng thiên văn (civil twilight), không fit
AXIS_ORDER = ("illum", "glare", "lens", "weather")
CV_PCT_HIGH = 97.5       # glare_sat_frac, glare_blob, tile_range, veil (SPEC-P01 §4)
CV_PCT_NIGHT = 95.0      # night_v_mean trên frame có sun_elev < night_deg
CV_PCT_BLUR = 2.5        # blur_sharp_ratio
CLIP_PCT = 20.0          # m_axis (SPEC-P02 §4)
CLIP_PCT_FALLBACK = 10.0  # khi review trên V > REVIEW_MAX
REVIEW_MAX = 0.15
CV_KEYS = ("night_v_mean", "glare_sat_frac", "glare_blob", "tile_range", "veil", "blur_sharp_ratio")


class ThresholdsNotFrozen(FileNotFoundError):
    """Chưa có context_thresholds_v1.json (01 §8): caller chạy tiếp ở chế độ không gán tag."""


def manifest_sha256(manifest: pd.DataFrame) -> str:
    """sha256 của manifest ở dạng CSV chuẩn hoá (cột sắp theo tên, hàng sắp theo mọi cột)."""
    cols = sorted(manifest.columns)
    canon = manifest[cols].sort_values(cols, kind="mergesort").to_csv(index=False, lineterminator="\n")
    return hashlib.sha256(canon.encode("utf-8")).hexdigest()


def v_tokens(manifest: pd.DataFrame, frames: pd.DataFrame | None) -> set[str]:
    if "split" not in manifest.columns:
        raise ValueError("split_manifest thiếu cột 'split'")
    v = manifest[manifest["split"] == "V"]
    if "sample_token" in manifest.columns:
        return set(v["sample_token"].astype(str))
    if "scene_token" in manifest.columns and frames is not None:  # manifest theo scene (SPEC-P04)
        scenes = set(v["scene_token"].astype(str))
        return set(frames.loc[frames["scene_token"].astype(str).isin(scenes), "sample_token"].astype(str))
    raise ValueError("split_manifest cần cột 'sample_token' (hoặc 'scene_token' kèm frames=)")


def _margins(p: np.ndarray) -> np.ndarray:
    top2 = np.sort(np.asarray(p, np.float64), axis=1)[:, -2:]
    return top2[:, 1] - top2[:, 0]


def fit_thresholds(qcv_V: pd.DataFrame, probs_V: dict[str, np.ndarray], split: str,
                   split_manifest: pd.DataFrame, *, frames: pd.DataFrame | None = None) -> dict:
    """Ngưỡng = phân vị trên V. `qcv_V` hàng-theo-hàng khớp `probs_V[axis]` (N, k); cột tuỳ chọn
    `sun_elev_deg` dùng fit `night_v_mean` (không có/không frame đêm ⇒ 0.0 = NIGHT_CV không bao giờ bật).
    `split != "V"` ⇒ ValueError; token ngoài V ⇒ ValueError("LEAK_T")."""
    if split != "V":
        raise ValueError(f"fit_thresholds chỉ nhận split='V', nhận {split!r}")
    v_set = v_tokens(split_manifest, frames)
    bad = sorted(set(qcv_V["sample_token"].astype(str)) - v_set)
    if bad:
        raise ValueError(f"LEAK_T: {len(bad)} sample_token ngoài V (vd {bad[:3]})")
    n = len(qcv_V)
    if n == 0:
        raise ValueError("qcv_V rỗng")
    for ax in AXIS_ORDER:
        if ax not in probs_V or len(probs_V[ax]) != n:
            raise ValueError(f"probs_V thiếu trục {ax} hoặc lệch số hàng ({n})")

    ok = qcv_V["img_ok"].to_numpy(bool)
    if not ok.any():
        raise ValueError("V không có ảnh đọc được")
    q = qcv_V[ok]
    sun = (qcv_V["sun_elev_deg"].to_numpy(float) if "sun_elev_deg" in qcv_V.columns
           else np.full(n, np.nan))[ok]
    night_rows = q["v_mean"].to_numpy(float)[sun < SUN["night_deg"]]
    cv = {
        "night_v_mean": float(np.percentile(night_rows, CV_PCT_NIGHT)) if len(night_rows) else 0.0,
        "glare_sat_frac": float(np.percentile(q["sat_frac"], CV_PCT_HIGH)),
        "glare_blob": float(np.percentile(q["blob_max_frac"], CV_PCT_HIGH)),
        "tile_range": float(np.percentile(q["tile_range"], CV_PCT_HIGH)),
        "veil": float(np.percentile(q["veil"], CV_PCT_HIGH)),
        "blur_sharp_ratio": float(np.percentile(q["sharp_ratio"], CV_PCT_BLUR)),
    }
    margins = {ax: _margins(probs_V[ax]) for ax in AXIS_ORDER}

    def build(pct: float) -> dict:
        return {"version": VERSION, "split": "V", "n_frames": int(n),
                "split_manifest_sha256": manifest_sha256(split_manifest),
                "cv": dict(cv),
                "clip": {f"m_{ax}": float(np.percentile(margins[ax], pct)) for ax in AXIS_ORDER},
                "clip_margin_pct": float(pct), "sun": dict(SUN)}

    thr = build(CLIP_PCT)
    out = fuse(qcv_V, probs_V, pd.Series(np.asarray(
        qcv_V["sun_elev_deg"], float) if "sun_elev_deg" in qcv_V.columns else np.full(n, np.nan)), thr)
    if float(out["review"].mean()) > REVIEW_MAX:  # SPEC-P02 §4: hạ một lần, không lặp thêm
        thr = build(CLIP_PCT_FALLBACK)
    return thr


def save_thresholds(thr: dict, path: Path) -> str:
    """Ghi JSON (sort_keys) nguyên tử; trả sha256 của file."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + ".tmp")
    with open(tmp, "w", encoding="utf-8", newline="\n") as f:
        json.dump(thr, f, sort_keys=True, indent=2)
        f.write("\n")
    tmp.replace(path)
    return hashlib.sha256(path.read_bytes()).hexdigest()


def load_thresholds(path: Path) -> tuple[dict, str]:
    """(thresholds, sha256 byte của file). Thiếu file ⇒ ThresholdsNotFrozen; sai khoá ⇒ ValueError."""
    path = Path(path)
    if not path.is_file():
        raise ThresholdsNotFrozen(str(path))
    raw = path.read_bytes()
    thr = json.loads(raw.decode("utf-8"))
    miss = [k for k in CV_KEYS if k not in thr.get("cv", {})] + \
           [f"m_{a}" for a in AXIS_ORDER if f"m_{a}" not in thr.get("clip", {})] + \
           [k for k in ("night_deg", "lowlight_deg") if k not in thr.get("sun", {})]
    if miss:
        raise ValueError(f"{path}: thiếu ngưỡng {miss}")
    return thr, hashlib.sha256(raw).hexdigest()
