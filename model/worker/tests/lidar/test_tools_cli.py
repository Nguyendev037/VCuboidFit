"""Công cụ CLI LiDAR Tầng 0/Tầng 1 (G1 · downstream · train_seed) chạy CPU-only.

Không import torch/pcdet: chỉ chạm phần thuần Python của train_seed (detect_version,
split_infos, to_plain, seed_class_counts) và các nhánh thoát sớm của downstream.
"""
import math
import pickle

import pandas as pd
import pytest

from c4.cli import lidar_g1
from c4.contracts import write_table
from c4.data.nusc import NuscTables
from c4.lidar import load_lidar_config
from c4.lidar.index import build_lidar_index
from c4.lidar.splits import assign_splits
from c4.lidar.tier1 import downstream, train_seed
from tests.fixtures.make_nuscenes import make_nuscenes

N_SCENES, FRAMES = 3, 5
N = N_SCENES * FRAMES
# g1_table mặc định có 4 định nghĩa nhóm C (variants) ngoài các dòng tau.
N_C_VARIANTS = 7  # 4 định nghĩa "có ≥1 box" + 3 theo số lượng box khó (≥3, ≥5, ≥10)


def _write_index(out, root):
    """index.parquet ở gốc ``out`` — đúng bố cục c4.lidar.experiment.prepare."""
    out.mkdir(parents=True, exist_ok=True)
    t = NuscTables.load(root)
    index = assign_splits(build_lidar_index(t, root), load_lidar_config())
    write_table(index, str(out / "index.parquet"), "lidar_index")
    return index


# ---- (1) c4.cli.lidar_g1 -----------------------------------------------------------------


def test_lidar_g1_writes_counts_per_tau_and_split(tmp_path):
    root = make_nuscenes(tmp_path, n_scenes=N_SCENES, frames_per_scene=FRAMES)
    out = tmp_path / "out"
    index = _write_index(out, root)
    assert len(index) == N
    n_splits = index["split"].nunique()

    argv = ["--data-root", str(root), "--out", str(out), "--taus", "0.005,0.01,0.02"]
    assert lidar_g1.main(argv) == 0

    csv = pd.read_csv(out / "gt" / "g1_table.csv")
    assert list(csv.columns) == ["split", "kind", "value", "frames", "hit", "pct", "B"]
    assert set(csv["split"]) == set(index["split"])
    tau = csv[csv["kind"] == "tau"]
    assert len(tau) == n_splits * 3
    assert {float(v) for v in tau["value"]} == {0.005, 0.01, 0.02}
    assert len(csv) == n_splits * (3 + N_C_VARIANTS)
    for split, part in csv.groupby("split"):
        n = int((index["split"] == split).sum())
        assert (part["frames"] == n).all()
        assert (part["B"] == max(1, math.ceil(0.05 * n))).all()
        assert ((part["pct"] - (part["hit"] / n).round(4)).abs() < 1e-9).all()


def test_lidar_g1_missing_index_exits_4(tmp_path, capsys):
    root = make_nuscenes(tmp_path, n_scenes=N_SCENES, frames_per_scene=FRAMES)
    out = tmp_path / "out"
    out.mkdir()
    assert lidar_g1.main(["--data-root", str(root), "--out", str(out)]) == 4
    assert not (out / "gt").exists()
    assert "thiếu đầu vào" in capsys.readouterr().err


# ---- (2) c4.lidar.tier1.downstream -------------------------------------------------------


def _seed_yaml(exp, **over):
    (exp / "t1").mkdir(parents=True, exist_ok=True)
    body = {"version": "v1.0-mini", "sweeps": 1, "epochs": 1}
    body.update(over)
    (exp / "t1" / "train_config.yaml").write_text(
        "".join(f"{k}: {v}\n" for k, v in body.items()), encoding="utf-8")


def _selected(path, rows):
    pd.DataFrame(rows, columns=["rank", "budget_B", "sample_token"]).to_csv(path, index=False)
    return path


def test_downstream_missing_seed_config_exits_4(tmp_path):
    exp = tmp_path / "exp"
    exp.mkdir()
    sel = _selected(tmp_path / "selected.csv", [(1, 1, "s0")])
    argv = ["--exp", str(exp), "--selected", str(sel), "--tag", "hybrid"]
    assert downstream.main(argv) == 4
    assert not (exp / "t1").exists()


def test_downstream_selected_token_in_T_exits_2(tmp_path, capsys):
    exp = tmp_path / "exp"
    _seed_yaml(exp)
    pd.DataFrame([dict(sample_token="s0", split="S"),
                  dict(sample_token="t0", split="T")]).to_parquet(
        exp / "index.parquet", index=False)
    sel = _selected(tmp_path / "selected.csv", [(1, 2, "t0"), (2, 2, "s0")])
    argv = ["--exp", str(exp), "--selected", str(sel), "--tag", "hybrid"]
    assert downstream.main(argv) == 2
    assert "split T" in capsys.readouterr().err


def test_downstream_empty_selection_exits_2(tmp_path):
    exp = tmp_path / "exp"
    _seed_yaml(exp)
    pd.DataFrame([dict(sample_token="s0", split="S")]).to_parquet(
        exp / "index.parquet", index=False)
    sel = _selected(tmp_path / "selected.csv", [(1, 0, "s0")])
    argv = ["--exp", str(exp), "--selected", str(sel), "--tag", "hybrid"]
    assert downstream.main(argv) == 2


# ---- (3) c4.lidar.tier1.train_seed -------------------------------------------------------


def _write_infos(path, tokens):
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "wb") as f:
        pickle.dump([{"token": t} for t in tokens], f)
    return path


def test_split_infos_seed_is_subset_of_S(tmp_path):
    d = tmp_path / "t1" / "pcdet"
    all_path = _write_infos(d / "infos_all_1sweeps.pkl", ["s0", "s1", "t0", "x0"])
    index = pd.DataFrame(dict(sample_token=["s0", "t0", "s1", "x0"],
                              split=["S", "T", "S", "V"]))
    p_seed, p_ord, p_test, seed_toks = train_seed.split_infos(all_path, index, 1)

    seed = set(index.loc[index["split"] == "S", "sample_token"])
    assert set(seed_toks) <= seed
    assert seed_toks == ["s0", "s1"]  # theo thứ tự index, chỉ token nằm trong S
    assert p_seed.name == "infos_seed_1sweeps.pkl"
    assert [i["token"] for i in pickle.loads(p_seed.read_bytes())] == seed_toks
    assert [i["token"] for i in pickle.loads(p_ord.read_bytes())] == ["s0", "t0", "s1", "x0"]
    assert [i["token"] for i in pickle.loads(p_test.read_bytes())] == ["t0"]


def test_split_infos_empty_S_raises(tmp_path):
    d = tmp_path / "t1" / "pcdet"
    all_path = _write_infos(d / "infos_all_1sweeps.pkl", ["t0"])
    index = pd.DataFrame(dict(sample_token=["t0"], split=["T"]))
    with pytest.raises(ValueError, match="split S rỗng"):
        train_seed.split_infos(all_path, index, 1)


def test_to_plain_drops_base_config_recursively():
    nested = {
        "_BASE_CONFIG_": "cfgs/base.yaml",
        "a": 1,
        "b": {"_BASE_CONFIG_": "x.yaml", "c": 2},
        "d": [{"_BASE_CONFIG_": "y.yaml", "e": 3}, 4],
        "f": (5, {"_BASE_CONFIG_": "z.yaml"}),
    }
    assert train_seed.to_plain(nested) == {
        "a": 1, "b": {"c": 2}, "d": [{"e": 3}, 4], "f": [5, {}]}


def test_seed_class_counts_counts_known_classes(tmp_path):
    p = tmp_path / "infos_seed_1sweeps.pkl"
    infos = [
        {"token": "a", "gt_names": ["car", "pedestrian", "car"]},
        {"token": "b", "gt_names": ["pedestrian"]},
        {"token": "c"},  # thiếu gt_names
        {"token": "d", "gt_names": ["bicycle"]},  # ngoài class_names ⇒ bỏ
    ]
    with open(p, "wb") as f:
        pickle.dump(infos, f)
    counts = train_seed.seed_class_counts(p, ["car", "pedestrian", "truck"])
    assert counts == {"car": 2, "pedestrian": 2, "truck": 0}


def test_detect_version_requires_exactly_one_dir(tmp_path):
    root = tmp_path / "nusc"
    root.mkdir()
    (root / "v1.0-notadir").write_text("", encoding="utf-8")  # file, không phải thư mục
    with pytest.raises(FileNotFoundError, match="đúng một"):
        train_seed.detect_version(root)  # 0 thư mục v1.0-*
    (root / "v1.0-a").mkdir()
    assert train_seed.detect_version(root) == "v1.0-a"
    (root / "v1.0-b").mkdir()
    with pytest.raises(FileNotFoundError, match="đúng một"):
        train_seed.detect_version(root)  # 2 thư mục v1.0-*


def test_detect_version_returns_single_dir(tmp_path):
    root = tmp_path / "nusc"
    (root / "v1.0-mini").mkdir(parents=True)
    assert train_seed.detect_version(root) == "v1.0-mini"
