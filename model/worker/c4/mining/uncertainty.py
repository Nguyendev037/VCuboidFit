# c4/mining/uncertainty.py · Unc(x) = ½ Ent + ½ Tmp
import numpy as np
import pandas as pd


def uncertainty(det: pd.DataFrame, frames: pd.DataFrame, conf_hi: float = 0.5) -> pd.DataFrame:
    """det: một dòng một detection (sample_token, cam, conf). frames: index ảnh
    (sample_token, cam, scene_token, frame_idx). Tmp so cùng camera với frame_idx - 1."""
    p = det["conf"].clip(1e-6, 1 - 1e-6)
    H = -(p * np.log(p) + (1 - p) * np.log(1 - p)) / np.log(2)  # entropy nhị phân, 0..1
    d = det.assign(H=H, hi=det["conf"] >= conf_hi)
    g = d.groupby(["sample_token", "cam"]).agg(
        det_n=("conf", "size"), det_ent=("H", "mean"), det_n_conf=("hi", "sum")).reset_index()
    f = frames.merge(g, on=["sample_token", "cam"], how="left")
    f[["det_n", "det_ent", "det_n_conf"]] = f[["det_n", "det_ent", "det_n_conf"]].fillna(0)

    prev = f[["scene_token", "cam", "frame_idx", "det_n_conf"]].assign(
        frame_idx=f["frame_idx"] + 1).rename(columns={"det_n_conf": "prev"})
    f = f.merge(prev, on=["scene_token", "cam", "frame_idx"], how="left")
    cur = f["det_n_conf"]
    denom = np.maximum(np.maximum(cur, f["prev"].fillna(0)), 1)
    # frame đầu scene hoặc frame trước thiếu camera này: Tmp = 0
    f["det_tmp"] = ((cur - f["prev"]).abs() / denom).fillna(0.0)
    f["unc"] = 0.5 * f["det_ent"] + 0.5 * f["det_tmp"]
    return f.drop(columns=["prev"]).astype(dict(
        det_n="int16", det_n_conf="int16", det_ent="float32", det_tmp="float32", unc="float32"))
