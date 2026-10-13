import numpy as np
import pandas as pd

from c4.cli import context as context_cli
from c4.context.quality_cv import FEATURE_KEYS, QUALITY_WH, extract_quality_cv, quality_features
from c4.contracts import QUALITY_CV, read_table, write_table
from c4.data.index import build_frames
from c4.data.nusc import NuscTables
from tests.fixtures.make_nuscenes import make_nuscenes

W, H = QUALITY_WH


def _job(tmp_path, **kw):
    root = make_nuscenes(tmp_path, **kw)
    frames = build_frames(NuscTables.load(root), root)
    job = tmp_path / "job"
    (job / "index").mkdir(parents=True)
    write_table(frames, job / "index" / "frames.parquet", "frames")
    return root, job, frames


def test_quality_features_synthetic_blob():
    img = np.full((H, W, 3), 20, np.uint8)
    img[100:147, 200:248] = 255  # đốm trắng ≈ 2% diện tích
    f = quality_features(img)
    assert list(f) == FEATURE_KEYS and len(f) == 13
    assert 0.015 < f["sat_frac"] < 0.025
    assert 0.015 < f["blob_max_frac"] < 0.03 and f["blob_count"] == 1
    assert f["tile_range"] > 0 and f["v_mean"] > 20


def test_cli_cv_writes_parquet_and_unreadable_image_is_flagged(tmp_path):
    _, _, probe = _job(tmp_path / "probe")
    root, job, frames = _job(tmp_path / "real", corrupt=[probe["img_path"].iloc[0]])
    assert context_cli.main(["cv", "--job-dir", str(job), "--data-root", str(root)]) == 0
    df = pd.read_parquet(job / "cache" / "quality_cv.parquet")
    assert list(df.columns) == list(QUALITY_CV) and len(df.columns) == 16 and len(df) == len(frames)
    assert df["img_ok"].tolist() == [False] + [True] * (len(frames) - 1)
    assert (df.loc[0, FEATURE_KEYS] == 0).all() and not df[FEATURE_KEYS].isna().any(axis=None)
    read_table(job / "cache" / "quality_cv.parquet", "quality_cv")  # hợp lệ theo contract


def test_cli_limit_and_missing_frames(tmp_path):
    root, job, _ = _job(tmp_path)
    assert len(extract_quality_cv(job, root, limit=4, workers=2)) == 4
    assert context_cli.main(["cv", "--job-dir", str(tmp_path / "nojob"), "--data-root", str(root)]) == 2
