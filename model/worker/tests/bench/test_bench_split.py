"""Kiểm split chỉ phụ thuộc tên chuỗi."""
import hashlib

import pytest

from c4.bench.split import plan_bench_split
from tests.fixtures.make_nuscenes import make_nuscenes


def test_split_deterministic_partition():
    names = [f"scene-{i}" for i in range(101)]
    got = plan_bench_split(names)
    assert got == plan_bench_split(names[::-1])
    assert set(got) == set(names)
    assert [list(got.values()).count(s) for s in ("CAL", "POOL", "EVAL")] == [20, 56, 25]
    ordered = sorted(names, key=lambda n: hashlib.sha1(f"{n}|20261017".encode()).hexdigest())
    assert {n for n in names if got[n] == "CAL"} == set(ordered[:20])
    assert {n for n in names if got[n] == "EVAL"} == set(ordered[-25:])
    assert got != plan_bench_split(names, seed=1)


@pytest.mark.parametrize("names,frac", [(["a", "a"], None), (["a"], {"CAL": 1})])
def test_split_rejects_bad_contract(names, frac):
    with pytest.raises(ValueError):
        plan_bench_split(names, **({"frac": frac} if frac is not None else {}))


def test_fixture_names_only(tmp_path):
    import json

    make_nuscenes(tmp_path, n_scenes=2, frames_per_scene=2)
    scene_file = next(tmp_path.glob("data/v*/scene.json"))
    scenes = json.loads(scene_file.read_text())
    names = [s["name"] for s in scenes]
    before = plan_bench_split(names)
    for scene in scenes:
        scene["description"] = "unrelated labels and metadata"
    assert before == plan_bench_split([s["name"] for s in scenes])
