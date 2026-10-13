"""H15 · P1 sửa hệ toạ độ (box cảm biến LIDAR_TOP -> ego, kèm cache hiệu chuẩn) + P2 quota "even"
(planning/11 §1, SPEC-P05 §3.1/§6.2)."""
import json
import math

import numpy as np
import pandas as pd

from c4.lidar import load_lidar_config
from c4.rare import candidates as cand_mod
from c4.rare.calib import lidar_to_ego
from c4.rare.candidates import cluster_candidates
from c4.rare.select import select_rare

_HEUR = {"vru_unknown": {"max_l": 3.0, "max_w": 2.0, "min_h": 0.4, "max_h": 2.5}}
_T = [1.0, 0.0, 2.0]
_HALF = math.sqrt(0.5)
_ROT = [_HALF, 0.0, 0.0, _HALF]  # quaternion yaw +90° quanh z
_ROT_NEG = [_HALF, 0.0, 0.0, -_HALF]  # quaternion yaw -90° quanh z


def _cloud(center):
    """Lưới đối xứng quanh `center` (min+max)/2 == center chính xác; dài theo trục x để PCA yaw xác định mod π."""
    grid = np.array([[x, y, z] for x in (-0.24, 0.0, 0.24) for y in (-0.06, 0.0, 0.06) for z in (-0.24, 0.0, 0.24)])
    p = grid + np.asarray(center, np.float64)
    return np.hstack([p, np.zeros((len(p), 2))]).astype(np.float32)


def _rect_cloud(length: float = 4.0, width: float = 1.0, spin: float = 0.0) -> np.ndarray:
    """Lưới dày trong chữ nhật `length` × `width` quanh gốc HỆ CẢM BIẾN, quay `spin` quanh z."""
    xs, ys = np.linspace(-length / 2, length / 2, 9), np.linspace(-width / 2, width / 2, 5)
    g = np.array([[x, y, 0.0] for x in xs for y in ys])
    c, s = math.cos(spin), math.sin(spin)
    g[:, :2] = g[:, :2] @ np.array([[c, s], [-s, c]])
    return np.hstack([g, np.zeros((len(g), 2))]).astype(np.float32)


def _fake_dataset(root, tokens=("t0",), rot=None):
    """v1.0-x tối thiểu: sensor/calibrated_sensor/sample_data cho keyframe LIDAR_TOP."""
    vdir = root / "v1.0-x"
    vdir.mkdir()
    (vdir / "sensor.json").write_text(json.dumps([{"token": "s", "channel": "LIDAR_TOP"}]), encoding="utf-8")
    (vdir / "calibrated_sensor.json").write_text(json.dumps(
        [{"token": "c", "sensor_token": "s", "translation": _T, "rotation": rot or _ROT}]), encoding="utf-8")
    (vdir / "sample_data.json").write_text(json.dumps(
        [{"token": f"d{i}", "sample_token": t, "calibrated_sensor_token": "c", "is_key_frame": True}
         for i, t in enumerate(tokens)]), encoding="utf-8")


def test_cluster_candidates_moves_sensor_box_to_ego(monkeypatch, tmp_path):
    """Cache `lidar_calib.parquet` ghi/đọc đúng; box dựng ở HỆ CẢM BIẾN + hiệu chuẩn giả (yaw +90°, t=[1,0,2])
    => tâm box sau `cluster_candidates` ở HỆ EGO đúng (sai số < 1e-5), yaw lệch đúng dyaw (mod π)."""
    _fake_dataset(tmp_path, ("t0",))
    cache = tmp_path / "cache" / "lidar_calib.parquet"
    calib = lidar_to_ego(tmp_path, ["t0"], cache)
    assert cache.is_file() and set(calib) == {"t0"}
    cfg = load_lidar_config()
    c_sensor = np.array([5.0, 3.0, 0.5])
    monkeypatch.setattr(cand_mod, "load_pcd", lambda _: _cloud(c_sensor))
    monkeypatch.setattr(cand_mod, "preprocess", lambda p, c: (p, p))
    monkeypatch.setattr(cand_mod, "ground_plane", lambda v, c: None)
    out = cluster_candidates("fake.bin", cfg, dict(ego_x=0.0, ego_y=0.0, ego_yaw=0.0), _HEUR, calib["t0"])
    assert len(out) == 1
    R = np.array([[0.0, -1.0, 0.0], [1.0, 0.0, 0.0], [0.0, 0.0, 1.0]])
    exp = R @ c_sensor + np.asarray(_T)
    assert abs(out[0]["cx"] - exp[0]) < 1e-5
    assert abs(out[0]["cy"] - exp[1]) < 1e-5
    assert abs(out[0]["cz"] - exp[2]) < 1e-5
    dyaw = math.atan2(R[1, 0], R[0, 0])
    assert abs((out[0]["yaw"] - dyaw + math.pi / 2) % math.pi - math.pi / 2) < 1e-5  # yaw trục chính: mod π


def _one_cluster(monkeypatch, root, cloud, rot):
    """Dựng dataset giả + ghim point cloud, trả về ứng viên cụm duy nhất (hệ EGO)."""
    root.mkdir()
    _fake_dataset(root, ("t0",), rot)
    calib = lidar_to_ego(root, ["t0"], root / "cache" / "lidar_calib.parquet")
    monkeypatch.setattr(cand_mod, "load_pcd", lambda _: cloud)
    monkeypatch.setattr(cand_mod, "preprocess", lambda p, c: (p, p))
    monkeypatch.setattr(cand_mod, "ground_plane", lambda v, c: None)
    out = cluster_candidates("fake.bin", load_lidar_config(), dict(ego_x=0.0, ego_y=0.0, ego_yaw=0.0), _HEUR,
                             calib["t0"])
    assert len(out) == 1
    return out[0]


def test_cluster_candidates_measures_l_w_in_ego(monkeypatch, tmp_path):
    """F1 (H25): cụm dài `l`=4 dọc trục x-sensor, rộng `w`=1 + hiệu chuẩn Δyaw = -90° => `l`, `w` đo TRONG
    HỆ EGO cùng hệ với `yaw`/tâm: `l` ≈ 4 (dọc trục yaw), `w` ≈ 1, tâm mang translation, yaw quay đúng hướng
    dài của cụm (sai số < 1e-3). Phải đúng cả khi cụm xoay trong hệ cảm biến (tight box theo VẬT, không theo
    trục cảm biến) — đó là điểm test này bắt được ở bản cũ."""
    R = np.array([[0.0, 1.0, 0.0], [-1.0, 0.0, 0.0], [0.0, 0.0, 1.0]])  # hiệu chuẩn yaw -90°
    for name, spin in (("aligned", 0.0), ("rot30", math.radians(30.0))):
        o = _one_cluster(monkeypatch, tmp_path / name, _rect_cloud(spin=spin), _ROT_NEG)
        exp = R @ np.array([math.cos(spin), math.sin(spin), 0.0])
        assert abs(o["l"] - 4.0) < 1e-3, (name, o["l"])
        assert abs(o["w"] - 1.0) < 1e-3, (name, o["w"])
        assert abs(o["cx"] - 1.0) < 1e-3 and abs(o["cy"]) < 1e-3, (name, o["cx"], o["cy"])  # tâm ở hệ EGO
        dot = math.cos(o["yaw"]) * exp[0] + math.sin(o["yaw"]) * exp[1]
        assert abs(abs(dot) - 1.0) < 1e-3, (name, o["yaw"], exp)


def test_even_quota_is_ceil_b_over_scenes():
    """`quota_m="even"` với 3 scene, B=7 => trần mỗi scene = ceil(7/3) = 3; lô chọn vẫn đúng B."""
    toks = [f"t{i}" for i in range(9)]
    index = pd.DataFrame(dict(sample_token=toks, scene_token=["s0", "s1", "s2"] * 3, frame_idx=list(range(9))))
    frames = pd.DataFrame(dict(sample_token=toks, gate=["valid"] * 9, s_frame=np.linspace(1.0, 0.1, 9)))
    empty = pd.DataFrame(columns=["sample_token", "track_id", "s_obj"])
    out = select_rare(frames, empty, np.eye(9, 4, dtype=np.float32), index, 7,
                      {"mmr_lambda": 0.7, "quota_m": "even"})
    assert out.attrs["quota_m"] == 3 and int(out.attrs["B"]) == 7
    assert int(out["selected"].sum()) == 7
