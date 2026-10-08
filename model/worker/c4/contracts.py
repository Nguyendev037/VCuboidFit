# c4/contracts.py · nguồn duy nhất của schema. Mọi stage đọc/ghi bảng qua read_table và write_table.
import json
import os
import subprocess
import time

import pandas as pd

SCHEMA_VERSION = "1.2"
CAMS = ["CAM_FRONT", "CAM_FRONT_LEFT", "CAM_FRONT_RIGHT",
        "CAM_BACK", "CAM_BACK_LEFT", "CAM_BACK_RIGHT"]

FEATURES_CACHE = dict(
    sample_token="string", cam="string", scene_token="string", split="string",
    frame_idx="int32", img_path="string", emb_row="int32", nov_knn="float32",
    det_n="int16", det_n_conf="int16", det_ent="float32", det_tmp="float32",
    unc="float32", qry_max="float32", qry_best="string",
    q_bright="float32", q_blur="float32", q_ok="bool")

FRAME_SCORES = dict(
    sample_token="string", scene_token="string", split="string", frame_idx="int32",
    best_cam="string", S_hybrid="float32", S_nov="float32", S_unc="float32",
    S_qry="float32", r_nov="float32", r_unc="float32", r_qry="float32",
    qry_best="string", q_ok="bool", emb_row_best="int32", frame_emb_row="int32",
    n_cams="int16", det_n_conf_best="int16")

SELECTED = dict(
    method="string", seed="int32", rank="int32", sample_token="string",
    scene_token="string", best_cam="string", S="float32", max_sim="float32",
    mmr_util="float32", reason="string", budget_B="int32", split="string")

GT_RARE = dict(
    sample_token="string", is_rare="bool", A_night="bool", A_rain="bool",
    B_rare_class="bool", C_crowd="bool", C_low_vis="bool", C_far="bool")

FRAMES = dict(  # kiểu "list" = cột danh sách: validate() không astype, không kiểm NaN
    sample_token="string", cam="string", sd_token="string", scene_token="string",
    scene_name="string", scene_desc="string", split="string", frame_idx="int32",
    timestamp="int64", img_path="string")

CAM_POSES = dict(  # camera -> ego; rotation = quaternion (w, x, y, z)
    sample_token="string", cam="string", translation="list", rotation="list",
    intrinsic="list")

GT_BOXES_2D = dict(  # corners = 8 cặp (u, v) chưa cắt; x1..y2 đã cắt về ảnh 1600×900
    sample_token="string", cam="string", ann_token="string", category="string",
    x1="float32", y1="float32", x2="float32", y2="float32", corners="list",
    depth="float32", visibility="string", num_lidar_pts="int32")

BOXES_3D = dict(  # corners = 8 góc × (x, y, z), hệ ego của keyframe LIDAR_TOP
    sample_token="string", ann_token="string", category="string", corners="list")

# ---- Pipeline LiDAR (planning/04 · 01-CONTRACTS §1) ----
LIDAR_INDEX = dict(
    sample_token="string", scene_token="string", scene_name="string", split="string",
    frame_idx="int32", timestamp="int64", lidar_path="string", ego_x="float32",
    ego_y="float32", ego_yaw="float32")

LIDAR_FILTER = dict(sample_token="string", n_points="int32", keep="bool", reason="string")

GT_RARE_LIDAR = dict(  # CHỈ c4.lidar.gt ghi, CHỈ c4.lidar.eval đọc
    sample_token="string", is_rare="bool", A_env="bool", B_few="bool", Bp_medium="bool",
    C_sensor="bool", n_boxes="int32", rare_cells="string")

T1_SIGNALS = dict(sample_token="string", ent="float32", inc="float32", n_det="int32",
                  nov="float32")

LIDAR_SCORES = dict(
    sample_token="string", scene_token="string", split="string", frame_idx="int32",
    keep="bool", rar="float32", nov="float32", unc="float32", r_rar="float32",
    r_nov="float32", r_unc="float32", s="float32")

LIDAR_SELECTED = dict(
    method="string", seed="int32", rank="int32", sample_token="string", scene_token="string",
    s="float32", max_sim="float32", mmr_util="float32", reason="string", budget_B="int32")

SPEC = dict(  # tên -> (schema, khóa chính)
    features_cache=(FEATURES_CACHE, ["sample_token", "cam"]),
    frame_scores=(FRAME_SCORES, ["sample_token"]),
    selected=(SELECTED, ["method", "seed", "sample_token"]),
    gt_rare=(GT_RARE, ["sample_token"]),
    frames=(FRAMES, ["sample_token", "cam"]),
    cam_poses=(CAM_POSES, ["sample_token", "cam"]),
    gt_boxes_2d=(GT_BOXES_2D, ["sample_token", "cam", "ann_token"]),
    boxes_3d=(BOXES_3D, ["sample_token", "ann_token"]),
    lidar_index=(LIDAR_INDEX, ["sample_token"]),
    lidar_filter=(LIDAR_FILTER, ["sample_token"]),
    gt_rare_lidar=(GT_RARE_LIDAR, ["sample_token"]),
    t1_signals=(T1_SIGNALS, ["sample_token"]),
    lidar_scores=(LIDAR_SCORES, ["sample_token"]),
    lidar_selected=(LIDAR_SELECTED, ["method", "seed", "sample_token"]))


class ContractError(Exception):
    pass


def validate(df: pd.DataFrame, name: str) -> pd.DataFrame:
    schema, key = SPEC[name]
    missing = [c for c in schema if c not in df.columns]
    if missing:
        raise ContractError(f"{name}: thiếu cột {missing}")
    if df.duplicated(key).any():
        raise ContractError(f"{name}: trùng khóa {key}")
    num = [c for c, t in schema.items() if t.startswith(("float", "int"))]
    if num and df[num].isna().any().any():
        raise ContractError(f"{name}: có NaN ở cột số")
    if "cam" in schema and not df["cam"].isin(CAMS).all():
        raise ContractError(f"{name}: tên camera lạ")
    cast = {c: t for c, t in schema.items() if t != "list"}
    out = df[list(schema)].copy()
    out[list(cast)] = out[list(cast)].astype(cast)
    return out.reset_index(drop=True)


def _git_sha() -> str:
    try:
        return subprocess.run(["git", "rev-parse", "--short", "HEAD"],
                              capture_output=True, text=True, timeout=5, check=False).stdout.strip()
    except (OSError, subprocess.SubprocessError):
        return ""


def write_table(df: pd.DataFrame, path: str, name: str, **meta) -> None:
    df = validate(df, name)
    path = str(path)
    tmp = f"{path}.tmp"
    if path.endswith(".parquet"):
        df.to_parquet(tmp, index=False)
    else:
        df.to_csv(tmp, index=False, float_format="%.6f", encoding="utf-8")
    os.replace(tmp, path)  # ghi nguyên tử: không ai đọc phải file dở
    info = dict(schema_version=SCHEMA_VERSION, name=name, rows=len(df), git_sha=_git_sha(),
                created_at=time.strftime("%Y-%m-%dT%H:%M:%S"), **meta)
    with open(f"{path}.manifest.json", "w", encoding="utf-8") as f:
        json.dump(info, f, indent=2)


def read_table(path: str, name: str) -> pd.DataFrame:
    path = str(path)
    df = pd.read_parquet(path) if path.endswith(".parquet") else pd.read_csv(path)
    return validate(df, name)
