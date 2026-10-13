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

QUALITY_CV = dict(  # planning/11 · 01-CONTRACTS §2 · c4.context.quality_cv
    sample_token="string", cam="string", img_ok="bool", luma_mean="float32", v_mean="float32",
    v_p5="float32", v_p95="float32", sat_frac="float32", blob_max_frac="float32",
    blob_count="int16", tile_range="float32", veil="float32", noise_sigma="float32",
    lap_var_raw="float32", lap_var_dn="float32", sharp_ratio="float32")

CONTEXT_FRAME = dict(  # planning/11 · 01-CONTRACTS §3 · c4.context.fuse. "Float32" (nullable) cho sun_elev_deg:
    # validate() chỉ kiểm NaN ở cột "float*"/"int*" ⇒ null hợp lệ khi không biết vị trí log.
    sample_token="string", cam="string", sun_elev_deg="Float32", p_illum="string", p_glare="string",
    p_lens="string", p_weather="string", tag_illum="string", tag_glare="string", tag_lens="string",
    tag_weather="string", margin_illum="float32", margin_glare="float32", margin_lens="float32",
    margin_weather="float32", cv_flags="string", review="bool", review_reasons="string",
    context_version="string")

GT_RHCIO_FRAME = dict(  # planning/10 01-CONTRACTS §1 · CHỈ c4.rare.gt_rhcio ghi, CHỈ c4.rare.eval đọc
    sample_token="string", scene_token="string", split="string", r1_class="bool", r2_combo="bool",
    r3_behavior="bool", i_conflict="bool", h_hard="bool", c_night="bool", c_rain="bool",
    unknown="bool", is_target="bool", target_instances="string", n_vru_visible="int32")

GT_RHCIO_INSTANCE = dict(
    instance_token="string", category="string", vru_group="string", axes="string",
    n_frames_visible="int32", frames="string")

RARE_OBJECTS = dict(  # planning/11 SPEC-P05 §7.1 · c4.rare.candidates ghi, c4.rare.object_score chấm
    sample_token="string", object_id="string",
    source="string",       # cluster | pointpillars | merged
    cls_pred="string",     # pedestrian|bicycle|motorcycle|vru_unknown|other
    cx="float32", cy="float32", cz="float32",
    l="float32", w="float32", h="float32", yaw="float32",
    pts="int32", dist_m="float32",
    track_id="string",     # "" chưa track
    speed_mps="Float32",   # nullable: None khi track 1 box
    score_shape="float32", score_slice="float32",
    score_vru="float32", score_unc="float32",
    r_sem="Float32",       # nullable, chờ M3
    concept_top="string",  # "" chờ M3
    concept_score="Float32",
    s_obj="float32",
    missed_by_model="bool",
    reasons="string")

RARE_FRAMES = dict(  # planning/11 SPEC-P05 §7.2
    sample_token="string", scene_token="string",
    gate="string",         # valid | suspect | outlier
    gate_fail="string",    # "" khi valid
    ood_flag="bool",
    s_objects="float32",
    crowd="int32",
    weather_pred="string",
    s_frame="float32",
    pred_tags="string",    # ⊆ R1|R2|R3|H|C|I, "|" phân cách
    evidence="string",     # JSON
    rank="Int32",          # nullable
    selected="bool",
    explore="bool")

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
    gt_rhcio_frame=(GT_RHCIO_FRAME, ["sample_token"]),
    gt_rhcio_instance=(GT_RHCIO_INSTANCE, ["instance_token"]),
    t1_signals=(T1_SIGNALS, ["sample_token"]),
    lidar_scores=(LIDAR_SCORES, ["sample_token"]),
    lidar_selected=(LIDAR_SELECTED, ["method", "seed", "sample_token"]),
    quality_cv=(QUALITY_CV, ["sample_token", "cam"]),
    context_frame=(CONTEXT_FRAME, ["sample_token", "cam"]),
    rare_objects=(RARE_OBJECTS, ["sample_token", "object_id"]),
    rare_frames=(RARE_FRAMES, ["sample_token"]))


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
