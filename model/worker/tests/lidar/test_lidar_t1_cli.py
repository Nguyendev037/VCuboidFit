"""Plan 07 · stage CLI t1: các trường hợp skip (mã 0, không ghi file, không gọi Docker)."""
import subprocess

import pandas as pd

from c4.cli import lidar_t1
from c4.contracts import write_table


def _idx(tokens):
    n = len(tokens)
    return pd.DataFrame(dict(
        sample_token=tokens, scene_token=["s"] * n, scene_name=["scene-0"] * n, split=["val"] * n,
        frame_idx=list(range(n)), timestamp=[1000 + i for i in range(n)],
        lidar_path=["x.bin"] * n, ego_x=[0.0] * n, ego_y=[0.0] * n, ego_yaw=[0.0] * n))


def _no_docker(monkeypatch):
    real = subprocess.run

    def guard(cmd, *a, **k):
        if cmd and cmd[0] == "docker":
            raise AssertionError("không được gọi Docker khi skip")
        return real(cmd, *a, **k)
    monkeypatch.setattr(subprocess, "run", guard)


def _make_job(tmp_path, tokens):
    job = tmp_path / "job"
    (job / "lidar").mkdir(parents=True)
    write_table(_idx(tokens), str(job / "lidar" / "index.parquet"), "lidar_index")
    return job


def _run(job, tmp_path):
    return lidar_t1.main(["--job-dir", str(job), "--data-root", str(tmp_path)])


def test_t1_cli_unset_skips(tmp_path, monkeypatch, capsys):
    monkeypatch.delenv("VCF_T1_EXP", raising=False)
    _no_docker(monkeypatch)
    job = _make_job(tmp_path, ["a", "b"])
    assert _run(job, tmp_path) == 0
    assert "skip: VCF_T1_EXP chưa đặt" in capsys.readouterr().out
    assert not (job / "t1" / "signals.parquet").exists()


def test_t1_cli_missing_ckpt_skips(tmp_path, monkeypatch, capsys):
    exp = tmp_path / "exp"
    exp.mkdir()
    monkeypatch.setenv("VCF_T1_EXP", str(exp))
    _no_docker(monkeypatch)
    job = _make_job(tmp_path, ["a", "b"])
    assert _run(job, tmp_path) == 0
    assert "skip: thiếu" in capsys.readouterr().out
    assert not (job / "t1" / "signals.parquet").exists()


def test_t1_cli_not_subset_skips(tmp_path, monkeypatch, capsys):
    exp = tmp_path / "exp"
    (exp / "t1" / "cfg").mkdir(parents=True)
    (exp / "t1" / "ckpt").mkdir(parents=True)
    (exp / "t1" / "cfg" / "pp_seed.yaml").write_text("x: 1\n", encoding="utf-8")
    (exp / "t1" / "ckpt" / "seed_latest.pth").write_bytes(b"x")
    write_table(_idx(["a", "b"]), str(exp / "index.parquet"), "lidar_index")
    monkeypatch.setenv("VCF_T1_EXP", str(exp))
    _no_docker(monkeypatch)
    job = _make_job(tmp_path, ["a", "zzz"])
    assert _run(job, tmp_path) == 0
    assert "không có trong thí nghiệm seed" in capsys.readouterr().out
    assert not (job / "t1" / "signals.parquet").exists()
