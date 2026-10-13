"""C3: luật ghép CLIP 4 trục + cờ OpenCV + độ cao mặt trời → bảng `context_frame`.

Bảng quyết định: planning/11 SPEC-P02 §5 (luật thắng điểm số: DISAGREE không bao giờ cho tag, B-vùng cấm P02).
Mọi ngưỡng đọc từ `thr` (context_thresholds_v1.json); `thr=None` ⇒ chưa đóng băng (01 §8): tag null, review False.
Không import torch/VLM.
"""
import json

import numpy as np
import pandas as pd

from c4.context.clip_axes import load_axes
from c4.contracts import CONTEXT_FRAME

CONTEXT_VERSION = "ctx_v1.1"
AXIS_ORDER = ("illum", "glare", "lens", "weather")
NORMAL = {"illum": "day", "glare": "none", "lens": "clean", "weather": "dry"}
STRONG = 2.0  # "margin ≥ 2·m" ở SPEC-P02 §5, giới hạn bởi _strong() để luôn với tới được


def _strong(m: float) -> float:
    """Ngưỡng 'CLIP chắc chắn' = min(2m, (1+m)/2): với m lớn (vd m_glare 0,51 đo trên mini) 2m > 1 là không thể đạt."""
    return min(STRONG * m, (1.0 + m) / 2.0)
OK, DISAGREE, SOFT = "OK", "DISAGREE", "SOFT"
NOT_FROZEN = "CONTEXT_NOT_FROZEN"


def cv_flag_arrays(qcv: pd.DataFrame, cv: dict) -> dict[str, np.ndarray]:
    """4 cờ CV (SPEC-P01 §3) dạng mảng bool theo hàng."""
    g = lambda c: qcv[c].to_numpy(float)  # noqa: E731
    sat, blob, tile = g("sat_frac"), g("blob_max_frac"), g("tile_range")
    glare_sat = sat >= cv["glare_sat_frac"]
    return {
        "NIGHT_CV": g("v_mean") < cv["night_v_mean"],
        "GLARE_CV": (glare_sat & (blob >= cv["glare_blob"])) | ((tile >= cv["tile_range"]) & glare_sat),
        "BLUR_CV": g("sharp_ratio") < cv["blur_sharp_ratio"],
        "VEIL_CV": g("veil") >= cv["veil"],
    }


def _decide(axis: str, cls: str, margin: float, m: float, f: dict, sun: float, sun_cfg: dict):
    """(tag|None, status) cho một trục — luật v1.1 (planning/11 SPEC-P02 §5, Đ23, đo trên ảnh thật mini).
    status: OK · DISAGREE (vào hàng đợi review) · SOFT (bỏ tag, KHÔNG review). `sun` NaN = không rõ."""
    known = not np.isnan(sun)
    if axis == "illum":
        if known:  # mặt trời là nguồn chính: CLIP không tách được night/lowlight (P 0,38/0,62 trên ảnh đêm)
            band = ("night" if sun < sun_cfg["night_deg"] else
                    "lowlight" if sun < sun_cfg["lowlight_deg"] else "day")
            opposite = {("day", "night"), ("night", "day")}
            if margin >= m and (cls, band) in opposite:
                return None, DISAGREE  # CLIP chắc chắn ngược mặt trời (vd hầm, đèn sân vận động)
            return band, OK
        if margin < m:
            return None, SOFT
        if cls == "night" and not (f["NIGHT_CV"] or f["GLARE_CV"] or margin >= _strong(m)):
            return None, SOFT
        return cls, OK
    if axis == "glare":
        cv_on = f["GLARE_CV"] or f["VEIL_CV"]
        if cls == "none":
            return (None, DISAGREE) if (f["GLARE_CV"] and margin >= m) else ("none", OK)
        if cls == "sun" and known and sun < 0:  # không có mặt trời
            return None, SOFT
        if cv_on and margin >= m:
            return f"glare_{cls}", OK
        if margin >= _strong(m):  # CLIP bắt được lóe mà CV không thấy (đo: headlight 0,82, top 4% ảnh đêm)
            return f"glare_{cls}", OK
        return (None, DISAGREE) if margin >= m else (None, SOFT)
    if axis == "lens":
        if cls == "clean" or margin < m:
            return ("clean", OK) if cls == "clean" and margin >= m else (None, SOFT)
        return (cls, OK) if (f["BLUR_CV"] or f["VEIL_CV"]) else (None, SOFT)
    if axis == "weather":
        if known and sun < sun_cfg["night_deg"]:
            return None, SOFT  # CLIP zero-shot cho P(rain)≈0,8 ở MỌI cảnh đêm (khô lẫn mưa) ⇒ không gán
        if margin < m:
            return None, SOFT
        if cls == "dry":
            return "dry", OK
        return (cls, OK) if margin >= _strong(m) else (None, SOFT)
    return None, SOFT


def _js(classes: tuple[str, ...], p: np.ndarray) -> str:
    return json.dumps({c: round(float(x), 6) for c, x in zip(classes, p)}, sort_keys=False)


def fuse(qcv: pd.DataFrame, probs: dict[str, np.ndarray], sun: pd.Series, thr: dict | None) -> pd.DataFrame:
    """qcv (bảng quality_cv, N hàng) + probs (axis → (N,k)) + sun (N, độ; NaN = null) → context_frame.

    `df.attrs["warningCodes"]` = ["CONTEXT_NOT_FROZEN"] khi thr=None."""
    n = len(qcv)
    axes = {a.name: a.classes for a in load_axes()}
    for ax in AXIS_ORDER:
        if ax not in probs or np.asarray(probs[ax]).shape != (n, len(axes[ax])):
            raise ValueError(f"probs[{ax!r}] phải có shape ({n}, {len(axes[ax])})")
    sun_arr = np.asarray(sun, dtype=float)
    if sun_arr.shape != (n,):
        raise ValueError(f"sun phải có {n} phần tử")
    P = {ax: np.asarray(probs[ax], np.float64) for ax in AXIS_ORDER}
    order = {ax: np.argsort(-P[ax], axis=1)[:, :2] for ax in AXIS_ORDER}
    top = {ax: P[ax][np.arange(n), order[ax][:, 0]] for ax in AXIS_ORDER}
    margin = {ax: top[ax] - P[ax][np.arange(n), order[ax][:, 1]] for ax in AXIS_ORDER}

    out = pd.DataFrame({"sample_token": qcv["sample_token"].to_numpy(), "cam": qcv["cam"].to_numpy(),
                        "sun_elev_deg": pd.array(np.where(np.isnan(sun_arr), np.nan, sun_arr), dtype="Float32")})
    for ax in AXIS_ORDER:
        out[f"p_{ax}"] = [_js(axes[ax], P[ax][i]) for i in range(n)]
    tags = {ax: [None] * n for ax in AXIS_ORDER}
    review = np.zeros(n, bool)
    reasons = [""] * n
    flags_s = [""] * n
    ok_img = qcv["img_ok"].to_numpy(bool)

    if thr is not None:
        flags = cv_flag_arrays(qcv, thr["cv"])
        names = ("NIGHT_CV", "GLARE_CV", "BLUR_CV", "VEIL_CV")
        for i in range(n):
            if not ok_img[i]:
                continue
            f = {k: bool(flags[k][i]) for k in names}
            flags_s[i] = "|".join(k for k in names if f[k])
            rs = []
            for ax in AXIS_ORDER:
                cls = axes[ax][order[ax][i, 0]]
                tag, st = _decide(ax, cls, margin[ax][i], thr["clip"][f"m_{ax}"], f, sun_arr[i], thr["sun"])
                tags[ax][i] = tag
                if st == DISAGREE:  # v1.1: chỉ mâu thuẫn thật vào hàng đợi; SOFT thì im lặng
                    rs.append(f"{ax}:{st}")
            reasons[i] = "|".join(rs)
            review[i] = bool(rs)
    for i in np.flatnonzero(~ok_img):  # 01 §8: ảnh hỏng luôn vào hàng đợi, kể cả khi chưa đóng băng
        review[i], reasons[i] = True, "IMG_UNREADABLE"
        for ax in AXIS_ORDER:
            tags[ax][i] = None

    for ax in AXIS_ORDER:
        out[f"tag_{ax}"] = pd.array(tags[ax], dtype="string")
    for ax in AXIS_ORDER:
        out[f"margin_{ax}"] = margin[ax].astype(np.float32)
    out["cv_flags"] = flags_s
    out["review"] = review
    out["review_reasons"] = reasons
    out["context_version"] = CONTEXT_VERSION
    out = out[list(CONTEXT_FRAME)]
    out.attrs["warningCodes"] = [NOT_FROZEN] if thr is None else []
    return out
