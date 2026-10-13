"""M8a: prereg fail closed and end-to-end miniature benchmark without torch."""

import copy
import json

from PIL import Image

from c4.cli import bench_pitch, lidar_index, lidar_t0
from c4.lidar import load_lidar_config
from tests.fixtures.make_nuscenes import make_nuscenes


def test_hash_mismatch_exits_3_before_job_read(tmp_path, monkeypatch, capsys):
    spec = tmp_path / "spec.md"
    spec.write_text("```prereg\nid: changed\n```\n", encoding="utf-8")
    monkeypatch.setattr(bench_pitch, "SPEC", spec)
    assert (
        bench_pitch.main(
            [
                "--job-dir",
                str(tmp_path / "absent"),
                "--mode",
                "mini",
                "--out",
                str(tmp_path / "out"),
            ]
        )
        == 3
    )
    assert "PREREG_HASH_MISMATCH" in capsys.readouterr().err
    assert not (tmp_path / "out").exists()


def test_mini_fixture_writes_all_methods_and_figures(tmp_path, monkeypatch):
    cfg = copy.deepcopy(load_lidar_config())
    cfg["filter"]["min_points"] = 50
    monkeypatch.setattr(lidar_t0, "load_lidar_config", lambda: cfg)
    blobs = {
        (s, i): [("human.pedestrian.adult", (8.0 + i, 2.0 * s, 0.0), 150)]
        for s in range(2)
        for i in range(6)
    }
    root = make_nuscenes(tmp_path, n_scenes=2, frames_per_scene=6, rare_frames=blobs)
    job, out = tmp_path / "job", tmp_path / "out"
    assert lidar_index.main(["--data-root", str(root), "--job-dir", str(job)]) == 0
    assert lidar_t0.main(["--data-root", str(root), "--job-dir", str(job)]) == 0
    original = bench_pitch.run_rare_v24

    def small_fixture(*args, **kwargs):
        return original(*args, **kwargs, scoring={"min_ref_vru": 0})

    monkeypatch.setattr(bench_pitch, "run_rare_v24", small_fixture)
    assert (
        bench_pitch.main(
            ["--job-dir", str(job), "--data-root", str(root), "--mode", "mini", "--out", str(out)]
        )
        == 0
    )
    rep = json.loads((out / "report_pitch.json").read_text(encoding="utf-8"))
    assert set(rep["methods"]) == {"M0", "M1", "M2", "M3"} and "oracle" in rep
    assert rep["methods"]["M3"]["status"] == "chưa đo"
    assert rep["capture_primary"] == "rare_form" and rep["bootstrap"]["n_boot"] == 1000
    assert rep["B"] == 1 and rep["mode"] == "mini"
    assert {r["frac"] for r in rep["curve"]} == {0.01, 0.02, 0.05, 0.1}
    assert "IY@B (A)" in (out / "bench_table.md").read_text(encoding="utf-8")
    for name in ("fig_iy_budget.png", "fig_context.png", "fig_examples.png"):
        with Image.open(out / name) as img:
            assert img.size == (1600, 900)
