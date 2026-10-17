"""Chặn đọc nhãn trong selector; fixture giả không cần model/GPU."""
import builtins
import io
import json
from pathlib import Path
import sys
import types

import numpy as np
import pandas as pd
import pytest

from c4.bench import ours


def install_guard(monkeypatch):
    original = builtins.open
    original_io = io.open

    def checked(opener):
        def guarded(path, *args, **kwargs):
            text = str(path).replace("\\", "/")
            if any(p in text for p in ("/gt/", "/bench/judge/", "sample_annotation.json", "instance.json")):
                raise AssertionError("label leakage: " + text)
            return opener(path, *args, **kwargs)
        return guarded

    monkeypatch.setattr(builtins, "open", checked(original))
    monkeypatch.setattr(io, "open", checked(original_io))
    original_import = builtins.__import__

    def guarded_import(name, *args, **kwargs):
        if name in {"c4.rare.gt_rhcio", "c4.lidar.gt", "c4.gt"}:
            raise AssertionError("label import: " + name)
        return original_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", guarded_import)


@pytest.mark.parametrize("path", ["gt/x.parquet", "bench/judge/x.parquet",
                                  "sample_annotation.json", "instance.json"])
def test_guard_catches_bad_selector(tmp_path, monkeypatch, path):
    install_guard(monkeypatch)
    with pytest.raises(AssertionError, match="label leakage"):
        (tmp_path / path).read_text()


def test_ours_wrapper_no_label_reads(tmp_path, monkeypatch):
    config = tmp_path / "final_config.json"
    config.write_text(json.dumps(dict(engine="rare_v24", candidate_frame="ego", quota_m="even")))
    monkeypatch.setattr(ours, "FROZEN_SHA", ours.sha256(config))

    def run(job, root, **kwargs):
        assert kwargs["pool_split"] == "T" and kwargs["ref_split"] == "V"
        assert kwargs["scoring"] == {"quota_m": "even"}
        used = tmp_path / "config_used.json"
        used.write_text("{}")
        return dict(ranking=["pool"], selection_dir=tmp_path)

    monkeypatch.setitem(sys.modules, "c4.rare.pipeline", types.SimpleNamespace(run_rare_v24=run))
    install_guard(monkeypatch)
    for method in ("OURS", "M2"):
        result = ours.select_ours(method, tmp_path, tmp_path, config, ["pool"])
        assert result["tokens"] == ["pool"]


def test_wrapper_propagates_leak_detection(tmp_path, monkeypatch):
    config = tmp_path / "final_config.json"
    config.write_text(json.dumps(dict(engine="rare_v24", candidate_frame="ego", quota_m="even")))
    monkeypatch.setattr(ours, "FROZEN_SHA", ours.sha256(config))

    def bad(*args, **kwargs):
        return (tmp_path / "gt/secret.parquet").read_bytes()

    monkeypatch.setitem(sys.modules, "c4.rare.pipeline", types.SimpleNamespace(run_rare_v24=bad))
    install_guard(monkeypatch)
    with pytest.raises(AssertionError, match="label leakage"):
        ours.select_ours("OURS", tmp_path, tmp_path, config, ["pool"])


def test_m1_isolates_pool_and_does_not_modify_original_index(tmp_path, monkeypatch):
    config = tmp_path / "final_config.json"
    config.write_text(json.dumps(dict(engine="rare_v24", candidate_frame="ego", quota_m="even")))
    monkeypatch.setattr(ours, "FROZEN_SHA", ours.sha256(config))
    lidar = tmp_path / "lidar"
    lidar.mkdir()
    np.save(lidar / "z0.npy", np.array([[1.0], [2.0], [3.0]]))
    (lidar / "filter.parquet").touch()
    index = pd.DataFrame(dict(sample_token=["cal", "pool", "eval"]))
    filt = index.assign(keep=True)
    saved = {}

    def read(path, name):
        if name == "lidar_index":
            return index.copy()
        if name == "lidar_filter":
            return filt.copy()
        return pd.DataFrame(dict(method=["hybrid"], rank=[1], sample_token=["pool"]))

    def write(df, path, name):
        saved[name] = df.copy()

    def run(job, params):
        assert not (job / "gt").exists()
        assert params.tier == 0 and params.budget == 0.10
        assert saved["lidar_index"].sample_token.tolist() == ["pool"]
        np.testing.assert_array_equal(np.load(job / "lidar/z0.npy"), [[2.0]])
        return dict(selectionId="fake", params=dict(tier=0), warnings=[])

    monkeypatch.setattr(ours, "read_table", read)
    monkeypatch.setattr(ours, "write_table", write)
    monkeypatch.setitem(sys.modules, "c4.lidar.pipeline",
                        types.SimpleNamespace(run_selection_lidar=run))
    install_guard(monkeypatch)
    assert ours.select_ours("M1", tmp_path, tmp_path, config, ["pool"])["tokens"] == ["pool"]
    assert index.sample_token.tolist() == ["cal", "pool", "eval"]
