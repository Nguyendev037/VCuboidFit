"""H15 · hiệu chuẩn LIDAR_TOP keyframe -> ego cho từng sample, có cache `cache/lidar_calib.parquet` (planning/11 §1).

Chỉ đọc `sample_data`, `calibrated_sensor`, `sensor` (SPEC-P05 §9.1 cho phép) — KHÔNG đọc nhãn. Lần đầu quét
metadata nuScenes rồi ghi cache (`sample_token, R` = 9 số hàng-ngang 3×3, `t` = 3 số); các lần sau chỉ đọc cache
nên không phải nạp lại `sample_data.json` (trainval ~1,3 GB).
"""
import hashlib
import json
from pathlib import Path

import numpy as np
import pandas as pd

from c4.contracts import read_table, write_table
from c4.data.geometry import quat_to_mat

CHANNEL = "LIDAR_TOP"


def _vdir(data_root: Path) -> Path | None:
    """Thư mục `v1.0-*` duy nhất dưới data_root (không có / nhiều hơn một => không hiệu chuẩn được)."""
    vdirs = sorted(p for p in Path(data_root).glob("v1.0-*") if p.is_dir())
    return vdirs[0] if len(vdirs) == 1 else None


def _scan(data_root: Path, tokens: set[str]) -> dict[str, dict]:
    """Quét metadata nuScenes -> {sample_token: {"R": [9 số], "t": [3 số]}} cho keyframe LIDAR_TOP."""
    v = _vdir(data_root)
    if v is None:
        return {}

    def rd(name):
        return json.loads((v / f"{name}.json").read_text(encoding="utf-8"))

    channel = {r["token"]: r["channel"] for r in rd("sensor")}
    calib = {r["token"]: r for r in rd("calibrated_sensor") if channel.get(r["sensor_token"]) == CHANNEL}
    out = {}
    for sd in rd("sample_data"):
        if not sd["is_key_frame"] or sd["sample_token"] not in tokens:
            continue
        c = calib.get(sd["calibrated_sensor_token"])
        if c is None:
            continue
        out[sd["sample_token"]] = {"R": quat_to_mat(c["rotation"]).reshape(-1).tolist(),
                                   "t": [float(x) for x in c["translation"]]}
    return out


def _from_cache(path: Path) -> dict[str, dict]:
    df = read_table(path, "lidar_calib")
    return {r.sample_token: {"R": np.asarray(r.R, np.float64).reshape(-1).tolist(),
                             "t": np.asarray(r.t, np.float64).reshape(-1).tolist()}
            for r in df.itertuples()}


def _to_frame(calib: dict[str, dict]) -> pd.DataFrame:
    rows = [{"sample_token": t, "R": [float(x) for x in c["R"]], "t": [float(x) for x in c["t"]]}
            for t, c in sorted(calib.items())]
    return pd.DataFrame(rows, columns=["sample_token", "R", "t"])


def lidar_to_ego(data_root, tokens, cache_path=None) -> dict[str, dict]:
    """sample_token -> {"R", "t"} (LIDAR_TOP keyframe -> ego). Cache đủ `tokens` => đọc cache, KHÔNG quét metadata.

    Thiếu hiệu chuẩn (data_root không có đúng một `v1.0-*`, sample không có keyframe LIDAR_TOP) => token vắng mặt
    trong dict; caller giữ hành vi cũ (hệ cảm biến) + cảnh báo `LIDAR_CALIB_MISSING`.
    """
    want = {str(t) for t in tokens}
    cache = Path(cache_path) if cache_path else None
    if cache is not None and cache.is_file():
        cached = _from_cache(cache)
        if want <= set(cached):
            return {t: cached[t] for t in want}
    calib = _scan(Path(data_root), want)
    if cache is not None and calib:
        cache.parent.mkdir(parents=True, exist_ok=True)
        write_table(_to_frame(calib), cache, "lidar_calib")
    return {t: c for t, c in calib.items() if t in want}


def calib_sha256(calib: dict[str, dict]) -> str:
    """sha256 nội dung ánh xạ (JSON chuẩn hoá theo token) — bền với định dạng file cache."""
    payload = {t: {"R": [float(x) for x in c["R"]], "t": [float(x) for x in c["t"]]}
               for t, c in sorted(calib.items())}
    return hashlib.sha256(json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
