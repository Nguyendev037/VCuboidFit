import json

import pandas as pd
import pytest

from c4.config import load_config
from c4.contracts import ContractError, read_table, validate, write_table


def features_row(token="t0", cam="CAM_FRONT", emb_row=0):
    return dict(
        sample_token=token, cam=cam, scene_token="scene0", split="pool", frame_idx=0,
        img_path=f"samples/{cam}/{token}.jpg", emb_row=emb_row, nov_knn=0.3, det_n=2,
        det_n_conf=1, det_ent=0.4, det_tmp=0.0, unc=0.2, qry_max=0.25, qry_best="night_rain",
        q_bright=120.0, q_blur=80.0, q_ok=True,
    )


def features_df():
    return pd.DataFrame([features_row("t0", "CAM_FRONT", 0), features_row("t0", "CAM_BACK", 1)])


def test_validate_missing_column_raises():
    with pytest.raises(ContractError, match="nov_knn"):
        validate(features_df().drop(columns=["nov_knn"]), "features_cache")


def test_validate_duplicate_key_raises():
    df = pd.DataFrame([features_row("t0", "CAM_FRONT", 0), features_row("t0", "CAM_FRONT", 1)])
    with pytest.raises(ContractError):
        validate(df, "features_cache")


def test_validate_nan_in_numeric_raises():
    df = features_df()
    df.loc[0, "unc"] = float("nan")
    with pytest.raises(ContractError):
        validate(df, "features_cache")


def test_validate_unknown_camera_raises():
    df = pd.DataFrame([features_row("t0", "CAM_TOP", 0)])
    with pytest.raises(ContractError):
        validate(df, "features_cache")


@pytest.mark.parametrize("ext", ["csv", "parquet"])
def test_write_read_roundtrip_csv_and_parquet(tmp_path, ext):
    path = str(tmp_path / f"features.{ext}")
    write_table(features_df(), path, "features_cache", note="x")
    back = read_table(path, "features_cache")
    pd.testing.assert_frame_equal(back, validate(features_df(), "features_cache"))
    info = json.loads((tmp_path / f"features.{ext}.manifest.json").read_text())
    assert info["rows"] == 2
    assert info["schema_version"] == "1.2"
    assert not list(tmp_path.glob("*.tmp"))


def test_load_config_profile_override(tmp_path):
    (tmp_path / "profiles").mkdir()
    base = load_config()
    (tmp_path / "profiles" / "fast.yaml").write_text("mmr:\n  lambda: 0.5\n")
    cfg = load_config("fast", profiles_dir=tmp_path / "profiles")
    assert cfg.mmr["lambda"] == 0.5
    assert cfg.mmr["max_per_scene"] == base.mmr["max_per_scene"] == 3
    assert cfg.budget == 0.05
