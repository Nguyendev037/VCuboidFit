"""M2 · smoke rare_v24 trên nuScenes giả: chạy hết pipeline, len(selected) == B, bảng qua validate (SPEC-P05 §12/§14.5)."""
import copy
import json

import numpy as np
import pytest

from c4.cli import build_index, lidar_index, lidar_t0
from c4.cli import rare as rare_cli
from c4.contracts import CONTEXT_FRAME, read_table, write_table
from c4.lidar import load_lidar_config
from c4.rare.pipeline import run_rare_v24
from c4.rare.select import rare_selector
from c4.rare.semantic import build_crops
from tests.fixtures.make_nuscenes import make_nuscenes

N_SCENES, FRAMES = 2, 6


@pytest.fixture
def job(tmp_path, monkeypatch):
    c = copy.deepcopy(load_lidar_config())
    c["filter"]["min_points"] = 50  # 300 điểm/frame của fixture đều hợp lệ
    monkeypatch.setattr(lidar_t0, "load_lidar_config", lambda: c)
    blobs = {(s, i): [("human.pedestrian.adult", (8.0 + i, 2.0 * s, 0.0), 150)]
             for s in range(N_SCENES) for i in range(FRAMES)}
    root = make_nuscenes(tmp_path, n_scenes=N_SCENES, frames_per_scene=FRAMES, rare_frames=blobs)
    j = tmp_path / "job"
    assert lidar_index.main(["--data-root", str(root), "--job-dir", str(j)]) == 0
    assert lidar_t0.main(["--data-root", str(root), "--job-dir", str(j)]) == 0
    return root, j


def test_smoke_selects_exactly_B(job):
    root, j = job
    r = run_rare_v24(j, root, budget_frac=0.25, pool_split="all", ref_split="all", scoring={"min_ref_vru": 0})
    n = N_SCENES * FRAMES
    assert r["modelMode"] == "cluster_only" and r["B"] == 3 and len(r["selected"]) == r["B"]
    assert len(r["ranking"]) == r["eligible_n"] <= n and r["selected"] == r["ranking"][:3]
    assert rare_selector(r["ranking"])(r["ranking"], 2) == r["ranking"][:2]
    d = r["selection_dir"]
    objs, frames = read_table(d / "rare_objects.parquet", "rare_objects"), read_table(d / "rare_frames.parquet",
                                                                                      "rare_frames")
    assert len(objs) > 0 and len(frames) == n and int(frames["selected"].sum()) == 3
    assert set(frames.loc[frames["selected"], "gate"]) == {"valid"}
    assert json.loads((d / "config_used.json").read_text(encoding="utf-8"))["B_resolved"] == 3


def test_missing_input_exits_2_and_small_ref_exits_3(job, tmp_path, capsys):
    root, j = job
    assert rare_cli.main(["run", "--job-dir", str(tmp_path / "nojob"), "--data-root", str(root)]) == 2
    assert "lidar/index.parquet" in capsys.readouterr().err
    assert rare_cli.main(["run", "--job-dir", str(j), "--data-root", str(root), "--pool-split", "all",
                          "--ref-split", "all"]) == 3  # fixture < 50 object VRU
    assert "PRED_REF_TOO_SMALL" in capsys.readouterr().err


def test_multisensor_profile_fake_models(job, monkeypatch, capsys):
    """M3 · crops (giả, không torch) -> run --profile multisensor; thiếu cache => exit 2 nêu tên file (SPEC-P06 §5, §7)."""
    root, j = job
    monkeypatch.setenv("C4_FAKE_MODELS", "1")
    assert build_index.main(["--data-root", str(root), "--job-dir", str(j), "--device", "cpu"]) == 0
    sc = {"min_ref_vru": 0}
    base = run_rare_v24(j, root, budget_frac=0.25, pool_split="all", ref_split="all", scoring=sc)
    ctx = read_table(j / "index" / "frames.parquet", "frames")[["sample_token", "cam"]].copy()
    for c, t in CONTEXT_FRAME.items():
        if c not in ctx:
            ctx[c] = {"string": "", "Float32": 40.0, "float32": 0.5, "bool": False}[t]
    (j / "cache").mkdir(exist_ok=True)
    write_table(ctx, j / "cache" / "context_frame.parquet", "context_frame")
    args = ["run", "--job-dir", str(j), "--data-root", str(root), "--budget-frac", "0.25", "--pool-split", "all",
            "--ref-split", "all", "--profile", "multisensor", "--scoring-config", str(j / "sc.json")]
    (j / "sc.json").write_text(json.dumps(sc), encoding="utf-8")
    assert rare_cli.main(args) == 2 and "cache/rare_crops.npy" in capsys.readouterr().err
    r = build_crops(j, root, device="cpu")
    assert r["n_crops"] > 0 and r["crops_skipped"] == 0
    assert np.load(j / "cache" / "rare_crops.npy").shape == (r["n_crops"], 512)
    ms = run_rare_v24(j, root, profile="multisensor", budget_frac=0.25, pool_split="all", ref_split="all", scoring=sc)
    assert ms["B"] == base["B"] == 3 and len(ms["selected"]) == 3 and len(ms["ranking"]) == ms["eligible_n"]
    objs = read_table(ms["selection_dir"] / "rare_objects.parquet", "rare_objects")
    assert int(objs["r_sem"].notna().sum()) == r["n_crops"]
    assert json.loads((ms["selection_dir"] / "config_used.json").read_text(encoding="utf-8"))[
        "scoring_weights"]["w_sem"] == 0.2
