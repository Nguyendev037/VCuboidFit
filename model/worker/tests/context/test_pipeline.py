import json
import sys

import numpy as np
import pandas as pd

from c4.cli import context as context_cli
from c4.context import pipeline
from c4.contracts import CONTEXT_FRAME, read_table, write_table
from c4.data.index import build_frames
from c4.data.nusc import NuscTables
from c4.extract.fake import fake_embed
from tests.fixtures.make_nuscenes import make_nuscenes


class _FakeEnc:
    """Chỉ có text encode + logit_scale; không có đường nào để mã hoá ảnh."""
    logit_scale = 100.0

    def encode(self, texts):
        return fake_embed(list(texts), 512, seed=7)


class _NoImageEncoder:
    def __getattr__(self, name):
        raise AssertionError(f"pipeline đã chạm c4.extract.clip.{name} (CẤM gọi encoder ảnh)")


def _manifest_warnings(job):
    return json.loads((job / "cache" / "context_frame.parquet.manifest.json").read_text())["warning_codes"]


def test_pipeline_cli_fit_run_end_to_end(tmp_path, monkeypatch):
    monkeypatch.setitem(sys.modules, "c4.extract.clip", _NoImageEncoder())
    monkeypatch.setattr(pipeline, "default_text_encoder", _FakeEnc)
    root = make_nuscenes(tmp_path)
    frames = build_frames(NuscTables.load(root), root)
    job = tmp_path / "job"
    (job / "index").mkdir(parents=True)
    write_table(frames, job / "index" / "frames.parquet", "frames")
    a = ["--job-dir", str(job)]
    run = ["run", *a, "--data-root", str(root)]
    assert context_cli.main(run) == 2  # thiếu clip_img.npy ⇒ ClipCacheMissing, không gọi encoder ảnh
    (job / "cache").mkdir(exist_ok=True)
    C = fake_embed([f"img{i}" for i in range(len(frames))], 512, seed=3)
    np.save(job / "cache" / "clip_img.npy", C.astype(np.float16))

    # chưa đóng băng: bảng hợp lệ, tag null, review False
    assert context_cli.main(run) == 0
    out = job / "cache" / "context_frame.parquet"
    df = read_table(out, "context_frame")
    assert list(df.columns) == list(CONTEXT_FRAME) and len(df) == len(frames)
    assert df["review"].dtype == bool and not df["review"].any()
    assert df[[c for c in df if c.startswith("tag_")]].isna().all(axis=None)
    assert _manifest_warnings(job) == ["CONTEXT_NOT_FROZEN"]

    # fit trên V (scene0); split T bị từ chối; chạy lại với ngưỡng đã đóng băng
    v = frames["scene_name"].eq("scene0")
    toks = frames["sample_token"].drop_duplicates()
    split = np.where(toks.isin(frames.loc[v, "sample_token"]), "V", "T")
    pd.DataFrame({"sample_token": toks, "split": split}).to_csv(job / "split_manifest.csv", index=False)
    assert context_cli.main(["fit", *a, "--split", "T", "--data-root", str(root)]) == 1
    assert context_cli.main(["fit", *a, "--split", "V", "--data-root", str(root)]) == 0
    thr = json.loads((job / "cache" / "context_thresholds_v1.json").read_text(encoding="utf-8"))
    assert thr["split"] == "V" and thr["n_frames"] == int(v.sum()) and list(thr) == sorted(thr)
    assert context_cli.main(run) == 0
    df2 = read_table(out, "context_frame")
    assert len(df2) == len(frames) and df2["review"].dtype == bool
    assert (df2["context_version"] == "ctx_v1").all() and _manifest_warnings(job) == []
