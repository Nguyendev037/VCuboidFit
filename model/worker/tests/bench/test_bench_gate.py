"""Cổng thứ tự và hash đúng byte, không gọi model thật."""
import hashlib
import json
from argparse import Namespace
from types import SimpleNamespace

import pandas as pd
import pytest

from c4.bench.gate import (
    BenchGateError, check_prereg, freeze_selections, open_once, sha256,
)
from c4.cli.bench_judge import main


def frozen_job(tmp_path):
    bench = tmp_path / "bench"
    (bench / "judge").mkdir(parents=True)
    (bench / "bench_split.parquet").write_bytes(b"frozen split")
    (bench / "prereg.txt").write_bytes(b"preregistered\n")
    digest = sha256(bench / "prereg.txt")
    (bench / "prereg_sha256.txt").write_text(digest)
    sels = dict(schema="bench-selections/1", dataset="pandaset", B=1, n_pool=10,
                prereg_sha256=digest, split_sha256=sha256(bench / "bench_split.parquet"),
                repo_sha="abc", created_at="2026-10-17T00:00:00Z", methods={})
    return bench, sels


def test_prereg_one_byte(tmp_path):
    bench, sels = frozen_job(tmp_path)
    check_prereg(tmp_path, sels["prereg_sha256"])
    with (bench / "prereg.txt").open("ab") as f:
        f.write(b" ")
    with pytest.raises(BenchGateError, match="PREREG_MISMATCH"):
        check_prereg(tmp_path, sels["prereg_sha256"])


def test_freeze_exact_bytes_and_no_overwrite(tmp_path):
    bench, sels = frozen_job(tmp_path)
    digest = freeze_selections(tmp_path, sels)
    expected = json.dumps(sels, sort_keys=True, indent=1, ensure_ascii=False).encode()
    assert (bench / "selections.json").read_bytes() == expected
    assert digest == hashlib.sha256(expected).hexdigest()
    with pytest.raises(BenchGateError, match="ORDER_VIOLATION"):
        freeze_selections(tmp_path, sels)


def test_open_before_freeze_and_twice(tmp_path):
    bench, sels = frozen_job(tmp_path)
    (bench / "judge/judge_calib.json").write_text("{}")
    with pytest.raises(BenchGateError, match="ORDER_VIOLATION"):
        open_once(tmp_path, "pool")
    freeze_selections(tmp_path, sels)
    marker = open_once(tmp_path, "pool")
    assert marker == json.loads((bench / "pool_opened.json").read_text())
    assert {"created_at", "repo_sha"} <= marker.keys()
    with pytest.raises(BenchGateError, match="ALREADY_OPENED"):
        open_once(tmp_path, "pool")


def test_cli_pool_before_selection(tmp_path, capsys):
    assert main(["judge", "--split", "pool", "--job-dir", str(tmp_path)]) == 3
    result = json.loads(capsys.readouterr().out)
    assert result["error"] == "ORDER_VIOLATION"
    assert not (tmp_path / "bench/pool_opened.json").exists()


def test_selection_tampering_blocks_open(tmp_path):
    bench, sels = frozen_job(tmp_path)
    freeze_selections(tmp_path, sels)
    (bench / "judge/judge_calib.json").write_text("{}")
    with (bench / "selections.json").open("ab") as f:
        f.write(b" ")
    with pytest.raises(BenchGateError, match="ORDER_VIOLATION"):
        open_once(tmp_path, "pool")


def test_freeze_after_judge_rejected(tmp_path):
    bench, sels = frozen_job(tmp_path)
    (bench / "judge/judge_struggle_JA_pool.parquet").touch()
    with pytest.raises(BenchGateError, match="ORDER_VIOLATION"):
        freeze_selections(tmp_path, sels)


def test_marker_written_before_predictor(tmp_path, monkeypatch):
    import c4.cli.bench_judge as cli

    bench, sels = frozen_job(tmp_path)
    freeze_selections(tmp_path, sels)
    (bench / "judge/judge_calib.json").write_text('{"JA": {"tau": 0.5}}')
    (tmp_path / "index").mkdir()
    (tmp_path / "index/frames.parquet").touch()
    frames = pd.DataFrame(dict(sample_token=["pool"]))
    monkeypatch.setattr(cli, "read_table", lambda *a: frames)
    monkeypatch.setattr(cli, "_frames", lambda *a: frames)
    monkeypatch.setattr(cli, "_objects", lambda *a: frames)

    def run(*args, **kwargs):
        assert (bench / "pool_opened.json").is_file()
        raise FileNotFoundError("fake predictor stops after checking marker")

    monkeypatch.setattr(cli, "_late", lambda name: SimpleNamespace(run_judge=run))
    args = Namespace(job_dir=tmp_path, split="pool", judges="JA", device="cpu", batch=1,
                     exploratory=False)
    with pytest.raises(FileNotFoundError, match="fake predictor"):
        cli._judge(args)
    assert (bench / "pool_opened.json").is_file()
