"""select --split cal --exploratory ⇒ power.json (SPEC-P04 §4): công thức MDE, cổng thứ tự, không chạm selections.json."""
import json
import math

import numpy as np
import pandas as pd
import pytest

from c4.bench.gate import freeze_selections, sha256
import c4.cli.bench_judge as bj

SCENES = [f"s{k}" for k in range(4)]
CAL = pd.DataFrame(dict(sample_token=[f"c{k}_{i}" for k in range(4) for i in range(10)],
                        scene_token=[f"s{k}" for k in range(4) for _ in range(10)]))
POOL = pd.DataFrame(dict(sample_token=[f"p{k}" for k in range(9)],
                         scene_token=[f"q{k}" for k in range(9)]))


def struggle():
    # Mỗi scene 3 instance struggle, mỗi instance ở 1 khung riêng (c_k_0..2).
    rows = [dict(judge="JA", sample_token=f"c{k}_{i}", ann_token=f"a{k}{i}", instance_token=f"i{k}{i}",
                 scene_token=f"s{k}", group="vru", best_iou=1.0, best_score=0.0, struggle=True, unc=1.0)
            for k in range(4) for i in range(3)]
    return pd.DataFrame(rows)


def cal_sels():
    tokens = CAL.sample_token.tolist()
    rng = np.random.default_rng(0)
    methods = {m: {"tokens": list(rng.permutation(tokens)[:4])} for m in ("OURS", "M1", "M2", "X1", "X2",
                                                                         "X3", "N1", "N2")}
    methods["OURS"]["tokens"] = ["c0_0", "c1_0", "c2_1", "c3_9"]   # 3 trúng / 4
    methods["X1"]["tokens"] = ["c0_9", "c1_9", "c2_2", "c3_8"]     # 1 trúng / 4
    methods["X0"] = {"seeds": {str(s): list(np.random.default_rng(s).permutation(tokens)[:4])
                               for s in range(100)}}
    return dict(methods=methods)


def independent_mde(sels, n_boot, seed):
    """Tính lại theo SPEC-P04 §3.6, không gọi bootstrap_fixed."""
    hit = {f"c{k}_{i}" for k in range(4) for i in range(3)}
    names = sorted(SCENES)
    scene = dict(zip(CAL.sample_token, CAL.scene_token))
    b = math.ceil(0.05 * len(CAL))
    fixed = {m: e["tokens"][:b] for m, e in sels["methods"].items() if m != "X0"}

    def per_scene(sel):
        cap = np.array([sum(t in hit and scene[t] == n for t in sel) for n in names], float)
        nsel = np.array([sum(scene[t] == n for t in sel) for n in names], float)
        return cap, nsel

    arr = {m: per_scene(v) for m, v in fixed.items()}
    rng = np.random.default_rng(seed)
    d = []
    for _ in range(n_boot):
        idx = rng.integers(0, len(names), size=len(names))
        sy = {m: c[idx].sum() / max(n[idx].sum(), 1.0) for m, (c, n) in arr.items()}
        d.append(sy["OURS"] - max(sy["X1"], sy["X2"], sy["X3"]))
    return 2.8 * float(np.std(d, ddof=1)) * math.sqrt(4 / 9)


@pytest.fixture
def patched(monkeypatch):
    monkeypatch.setattr(bj, "_frames", lambda job, split: (CAL if split == "CAL" else POOL).copy())
    return monkeypatch


def test_power_matches_independent_formula(tmp_path, patched):
    sels = cal_sels()
    got = bj._power(tmp_path, sels, struggle(), CAL, n_boot=500, seed=20261017)
    assert got["B_cal"] == 2 and got["n_scenes_cal"] == 4 and got["n_scenes_pool"] == 9
    assert got["mde"] == pytest.approx(independent_mde(sels, 500, 20261017), rel=1e-12)
    assert got["mde"] == pytest.approx(2.8 * got["se_D_JA"] * math.sqrt(4 / 9))
    assert got["D_JA_cal"] == pytest.approx(got["sy_cal"]["OURS"] - max(
        got["sy_cal"][m] for m in ("X1", "X2", "X3")))
    assert got["underpowered"] is (got["mde"] > 0.5 * got["sy_x0_mean_cal"])
    assert got["label"] == "exploratory" and got["ours_in_sample"] is True


def prereg_job(tmp_path):
    bench = tmp_path / "bench"
    (bench / "judge").mkdir(parents=True)
    (bench / "bench_split.parquet").write_bytes(b"frozen split")
    (bench / "prereg.txt").write_bytes(b"preregistered\n")
    (bench / "prereg_sha256.txt").write_text(sha256(bench / "prereg.txt"))
    return bench


def test_select_cal_refused_after_pool_opened(tmp_path, patched, capsys):
    bench = prereg_job(tmp_path)
    (bench / "pool_opened.json").write_text("{}")
    assert bj.main(["select", "--split", "cal", "--exploratory", "--job-dir", str(tmp_path)]) == 3
    assert json.loads(capsys.readouterr().out)["error"] == "ORDER_VIOLATION"
    assert not (bench / "power.json").exists()


def test_select_cal_keeps_frozen_selections(tmp_path, patched, capsys):
    bench = prereg_job(tmp_path)
    frozen = dict(schema="bench-selections/1", dataset="nuscenes-pilot", B=1, n_pool=9,
                  prereg_sha256=sha256(bench / "prereg.txt"),
                  split_sha256=sha256(bench / "bench_split.parquet"), repo_sha="abc",
                  created_at="2026-10-17T00:00:00Z", methods={})
    digest = freeze_selections(tmp_path, frozen)
    (bench / "judge/judge_struggle_JA_cal.parquet").write_bytes(b"x")
    sels = cal_sels()
    calls = []
    patched.setattr(bj, "_run_methods", lambda args, job, pool, split="T": calls.append((pool, split))
                    or sels["methods"])
    patched.setattr(bj, "read_table", lambda path, name: struggle())
    patched.setenv("VCF_REPO_SHA", "94be150")
    assert bj.main(["select", "--split", "cal", "--exploratory", "--job-dir", str(tmp_path),
                    "--n-boot", "200"]) == 0
    out = json.loads(capsys.readouterr().out)
    assert out["ok"] and out["power"]["mde"] > 0
    assert calls == [(CAL.sample_token.tolist(), "V")]
    assert sha256(bench / "selections.json") == digest
    power = json.loads((bench / "power.json").read_text(encoding="utf-8"))
    assert power["repo_sha"] == "94be150" and power["n_boot"] == 200
    assert json.loads((bench / "cal/selections_cal.json").read_text(encoding="utf-8"))["label"] == "exploratory"


def test_plain_select_still_blocked_by_frozen_selections(tmp_path, patched, capsys):
    bench = prereg_job(tmp_path)
    freeze_selections(tmp_path, dict(schema="bench-selections/1", dataset="nuscenes-pilot", B=1, n_pool=9,
                                     prereg_sha256=sha256(bench / "prereg.txt"),
                                     split_sha256=sha256(bench / "bench_split.parquet"), repo_sha="abc",
                                     created_at="2026-10-17T00:00:00Z", methods={}))
    assert bj.main(["select", "--job-dir", str(tmp_path)]) == 3
    assert json.loads(capsys.readouterr().out)["error"] == "ORDER_VIOLATION"
