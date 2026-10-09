"""Hồi quy cho phát hiện thẩm định Tầng 1 (judge 2026-10-08): tự resume ckpt cấu hình khác, CBGS
lệch giữa arm, bất biến S đo trên file đã ghi. CPU-only, không import torch/pcdet."""
import pickle

import pytest
import yaml

from c4.lidar.tier1 import train_seed as ts


def _cfg(path, augs):
    path.write_text(yaml.safe_dump({"DATA_CONFIG": {"DATA_AUGMENTOR": {
        "AUG_CONFIG_LIST": [{"NAME": a} for a in augs]}}}), encoding="utf-8")
    return path


def _infos(path, tokens):
    with open(path, "wb") as f:
        pickle.dump([{"token": t} for t in tokens], f)
    return path


def test_run_key_changes_with_train_set_and_settings():
    k = ts.run_key(["a", "b"], 10, 20, True)
    assert k == ts.run_key(["b", "a"], 10, 20, True)  # không phụ thuộc thứ tự
    assert k != ts.run_key(["a", "c"], 10, 20, True)  # đổi tập train ⇒ thư mục mới
    assert k != ts.run_key(["a", "b"], 1, 20, True)
    assert k != ts.run_key(["a", "b"], 10, 80, True)
    assert k != ts.run_key(["a", "b"], 10, 20, False)


def test_verify_written_rejects_foreign_tokens_and_gt_sampling(tmp_path):
    ok = _cfg(tmp_path / "ok.yaml", ["random_world_flip"])
    ts.verify_written(_infos(tmp_path / "s.pkl", ["a", "b"]), ok, {"a", "b", "c"})
    with pytest.raises(ValueError, match="ngoài"):
        ts.verify_written(_infos(tmp_path / "x.pkl", ["a", "z"]), ok, {"a", "b"})
    with pytest.raises(ValueError, match="gt_sampling"):
        ts.verify_written(_infos(tmp_path / "s2.pkl", ["a"]),
                          _cfg(tmp_path / "bad.yaml", ["gt_sampling", "random_world_flip"]),
                          {"a"})


def test_run_train_reuses_finished_run_without_calling_train(tmp_path, monkeypatch):
    out = tmp_path / "pcdet_output"
    ck = out / "exp" / "t1" / "cfg" / "pp_seed" / "seed_abc" / "ckpt"
    ck.mkdir(parents=True)
    (ck / "checkpoint_epoch_20.pth").write_bytes(b"x")
    called = []
    monkeypatch.setattr(ts.subprocess, "run", lambda *a, **k: called.append(a))
    ckpt, status, run_dir = ts.run_train(tmp_path / "pp_seed.yaml", "seed_abc", 20, 2, 0, out)
    assert status == "reused" and not called
    assert ckpt.name == "checkpoint_epoch_20.pth" and run_dir.name == "seed_abc"


def test_run_train_does_not_pick_up_other_tag_checkpoints(tmp_path, monkeypatch):
    """Ckpt của tag KHÁC (cấu hình cũ) không được coi là kết quả của lần chạy này."""
    out = tmp_path / "pcdet_output"
    old = out / "exp" / "t1" / "cfg" / "pp_seed" / "seed_old" / "ckpt"
    old.mkdir(parents=True)
    (old / "checkpoint_epoch_20.pth").write_bytes(b"x")

    class R:
        returncode = 1

    monkeypatch.setattr(ts.subprocess, "run", lambda *a, **k: R())
    ckpt, status, _ = ts.run_train(tmp_path / "pp_seed.yaml", "seed_new", 20, 2, 0, out)
    assert ckpt is None and "exit 1" in status


def test_index_infos_carry_no_labels_but_test_infos_keep_them(tmp_path):
    import pandas as pd
    infos = [dict(token=f"t{i}", lidar_path="x", gt_boxes=[1], gt_names=["car"],
                  num_lidar_pts=[3], valid_flag=[True]) for i in range(3)]
    allp = tmp_path / "infos_all_1sweeps.pkl"
    allp.write_bytes(pickle.dumps(infos))
    index = pd.DataFrame(dict(sample_token=["t0", "t1", "t2"], split=["S", "P", "T"]))
    p_seed, p_ord, p_test, seed = ts.split_infos(allp, index, 1)
    assert seed == ["t0"]
    ts.verify_index_label_free(p_ord)  # không ném lỗi
    assert all("gt_boxes" not in i for i in pickle.loads(p_ord.read_bytes()))
    assert all("gt_boxes" in i for i in pickle.loads(p_test.read_bytes()))
    assert all("gt_boxes" in i for i in pickle.loads(p_seed.read_bytes()))
    p_ord.write_bytes(pickle.dumps(infos))  # file có nhãn ⇒ phải bị chặn
    with pytest.raises(ValueError):
        ts.verify_index_label_free(p_ord)
