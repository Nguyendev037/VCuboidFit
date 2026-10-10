"""M5 — Đầu ra: bảng xếp hạng + lý do + vật thể khoanh sẵn."""
import os
from typing import List

from .utils import save_csv, save_json

GATE_LABEL = {"valid": "Hợp lệ", "suspect": "Nghi ngờ (người duyệt)", "outlier": "Ngoại lai (loại)"}


def frame_reasons(f: dict, frame_cfg) -> str:
    parts = []
    if f["rare_class_flag"]:
        parts.append("có vật lớp hiếm (bicycle/motorcycle)")
    if f["crowd_count"] >= frame_cfg.crowd_n:
        parts.append(f"đông người ({f['crowd_count']})")
    if f["night"] > 0:
        parts.append("ban đêm")
    if f["rain_score"] > 0.5:
        parts.append(f"mưa ({f['rain_score']:.2f})")
    if f["far_few_flag"]:
        parts.append("có vật xa >30 m hoặc <10 điểm")
    if f.get("ood_flag"):
        parts.append(f"cờ OOD ({f['ood_raw']:.2f}) — chỉ cảnh báo, không cộng điểm")
    if f.get("gate", "valid") != "valid":
        parts.append(f"[{GATE_LABEL[f['gate']]}: {f.get('gate_fail', '')}]")
    parts.append(f"obj_agg {f['obj_agg']:.2f}")
    return "; ".join(parts)


def object_reasons(c: dict) -> str:
    parts = []
    if c["far"]:
        parts.append(f"xa {c['dist']:.1f} m")
    if c["few"]:
        parts.append(f"ít điểm ({c['n_points']})")
    if c["confusion"]:
        parts.append("model nhầm lẫn lớp")
    if c["missed"]:
        parts.append("model bỏ sót (chỉ cluster bắt được)")
    if c["class_name"] in ("bicycle", "motorcycle"):
        parts.append(f"lớp hiếm: {c['class_name']}")
    parts.append(f"shape {c.get('s_shape_raw', 0):.2f} | unc {c.get('s_unc_raw', 0):.2f} | vru {c.get('s_vru_raw', 0):.2f} → s_obj {c.get('s_obj', 0):.3f}")
    return "; ".join(parts)


def frame_rows(ranked: List[dict], frame_cfg, limit: int = 0) -> List[dict]:
    rows = []
    for f in (ranked[:limit] if limit else ranked):
        rows.append({
            "rank": f.get("rank", ""),
            "rank_nodedup": f.get("rank_nodedup", ""),
            "fid": f["fid"], "scene": f["scene"], "t": round(f["t"], 3),
            "s_frame": round(f["s_frame"], 6),
            "rule_only": f["rule_only"],
            "mean_det_score": round(f["mean_det_score"], 4),
            "obj_agg": round(f["obj_agg"], 4),
            "crowd_count": f["crowd_count"],
            "night": f["night"], "rain_score": round(f["rain_score"], 3),
            "ood": round(f.get("ood_raw", 0.0), 4),
            "ood_flag": f.get("ood_flag", 0),
            "gate": f.get("gate", "valid"),
            "gate_fail": f.get("gate_fail", ""),
            "slice_primary": f["slice_primary"],
            "kept": f.get("kept", True),
            "selected": f.get("selected", ""),
            "explore": f.get("explore", 0),
            "reasons": frame_reasons(f, frame_cfg),
        })
    return rows


def object_rows(cands: List[dict]) -> List[dict]:
    rows = []
    for c in cands:
        rows.append({
            "fid": c["fid"], "cid": c["cid"], "source": c["source"],
            "class_name": c["class_name"] or "",
            "det_score": "" if c["det_score"] is None else round(c["det_score"], 4),
            "dist_m": round(c["dist"], 2), "n_points": c["n_points"],
            "L": round(c["L"], 2), "W": round(c["W"], 2), "H": round(c["H"], 2),
            "cx": round(c["center"][0], 2), "cy": round(c["center"][1], 2),
            "cz": round(c["center"][2], 2), "yaw": round(c["yaw"], 3),
            "s_shape_raw": round(c.get("s_shape_raw", 0.0), 5),
            "s_unc_raw": round(c.get("s_unc_raw", 0.0), 5),
            "s_slice_raw": round(c.get("s_slice_raw", 0.0), 3),
            "s_vru_raw": round(c.get("s_vru_raw", 0.0), 3),
            "s_obj": round(c.get("s_obj", 0.0), 6),
            "far": int(c["far"]), "few": int(c["few"]), "confusion": int(c["confusion"]),
            "missed_by_model": int(c["missed"]),
            "reasons": object_reasons(c),
        })
    return rows


def write_outputs(artifacts: dict, out_dir: str, frame_cfg) -> None:
    os.makedirs(out_dir, exist_ok=True)
    ranked_T = artifacts["ranked_T"]
    ranked_V = artifacts["ranked_V"]
    cands_T = [c for c in artifacts["cands"] if artifacts["frames"][c["fid"]]["split"] == "T"]

    save_csv(frame_rows(ranked_T, frame_cfg), os.path.join(out_dir, "frames_ranked_T.csv"))
    save_csv(frame_rows(ranked_V, frame_cfg), os.path.join(out_dir, "frames_ranked_V.csv"))
    save_csv(object_rows(cands_T), os.path.join(out_dir, "objects_T.csv"))
    # Danh sách riêng cho người duyệt: Nghi ngờ + Ngoại lai (KHÔNG giao gán nhãn).
    # Người xác nhận là dữ liệu thật → chuyển sang nhóm hiếm ở vòng sau.
    review = [f for f in artifacts.get("ranked_T_all", ranked_T) if f.get("gate", "valid") != "valid"]
    save_csv(frame_rows(review, frame_cfg), os.path.join(out_dir, "review_T.csv"))

    preview = [{
        "rank": f["rank"], "fid": f["fid"], "slice": f["slice_primary"],
        "s_frame": round(f["s_frame"], 4), "reasons": frame_reasons(f, frame_cfg),
    } for f in ranked_T[:10]]
    save_json({
        "counts": {
            "frames_V": sum(1 for f in artifacts["frames"].values() if f["split"] == "V"),
            "frames_T": sum(1 for f in artifacts["frames"].values() if f["split"] == "T"),
            "candidates_T": len(cands_T),
        },
        "outlier_gate": artifacts.get("gate", {}),
        "top10_preview": preview,
    }, os.path.join(out_dir, "summary.json"))
