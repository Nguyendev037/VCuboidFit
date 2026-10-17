"""Test judge_bench_review_core.py — công thức độc lập.

Bộ đo chính: dựng fixture tổng hợp (8 scene, 100 lô random + mọi bên bắt buộc),
sinh `report_judge.json` bằng `c4.bench.metrics.bench_report`, rồi bắt core tính
lại và khớp từng số với dung sai 1e-9. Sửa một số trong report ⇒ phải `ok=False`.
Bộ đo này ĐỎ nếu core quay lại đếm scene lặp một lần (CI sẽ khác report).
"""
from __future__ import annotations

import importlib.util
import json
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

_CORE_PATH = Path(__file__).resolve().parents[3] / "notebooks" / "judge_bench_review_core.py"

SEED = 20261017
N_BOOT = 400


def _load_core():
    spec = importlib.util.spec_from_file_location("judge_bench_review_core", _CORE_PATH)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


# ── Fixture tổng hợp ─────────────────────────────────────────────────────────

@pytest.fixture(scope="module")
def fixture():
    from c4.bench.metrics import bench_report
    from c4.rare.eval import budget

    rng = np.random.default_rng(11)
    n_scenes, frames_per_scene = 8, 12

    rows = []
    for s in range(n_scenes):
        scene = f"sc{s:02d}"
        for f in range(frames_per_scene):
            rows.append({"sample_token": f"{scene}_f{f:02d}", "scene_token": scene})
    pool_frames = pd.DataFrame(rows)
    by_scene = {scene: group.sample_token.tolist()
                for scene, group in pool_frames.groupby("scene_token", sort=True)}

    instances = [(f"inst{s:02d}_{k}", f"sc{s:02d}")
                 for s in range(n_scenes) for k in range(3)]

    def struggle_table(offset: int) -> pd.DataFrame:
        table = []
        for inst, scene in instances:
            frames = by_scene[scene]
            picked = set(frames[offset:offset + 3])
            for token in frames:
                table.append({
                    "judge": "JA" if offset == 0 else "JB",
                    "sample_token": token,
                    "ann_token": f"ann_{inst}",
                    "instance_token": inst,
                    "scene_token": scene,
                    "group": "vru",
                    "best_iou": 0.1,
                    "best_score": 0.2,
                    "struggle": token in picked,
                    "unc": float(rng.uniform(0.0, 1.0)),
                })
        return pd.DataFrame(table)

    st = {"JA": struggle_table(0), "JB": struggle_table(4)}
    objs = pd.DataFrame([
        {"sample_token": by_scene[scene][0], "cam": "CAM_FRONT", "ann_token": f"ann_{inst}",
         "instance_token": inst, "scene_token": scene, "category": "human.pedestrian.adult",
         "group": "vru", "x1": 10.0, "y1": 10.0, "x2": 30.0, "y2": 50.0,
         "dist_m": 10.0, "in_corridor": False, "num_lidar_pts": 5}
        for inst, scene in instances
    ])

    pool = pool_frames.sample_token.tolist()
    bmax = budget(len(pool), 0.10)
    b = budget(len(pool), 0.05)

    def pick(size: int, source: list[str] | None = None) -> list[str]:
        values = rng.choice(source or pool, size=size, replace=False)
        return [str(value) for value in values]

    near = [token for token in pool if token.rsplit("_f", 1)[1] in {"00", "01", "02"}]
    methods = {name: {"tokens": pick(bmax)}
               for name in ("OURS", "M1", "M2", "X1", "X2", "X3", "N1", "N2")}
    methods["OURS"] = {"tokens": pick(bmax, near)}
    methods["X0"] = {"seeds": {str(i): pick(bmax) for i in range(100)}}

    sels = {
        "schema": "bench-selections/1",
        "dataset": "av2",
        "prereg_sha256": "a" * 64,
        "split_sha256": "b" * 64,
        "repo_sha": "deadbee",
        "B": b,
        "n_pool": len(pool),
        "methods": methods,
        "judges": {"JA": {"validity": {"ok": True}}, "JB": {"validity": {"ok": True}}},
    }
    report = bench_report(sels, st, objs, pool_frames, n_boot=N_BOOT, seed=SEED)
    return {
        "pool_frames": pool_frames,
        "st": st,
        "report": report,
        "selections": sels,
        "b": b,
    }


def _write(tmp_path: Path, name: str, payload: dict) -> Path:
    path = tmp_path / name
    path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
    return path


# ── Bootstrap: khớp từng bit với c4 ─────────────────────────────────────────

def test_bootstrap_matches_c4_bit_for_bit(fixture):
    core = _load_core()
    from c4.bench.metrics import struggle_frames
    from c4.rare.eval import bootstrap_fixed

    fixed = {name: fixture["selections"]["methods"][name]["tokens"]
             for name in ("OURS", "X1", "N1")}
    tf = struggle_frames(fixture["st"]["JA"])

    expected = bootstrap_fixed(fixed, fixture["pool_frames"], tf, n_boot=300, seed=SEED)
    got = core.bootstrap_fixed_independent(
        fixed, fixture["pool_frames"], tf, n_boot=300, seed=SEED)

    pd.testing.assert_frame_equal(got, expected[list(fixed)], check_exact=True)


def test_bootstrap_repeats_scene_cluster(fixture):
    """Hai lượt rút khác nhau phải cho SY khác nhau (scene lặp được đếm lặp)."""
    core = _load_core()
    from c4.bench.metrics import struggle_frames

    tf = struggle_frames(fixture["st"]["JA"])
    boot = core.bootstrap_fixed_independent(
        {"OURS": fixture["selections"]["methods"]["OURS"]["tokens"]},
        fixture["pool_frames"], tf, n_boot=50, seed=SEED)
    assert boot["OURS"].nunique() > 1


def test_tf_rejects_instance_spanning_scenes():
    core = _load_core()
    bad = pd.DataFrame([
        {"instance_token": "i1", "sample_token": "f1", "scene_token": "s1", "struggle": True},
        {"instance_token": "i1", "sample_token": "f2", "scene_token": "s2", "struggle": True},
    ])
    with pytest.raises(ValueError):
        core.tf_from_struggle(bad)


# ── verify_against_report: xanh trên report thật, đỏ khi sửa số ─────────────

def test_verify_against_report_ok(fixture, tmp_path):
    core = _load_core()
    report_path = _write(tmp_path, "report_judge.json", fixture["report"])
    selections_path = _write(tmp_path, "selections.json", fixture["selections"])

    result = core.verify_against_report(
        report_path, selections_path, fixture["st"]["JA"], fixture["st"]["JB"],
        fixture["pool_frames"], n_boot=N_BOOT, seed=SEED, tol=1e-9)

    assert result["ok"] is True, result["mismatches"][:20]


def test_verify_detects_tampered_numbers(fixture, tmp_path):
    core = _load_core()
    report = json.loads(json.dumps(fixture["report"]))
    report["methods"]["OURS"]["SY_JA"] = float(report["methods"]["OURS"]["SY_JA"]) + 1e-6
    report["contrasts"][0]["lo"] = float(report["contrasts"][0]["lo"]) + 1e-6
    report["verdict"]["win"] = not bool(report["verdict"]["win"])

    report_path = _write(tmp_path, "report_judge_bad.json", report)
    selections_path = _write(tmp_path, "selections.json", fixture["selections"])

    result = core.verify_against_report(
        report_path, selections_path, fixture["st"]["JA"], fixture["st"]["JB"],
        fixture["pool_frames"], n_boot=N_BOOT, seed=SEED, tol=1e-9)

    assert result["ok"] is False
    assert "methods.OURS.SY_JA" in result["mismatches"]
    assert any(key.startswith("contrasts[") and key.endswith(".lo")
               for key in result["mismatches"])
    assert "verdict.win" in result["mismatches"]


# ── Luật thắng ──────────────────────────────────────────────────────────────

def _secondary(delta: float = 0.1, p_holm: float = 0.01) -> list[dict]:
    return [{"a": "OURS", "b": name, "delta": delta, "p_holm": p_holm}
            for name in ("X0", "N1", "N2")]


def test_verdict_win_rule():
    core = _load_core()
    primary = {"JA": {"lo": 0.01}, "JB": {"lo": 0.02}}
    secondary = {"JA": _secondary(), "JB": _secondary()}

    assert core.verdict(primary, secondary, "confirmatory", ["JA", "JB"])["win"] is True
    assert core.verdict(primary, secondary, "preliminary", ["JA", "JB"])["win"] is False
    assert core.verdict(primary, secondary, "confirmatory", ["JA"])["win"] is False
    assert core.verdict({"JA": {"lo": 0.0}, "JB": {"lo": 0.02}},
                        secondary, "confirmatory", ["JA", "JB"])["win"] is False
    weak = {"JA": _secondary(p_holm=0.5), "JB": _secondary()}
    assert core.verdict(primary, weak, "confirmatory", ["JA", "JB"])["win"] is False


# ── Holm, SHA ───────────────────────────────────────────────────────────────

def test_holm_correction_monotone():
    core = _load_core()
    p_values = [0.001, 0.02, 0.04, 0.10, 0.50]
    adjusted = core.holm_correction(p_values)

    assert len(adjusted) == len(p_values)
    assert all(0.0 <= value <= 1.0 for value in adjusted)
    order = sorted(range(len(p_values)), key=p_values.__getitem__)
    sorted_adjusted = [adjusted[i] for i in order]
    for i in range(len(sorted_adjusted) - 1):
        assert sorted_adjusted[i] <= sorted_adjusted[i + 1] + 1e-12


def test_sha256_file(tmp_path):
    core = _load_core()
    path = tmp_path / "test.txt"
    path.write_bytes(b"hello world")
    digest = core.sha256_file(path)
    assert len(digest) == 64
    assert all(char in "0123456789abcdef" for char in digest)
