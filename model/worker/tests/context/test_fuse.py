import json

import numpy as np
import pandas as pd
import pytest

from c4.context.fuse import fuse
from c4.context.thresholds import fit_thresholds

THR = {"version": "ctx_v1",
       "cv": {"night_v_mean": 50.0, "glare_sat_frac": 0.01, "glare_blob": 0.005, "tile_range": 100.0,
              "veil": 0.5, "blur_sharp_ratio": 5.0},
       "clip": {"m_illum": 0.2, "m_glare": 0.2, "m_lens": 0.2, "m_weather": 0.2},
       "sun": {"night_deg": -6.0, "lowlight_deg": 6.0}}
NAN = float("nan")
BENIGN = dict(v_mean=100.0, sat_frac=0.0, blob_max_frac=0.0, tile_range=10.0, veil=0.1, sharp_ratio=50.0)
GLARE = dict(sat_frac=0.05, blob_max_frac=0.02)  # bật GLARE_CV
AXES = ("illum", "glare", "lens", "weather")


def _probs(axis, cls, p1, p2):
    """Mọi trục: lớp 0 (bình thường) thắng rõ; riêng `axis`: lớp `cls` có p1, lớp khác có p2."""
    out = {}
    for ax in AXES:
        row = np.full(3, 0.025)
        t, s = (cls, 1 if cls != 1 else 2) if ax == axis else (0, 1)
        a, b = (p1, p2) if ax == axis else (0.9, 0.05)
        row[t], row[s] = a, b
        out[ax] = (row / row.sum())[None, :]
    return out


def _run(axis, cls, sun, cv=None, p1=0.9, p2=0.05, thr=THR, img_ok=True):
    q = pd.DataFrame([{"sample_token": "s", "cam": "CAM_FRONT", "img_ok": img_ok, **BENIGN, **(cv or {})}])
    return fuse(q, _probs(axis, cls, p1, p2), pd.Series([sun]), thr).iloc[0]


# Luật v1.1 (SPEC-P02 §5, Đ23): m=0,2 ⇒ 2m=0,4; margin 0,9/0,05=0,85 · 0,6/0,3=0,3 · 0,45/0,35=0,1
# (trục, lớp CLIP idx, sun, đặc trưng đè, p1, p2, tag mong đợi, lý do review mong đợi)
CASES = [
    ("illum", 2, -30.0, None, 0.9, 0.05, "night", ""),                      # đêm theo mặt trời
    ("illum", 1, -30.0, None, 0.9, 0.05, "night", ""),                      # CLIP "lowlight" ảnh đêm ⇒ mặt trời thắng
    ("illum", 2, NAN, {"v_mean": 10.0}, 0.9, 0.05, "night", ""),            # không rõ sun: NIGHT_CV
    ("illum", 2, 30.0, None, 0.9, 0.05, None, "illum:DISAGREE"),            # CLIP chắc đêm, sun ban ngày
    ("illum", 1, 0.0, None, 0.9, 0.05, "lowlight", ""),                     # dải hoàng hôn
    ("illum", 2, NAN, None, 0.6, 0.3, None, ""),                            # không rõ sun, không cờ, margin < 2m ⇒ im
    ("glare", 1, NAN, GLARE, 0.9, 0.05, "glare_headlight", ""),             # chói có cờ CV
    ("glare", 1, NAN, None, 0.9, 0.05, "glare_headlight", ""),              # CLIP chắc (≥2m) dù CV không thấy
    ("glare", 1, NAN, None, 0.6, 0.3, None, "glare:DISAGREE"),              # CLIP vừa phải, không cờ ⇒ người xem
    ("glare", 0, NAN, GLARE, 0.9, 0.05, None, "glare:DISAGREE"),            # none nhưng cờ CV bật
    ("glare", 2, -20.0, GLARE, 0.9, 0.05, None, ""),                        # "nắng" khi sun < 0 ⇒ bỏ, im
    ("lens", 1, NAN, None, 0.9, 0.05, None, ""),                            # CLIP gợi ý giọt nước, không cờ ⇒ im
    ("lens", 1, NAN, {"sharp_ratio": 1.0}, 0.9, 0.05, "droplets", ""),      # có BLUR_CV
    ("weather", 1, NAN, None, 0.9, 0.05, "rain", ""),
    ("weather", 1, -30.0, None, 0.9, 0.05, None, ""),                       # đêm: không gán mưa
    ("weather", 1, NAN, None, 0.6, 0.3, None, ""),                          # margin < 2m
]


def test_fuse_rule_table():
    for axis, cls, sun, cv, p1, p2, tag, reasons in CASES:
        r = _run(axis, cls, sun, cv, p1, p2)
        got = r[f"tag_{axis}"]
        case = (axis, cls, sun, cv, p1, p2)
        assert (None if pd.isna(got) else got) == tag, case
        # cờ CV bật cho trục này có thể làm trục glare (CLIP none) DISAGREE: chỉ so lý do của chính trục
        mine = "|".join(x for x in r["review_reasons"].split("|") if x.startswith(f"{axis}:"))
        assert mine == reasons, case
        if "DISAGREE" in reasons:
            assert pd.isna(got), case  # luật thắng điểm số
        assert isinstance(r["review"], (bool, np.bool_))
        assert abs(sum(json.loads(r["p_illum"]).values()) - 1) < 1e-4
    r = _run("illum", 2, -30.0, img_ok=False)  # ảnh hỏng (01 §8)
    assert r["review"] and r["review_reasons"] == "IMG_UNREADABLE" and pd.isna(r["tag_illum"])
    q = pd.DataFrame([{"sample_token": "s", "cam": "CAM_FRONT", "img_ok": True, **BENIGN}])
    df = fuse(q, _probs("illum", 2, 0.9, 0.05), pd.Series([-30.0]), None)  # chưa đóng băng
    assert pd.isna(df.loc[0, "tag_illum"]) and not df.loc[0, "review"]
    assert df.attrs["warningCodes"] == ["CONTEXT_NOT_FROZEN"]


def test_fit_thresholds_rejects_t_tokens():
    rng = np.random.default_rng(0)
    toks = ["a", "b", "c", "d"]
    q = pd.DataFrame({"sample_token": toks, "cam": "CAM_FRONT", "img_ok": True,
                      **{k: rng.random(4) for k in ("v_mean", "sat_frac", "blob_max_frac", "tile_range",
                                                    "veil", "sharp_ratio")}})
    probs = {ax: rng.dirichlet(np.ones(3), 4) for ax in AXES}
    manifest = pd.DataFrame({"sample_token": toks, "split": ["V", "V", "V", "T"]})
    with pytest.raises(ValueError, match="LEAK_T"):
        fit_thresholds(q, probs, "V", manifest)                   # chứa token của T
    q3, p3 = q.iloc[:3], {k: v[:3] for k, v in probs.items()}
    with pytest.raises(ValueError):
        fit_thresholds(q3, p3, "T", manifest)
    thr = fit_thresholds(q3, p3, "V", manifest)
    assert thr["split"] == "V" and thr["n_frames"] == 3 and set(thr["clip"]) == {
        "m_illum", "m_glare", "m_lens", "m_weather"}
