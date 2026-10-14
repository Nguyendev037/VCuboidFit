"""planning/15: scripts/colab_pp_night.py — seed pack/split never touch pool V/T; diag on V."""

import importlib.util
import json
import os
import zipfile
from pathlib import Path

import pandas as pd
import pytest

from c4.contracts import write_table
from c4.rare.eval import reachability

SCRIPT = Path(__file__).resolve().parents[2] / "scripts" / "colab_pp_night.py"
spec = importlib.util.spec_from_file_location("colab_pp_night", SCRIPT)
night = importlib.util.module_from_spec(spec)
spec.loader.exec_module(night)

POOL = [
    "scene-0001",
    "scene-0002",
    "scene-0004",
    "scene-0005",
    "scene-0006",
    "scene-0007",
    "scene-0003",
    "scene-0012",
]  # 6 official TRAIN + 2 official VAL
EXTRA_TRAIN = ["scene-0008", "scene-0009"]
PARTIAL_TRAIN = "scene-0010"
EXTRA_VAL = "scene-0013"
N_KF = 3


def _meta(root: Path, scenes: list[str], version="v1.0-trainval") -> dict[str, list[str]]:
    """Minimal nuScenes json (scene/sample/log) -> {scene: [keyframe rel paths]}."""
    vd = root / version
    vd.mkdir(parents=True, exist_ok=True)
    rows_scene, rows_sample, rows_log, rels = [], [], [], {}
    for k, name in enumerate(scenes):
        log = f"n000-log-{k:02d}"
        rows_log.append(dict(token=f"log{k}", logfile=log))
        rows_scene.append(dict(token=f"sc{k}", name=name, log_token=f"log{k}", nbr_samples=N_KF))
        rels[name] = []
        for j in range(N_KF):
            ts = 1_000_000 * (k + 1) + j * 500_000
            rows_sample.append(dict(token=f"{name}-s{j}", scene_token=f"sc{k}", timestamp=ts))
            rels[name].append(f"samples/LIDAR_TOP/{log}__LIDAR_TOP__{ts}.pcd.bin")
    for n, rows in (("scene", rows_scene), ("sample", rows_sample), ("log", rows_log)):
        (vd / f"{n}.json").write_text(json.dumps(rows), encoding="utf-8")
    return rels


def _files(root: Path, rels: list[str]) -> None:
    for r in rels:
        p = root / r
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_bytes(b"\0" * 64)


ALL = POOL + EXTRA_TRAIN + [PARTIAL_TRAIN, EXTRA_VAL]


@pytest.fixture
def full_root(tmp_path):
    root = tmp_path / "trainval"
    rels = _meta(root, ALL)
    for n in ALL:
        _files(root, rels[n][:1] if n == PARTIAL_TRAIN else rels[n])
    pd.DataFrame({"scene_name": POOL}).to_parquet(tmp_path / "pool_index.parquet")
    return root, rels


def test_pack_seed_selects_only_official_train_outside_pool(full_root, tmp_path, capsys):
    root, rels = full_root
    args = [
        "pack-seed",
        "--data-root",
        str(root),
        "--pool-index",
        str(tmp_path / "pool_index.parquet"),
    ]
    assert night.main(args + ["--out", str(tmp_path / "unused"), "--dry-run"]) == 0
    dry = json.loads(capsys.readouterr().out.splitlines()[0])
    assert dry["seed_scenes"] == 2 and dry["keyframes"] == 2 * N_KF
    assert dry["partial_scenes"] == [PARTIAL_TRAIN] and dry["excluded_val_outside_pool"] == 1
    assert not (tmp_path / "unused").exists()
    out = tmp_path / "pack"
    assert night.main(args + ["--out", str(out), "--part-bytes", "1000000"]) == 0
    man = json.loads((out / "manifest.json").read_text(encoding="utf-8"))
    assert man["scenes"] == EXTRA_TRAIN and man["file_count"] == 2 * N_KF
    names = set()
    for part in man["parts"]:
        assert night.file_sha(out / part["name"]) == part["sha256"]
        with zipfile.ZipFile(out / part["name"]) as z:
            names |= set(z.namelist())
    assert names == {"data/" + r for n in EXTRA_TRAIN for r in rels[n]}
    assert man["pool_split_sha256"] == night.split_sha(night.pool_split_map(POOL))
    assert night.main(args + ["--out", str(out)]) == 3  # non-empty output refused


def _split_roots(tmp_path, extra=EXTRA_TRAIN):
    pool_root, seed_root = tmp_path / "pool", tmp_path / "seed"
    rels = _meta(pool_root, ALL)
    for n in POOL:
        _files(pool_root, rels[n])
    for n in extra:
        _files(seed_root, rels[n])
    return pool_root, seed_root, rels


def test_seed_split_trains_on_S_plus_pack_and_never_on_V_or_T(tmp_path, capsys):
    pool_root, seed_root, rels = _split_roots(tmp_path)
    smap = night.pool_split_map(POOL)
    man = tmp_path / "manifest.json"
    man.write_text(json.dumps(dict(scenes=EXTRA_TRAIN, pool_split_sha256=night.split_sha(smap))))
    exp = tmp_path / "exp"
    args = [
        "seed-split",
        "--pool-root",
        str(pool_root),
        "--seed-root",
        str(seed_root),
        "--exp",
        str(exp),
        "--manifest",
        str(man),
    ]
    assert night.main(args) == 0
    idx = pd.read_parquet(exp / "index.parquet")
    by = idx.groupby("split")["scene_name"].apply(set).to_dict()
    assert by["S"] == {n for n, s in smap.items() if s == "S"} | set(EXTRA_TRAIN)
    assert by["T"] == {n for n, s in smap.items() if s == "P"}  # exp "T" = pool P holdout
    forbidden = {n for n, s in smap.items() if s in ("V", "T")}
    assert not forbidden & set(idx["scene_name"])
    assert set(idx["split"]) == {"S", "T"}
    capsys.readouterr()
    assert night.main(args) == 0 and "skip" in capsys.readouterr().out  # idempotent
    man.write_text(
        json.dumps(dict(scenes=EXTRA_TRAIN[:1], pool_split_sha256=night.split_sha(smap)))
    )
    assert night.main(args) == 3  # manifest disagrees with disk


def test_seed_split_refuses_val_scene_and_wrong_split_sha(tmp_path):
    pool_root, seed_root, _ = _split_roots(tmp_path, EXTRA_TRAIN + [EXTRA_VAL])
    base = [
        "seed-split",
        "--pool-root",
        str(pool_root),
        "--seed-root",
        str(seed_root),
        "--exp",
        str(tmp_path / "exp"),
        "--dry-run",
    ]
    assert night.main(base + ["--expect-split-sha", "none"]) == 3  # official VAL in seed set
    pool_root2, seed_root2, _ = _split_roots(tmp_path / "b")
    base2 = [
        "seed-split",
        "--pool-root",
        str(pool_root2),
        "--seed-root",
        str(seed_root2),
        "--exp",
        str(tmp_path / "exp2"),
        "--dry-run",
    ]
    assert night.main(base2 + ["--expect-split-sha", "0" * 64]) == 3
    assert night.main(base2 + ["--expect-split-sha", "none"]) == 0
    assert not (tmp_path / "exp2").exists()  # dry-run writes nothing


def _can_symlink(tmp_path) -> bool:
    try:
        os.symlink(tmp_path, tmp_path / "probe_link", target_is_directory=True)
        return True
    except OSError:
        return False


def test_seed_split_link_makes_one_root(tmp_path):
    if not _can_symlink(tmp_path):
        pytest.skip("symlinks not permitted on this host (Windows without developer mode)")
    pool_root, seed_root, _ = _split_roots(tmp_path)
    exp = tmp_path / "exp"
    assert (
        night.main(
            [
                "seed-split",
                "--pool-root",
                str(pool_root),
                "--seed-root",
                str(seed_root),
                "--exp",
                str(exp),
                "--expect-split-sha",
                "none",
                "--link",
            ]
        )
        == 0
    )
    idx = pd.read_parquet(exp / "index.parquet")
    assert all((seed_root / p).is_file() for p in idx["lidar_path"])
    assert (seed_root / "v1.0-trainval" / "scene.json").is_file()


def _lidar_index(path: Path, splits: dict[str, int]) -> None:
    rows = []
    for k, (sp, n) in enumerate(splits.items()):
        for j in range(n):
            rows.append(
                dict(
                    sample_token=f"{sp}{j}",
                    scene_token=f"sc{k}",
                    scene_name=f"scene-{k}",
                    split=sp,
                    frame_idx=j,
                    timestamp=j,
                    lidar_path=f"x/{sp}{j}.bin",
                    ego_x=0.0,
                    ego_y=0.0,
                    ego_yaw=0.0,
                )
            )
    path.parent.mkdir(parents=True, exist_ok=True)
    write_table(pd.DataFrame(rows), str(path), "lidar_index")


def test_split_manifest_gates_counts(tmp_path):
    job = tmp_path / "job"
    _lidar_index(job / "lidar" / "index.parquet", {"S": 2, "V": 3, "P": 1, "T": 2})
    base = ["split-manifest", "--job", str(job), "--expect-split-sha", "none"]
    assert night.main(base) == 3  # default trainval counts do not match
    assert not (job / "split_manifest.csv").exists()
    assert night.main(base + ["--expect-counts", "S=2,V=3,P=1,T=2"]) == 0
    csv = pd.read_csv(job / "split_manifest.csv")
    assert list(csv.columns) == ["sample_token", "split"] and len(csv) == 8


def test_diag_refuses_T_before_reading_anything(tmp_path, capsys):
    code = night.main(
        [
            "diag",
            "--job",
            str(tmp_path / "absent"),
            "--data-root",
            str(tmp_path),
            "--run",
            "A=nowhere",
            "--split",
            "T",
            "--out",
            str(tmp_path / "o"),
        ]
    )
    assert code == 3 and "T is closed" in capsys.readouterr().err


def test_read_run_rejects_non_V_selection(tmp_path):
    d = tmp_path / "sel"
    d.mkdir()
    (d / "config_used.json").write_text(json.dumps(dict(pool_split="T", ref_split="V")))
    with pytest.raises(night.Gate):
        night.read_run(d, "V")


def test_reach_flags_agree_with_eval_and_bootstrap_is_paired():
    objs = pd.DataFrame(
        dict(sample_token=["f1", "f2", "f3"], cx=[0.0, 5.0, 9.0], cy=[0.0, 0.0, 0.0])
    )
    gt = pd.DataFrame(
        dict(
            instance_token=["i1", "i2", "i3"],
            sample_token=["f1", "f2", "f3"],
            cx=[0.5, 7.0, 9.2],
            cy=[0.0, 0.0, 0.0],
        )
    )
    tf = {"i1": {"f1"}, "i2": {"f2"}, "i3": {"f3"}}
    flags = night.reach_flags(objs, gt, tf)
    assert flags == {"i1": True, "i2": False, "i3": True}
    assert sum(flags.values()) == reachability(objs, gt, tf)["n_reachable"]
    scene = {"i1": "s1", "i2": "s2", "i3": "s3"}
    b = night.bootstrap_reach({"A": flags, "B": dict(flags)}, scene, n_boot=200)
    assert ((b["A"] - b["B"]).abs() < 1e-12).all()  # same scene draws for every run
    assert b.equals(night.bootstrap_reach({"A": flags, "B": dict(flags)}, scene, n_boot=200))


def test_det_recall_counts_pp_sources_and_point_bins():
    objs = pd.DataFrame(
        dict(sample_token=["f1", "f1"], cx=[0.0, 10.0], cy=[0.0, 0.0], source=["cluster", "merged"])
    )
    boxes = {
        "f1": [
            dict(x=0.3, y=0.0, pts=3, group="pedestrian"),
            dict(x=10.0, y=0.5, pts=20, group="bicycle"),
            dict(x=30.0, y=0.0, pts=0, group="pedestrian"),
        ]
    }  # 0 points: not counted
    rows = {
        (r["radius_m"], r["group"], r["pts"]): r
        for r in night.det_recall(objs, boxes, radii=(1.0,))
    }
    assert rows[(1.0, "all", "all")]["n_gt"] == 2
    assert rows[(1.0, "all", "all")]["recall_any"] == 1.0
    assert rows[(1.0, "all", "all")]["recall_pp"] == 0.5
    assert rows[(1.0, "pedestrian", "<8")]["recall_pp"] == 0.0
    assert rows[(1.0, "bicycle", ">=8")]["recall_pp"] == 1.0


def test_pool_split_constant_matches_its_definition():
    assert len(night.POOL_SPLIT_SHA) == 64 and sum(night.POOL_COUNTS.values()) == 6753
