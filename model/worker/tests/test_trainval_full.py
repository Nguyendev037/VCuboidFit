"""Large-pack integrity, sweep completeness and historical-split isolation."""

import importlib.util
import json
import zipfile
from pathlib import Path

import pandas as pd
import pytest

from c4.lidar.nusc_splits import TRAIN, VAL

spec = importlib.util.spec_from_file_location(
    "trainval_full", Path(__file__).resolve().parents[2] / "scripts/trainval_full.py"
)
full = importlib.util.module_from_spec(spec)
spec.loader.exec_module(full)


@pytest.fixture
def dataset(tmp_path):
    root = tmp_path / "data"
    meta = root / "v1.0-trainval"
    meta.mkdir(parents=True)
    train, evaluation, excluded = TRAIN[0], VAL[0], VAL[1]
    tables = {
        "scene": [
            {"token": "sc1", "name": train, "log_token": "log"},
            {"token": "sc2", "name": evaluation, "log_token": "log"},
        ],
        "log": [{"token": "log", "logfile": "clip"}],
        "sample": [
            {"token": "s1", "scene_token": "sc1", "timestamp": 1000},
            {"token": "s2", "scene_token": "sc2", "timestamp": 2000},
        ],
        "sensor": [{"token": "sensor", "channel": "LIDAR_TOP"}],
        "calibrated_sensor": [{"token": "cal", "sensor_token": "sensor"}],
        "sample_data": [
            {
                "token": "k1",
                "sample_token": "s1",
                "calibrated_sensor_token": "cal",
                "is_key_frame": True,
                "filename": "samples/LIDAR_TOP/clip__LIDAR_TOP__1000.pcd.bin",
                "prev": "sw1",
            },
            {
                "token": "sw1",
                "sample_token": "s1",
                "calibrated_sensor_token": "cal",
                "is_key_frame": False,
                "filename": "sweeps/LIDAR_TOP/sw1.pcd.bin",
                "prev": "",
            },
            {
                "token": "k2",
                "sample_token": "s2",
                "calibrated_sensor_token": "cal",
                "is_key_frame": True,
                "filename": "samples/LIDAR_TOP/clip__LIDAR_TOP__2000.pcd.bin",
                "prev": "",
            },
        ],
    }
    for name, records in tables.items():
        (meta / f"{name}.json").write_text(json.dumps(records))
    for record in tables["sample_data"]:
        p = root / record["filename"]
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_bytes(b"lidar")
    pool = tmp_path / "pool.parquet"
    pd.DataFrame({"scene_name": [train, excluded], "split": ["V", "T"]}).to_parquet(pool)
    return root, pool, train, evaluation, excluded


def test_pack_roundtrip_and_index(dataset, tmp_path):
    root, pool, _, _, _ = dataset
    output = tmp_path / "pack"
    assert (
        full.main(
            [
                "pack",
                "--data-root",
                str(root),
                "--pool-index",
                str(pool),
                "--out",
                str(output),
                "--part-bytes",
                "100000",
            ]
        )
        == 0
    )
    manifest = full.read_json(output / "manifest.json")
    assert manifest["train_frames"] == manifest["eval_frames"] == 1
    assert manifest["sweeps"] == 10
    extracted = tmp_path / "unpack"
    for part in manifest["parts"]:
        assert full.digest(output / part["name"]) == part["sha256"]
        with zipfile.ZipFile(output / part["name"]) as z:
            assert z.testzip() is None
            z.extractall(extracted)
    exp = tmp_path / "exp"
    assert (
        full.main(
            [
                "index",
                "--data-root",
                str(extracted / "data"),
                "--manifest",
                str(output / "manifest.json"),
                "--exp",
                str(exp),
            ]
        )
        == 0
    )
    index = pd.read_parquet(exp / "index.parquet")
    assert dict(index.groupby("split").size()) == {"S": 1, "T": 1}
    assert set(index.sample_token) == {"s1", "s2"}


def test_missing_real_predecessor_is_a_gate(dataset):
    root, pool, _, _, _ = dataset
    (root / "sweeps/LIDAR_TOP/sw1.pcd.bin").unlink()
    with pytest.raises(full.Gate, match="missing required"):
        full.inventory(root, pool)


def test_missing_predecessor_metadata_is_a_gate(dataset):
    root, pool, _, _, _ = dataset
    p = root / "v1.0-trainval/sample_data.json"
    p.write_text(json.dumps([r for r in full.read_json(p) if r["token"] != "sw1"]))
    with pytest.raises(full.Gate, match="predecessor metadata"):
        full.inventory(root, pool)


def test_val_cannot_be_trained(dataset):
    _, _, train, evaluation, excluded = dataset
    with pytest.raises(full.Gate, match="official"):
        full.check_scenes([train, evaluation], [evaluation], [excluded])


def test_historical_T_cannot_be_evaluated(dataset):
    _, _, train, evaluation, excluded = dataset
    with pytest.raises(full.Gate, match="historical"):
        full.check_scenes([train], [evaluation, excluded], [excluded])


@pytest.mark.parametrize("relative", ["../escape", "/absolute", "C:/secret", "foo\\bar"])
def test_unsafe_path_rejected(tmp_path, relative):
    with pytest.raises(full.Gate):
        full.safe_path(tmp_path, relative)


def test_manifest_missing_sweep_rejected(dataset):
    root, pool, _, _, _ = dataset
    m = full.inventory(root, pool)
    m["files"] = [f for f in m["files"] if not f["path"].startswith("sweeps/")]
    with pytest.raises(full.Gate, match="omits required"):
        full.verify(root, m)


def test_nonempty_output_refused_before_inventory(tmp_path):
    output = tmp_path / "pack"
    output.mkdir()
    (output / "keep.txt").write_text("keep")
    assert (
        full.main(
            [
                "pack",
                "--data-root",
                str(tmp_path / "source"),
                "--pool-index",
                "missing",
                "--out",
                str(output),
            ]
        )
        == 3
    )
    assert (output / "keep.txt").read_text() == "keep"
