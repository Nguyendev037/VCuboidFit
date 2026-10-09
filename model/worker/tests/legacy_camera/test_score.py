import numpy as np
import pytest

from c4.contracts import CAMS, validate
from c4.mining.score import apply_quality, frame_embeddings, frame_scores


def scores(feat, cams=CAMS):
    return frame_scores(feat, 0.4, 0.3, 0.3, cams).set_index("sample_token")


def test_rank_excludes_bad_images(fx):
    feat = fx.feat.copy()
    tok = feat["sample_token"].iloc[0]
    feat.loc[feat["sample_token"] == tok, "q_ok"] = False
    row = scores(feat).loc[tok]
    assert (row["r_nov"], row["r_unc"], row["r_qry"], row["S_hybrid"]) == (0, 0, 0, 0)
    assert not row["q_ok"]


def test_frame_score_is_max_over_available_cams(fx):
    n = fx.feat.groupby("sample_token")["cam"].nunique()
    tok = n[n == 2].index[0] if (n == 2).any() else n[n < 6].index[0]
    fs = scores(fx.feat)
    assert fs.loc[tok, "n_cams"] == n[tok]
    imgs = fx.feat[fx.feat["sample_token"] == tok]
    assert fs.loc[tok, "best_cam"] in set(imgs["cam"])
    # S_hybrid khớp với s(x) của best_cam, và lớn hơn hoặc bằng mọi camera khác
    assert fs.loc[tok, "S_hybrid"] == pytest.approx(
        0.4 * fs.loc[tok, "r_nov"] + 0.3 * fs.loc[tok, "r_unc"] + 0.3 * fs.loc[tok, "r_qry"])


def test_cameras_filter(fx):
    lacking = set(fx.feat["sample_token"]) - set(
        fx.feat.loc[fx.feat["cam"] == "CAM_FRONT", "sample_token"])
    if not lacking:
        pytest.skip("fixture has no frame lacking CAM_FRONT")
    tok = sorted(lacking)[0]
    fs = scores(fx.feat, ["CAM_FRONT"])
    assert fs.loc[tok, "S_hybrid"] == 0
    assert not fs.loc[tok, "q_ok"]
    assert fs.loc[tok, "best_cam"] == fx.feat.loc[fx.feat["sample_token"] == tok, "cam"].iloc[0]
    assert len(fs) == fx.feat["sample_token"].nunique()


def test_frame_embedding_mean_of_available_cams(fx):
    Zf, tokens = frame_embeddings(fx.Z_img, fx.feat, CAMS)
    tok = tokens[3]
    rows = fx.feat.loc[fx.feat["sample_token"] == tok, "emb_row"].to_numpy()
    m = fx.Z_img[rows].astype(np.float32).mean(0)
    assert np.allclose(Zf[3], m / np.linalg.norm(m), atol=1e-5)
    fs = scores(fx.feat)
    assert fs.loc[tok, "frame_emb_row"] == 3


def test_frame_scores_validates(fx):
    validate(frame_scores(fx.feat, 0.4, 0.3, 0.3, CAMS), "frame_scores")


def test_apply_quality_recomputes_q_ok(fx):
    feat = fx.feat.copy()
    feat.loc[0, "q_blur"] = 5.0
    feat.loc[1, "det_n"] = 0
    out = apply_quality(feat, 8, 15)
    assert not out.loc[0, "q_ok"] and not out.loc[1, "q_ok"] and out.loc[2, "q_ok"]
