import pandas as pd

from c4.contracts import validate
from tests.fixtures.make_fixture import make_fixture


def test_fixture_validates(fx):
    validate(fx.feat, "features_cache")
    validate(fx.gt, "gt_rare")
    assert len(fx.Z_img) == len(fx.feat) == len(fx.C_img)


def test_fixture_has_missing_cams(fx):
    n = fx.feat.groupby("sample_token")["cam"].nunique()
    assert n.min() >= 1
    assert (n < 6).any()


def test_fixture_deterministic():
    a, b = make_fixture(seed=0), make_fixture(seed=0)
    pd.testing.assert_frame_equal(a.feat, b.feat)
    assert (a.Z_img == b.Z_img).all()


def test_rare_frames_are_outliers(fx):
    rare = fx.feat["sample_token"].isin(fx.rare_tokens)
    assert fx.feat.loc[rare, "nov_knn"].mean() > fx.feat.loc[~rare, "nov_knn"].mean()


def test_write_job_dir_layout(job_dir):
    for rel in ["cache/features_cache.parquet", "cache/dino_cls.npy", "cache/clip_img.npy",
                "gt/gt_rare.parquet"]:
        assert (job_dir / rel).exists(), rel
