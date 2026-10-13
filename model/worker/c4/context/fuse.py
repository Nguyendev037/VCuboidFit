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

CONTEXT_VERSION = "ctx_v1"
AXIS_ORDER = ("illum", "glare", "lens", "weather")
NORMAL = {"illum": "day", "glare": "none", "lens": "clean", "weather": "dry"}
STRONG = 2.0  # "margin ≥ 2·m" ở SPEC-P02 §5
OK, DISAGREE, LOW_MARGIN = "OK", "DISAGREE", "LOW_MARGIN"
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
    """(tag|None, status) cho một trục — bảng SPEC-P02 §5. `sun` NaN = không rõ."""
    if margin < m:
        return None, LOW_MARGIN
    known = not np.isnan(sun)
    if axis == "illum":
        if cls == "night":
            if (known and sun < sun_cfg["night_deg"]) or f["NIGHT_CV"]:
                return "night", OK
            if not known and f["GLARE_CV"]:  # đèn pha kéo v_mean lên làm tắt NIGHT_CV
                return ("night", OK) if margin >= STRONG * m else (None, LOW_MARGIN)
            return None, DISAGREE
        if cls == "day":
            if not f["NIGHT_CV"] and (not known or sun >= sun_cfg["lowlight_deg"]):
                return "day", OK
            return None, DISAGREE
        if cls == "lowlight":
            in_band = (not known) or (sun_cfg["night_deg"] <= sun < sun_cfg["lowlight_deg"])
            if in_band and not f["NIGHT_CV"]:
                return "lowlight", OK
            return None, DISAGREE
    elif axis == "glare":
        if cls == "none":
            return (None, DISAGREE) if f["GLARE_CV"] else ("none", OK)
        if not (f["GLARE_CV"] or f["VEIL_CV"]):
            return None, DISAGREE
        if cls == "sun" and known and sun < 0:  # không có mặt trời
            return None, DISAGREE
        return f"glare_{cls}", OK
    elif axis == "lens":
        if cls == "clean":
            return "clean", OK
        return (cls, OK) if (f["BLUR_CV"] or f["VEIL_CV"]) else (None, DISAGREE)
    elif axis == "weather":
        if cls == "dry":
            return "dry", OK
        return (cls, OK) if margin >= STRONG * m else (None, LOW_MARGIN)
    return None, DISAGREE


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
                # LOW_MARGIN của lớp "bình thường" không vào hàng đợi (SPEC-P02 §5); DISAGREE luôn vào
                if st == DISAGREE or (st == LOW_MARGIN and cls != NORMAL[ax]):
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
