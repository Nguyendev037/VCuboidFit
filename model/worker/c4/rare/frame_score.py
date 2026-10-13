"""M2b · gom vật -> frame, thẻ dự đoán RHCIO (planning/11 SPEC-P05 §6.1). Thẻ suy từ DỰ ĐOÁN, không từ GT.
Không dùng OR của các thẻ R thành `is_rare` (10/SPEC-P01 §7)."""
import json

import numpy as np
import pandas as pd

from c4.lidar.score import pct_rank
from c4.rare.config import RareDefV24
from c4.rare.object_score import PredReference, object_cells, surprisal

VRU_ALL = ("pedestrian", "bicycle", "motorcycle", "vru_unknown")
DEFAULT_FRAME_W = {"w_obj": 0.70, "w_crowd": 0.15, "w_ctx": 0.15}
NIGHT_SUN_DEG = -6.0
BAD_WEATHER = ("rain", "fog")
TAG_ORDER = ("R1", "R2", "R3", "H", "C", "I")


def _context_by_frame(context: pd.DataFrame | None) -> dict[str, tuple[str, float | None]]:
    """token -> (weather_pred, sun_elev_deg). CAM_FRONT nếu có, không thì đa số phiếu mưa/sương trên các cam."""
    if context is None or len(context) == 0:
        return {}
    out = {}
    for tok, g in context.groupby("sample_token"):
        front = g[g["cam"] == "CAM_FRONT"]
        if len(front):
            v = front["tag_weather"].iloc[0]  # <NA> = tầng context từ chối gán nhãn (biên thấp) => coi như ""
            wx = "" if pd.isna(v) else str(v)
        else:
            bad = g["tag_weather"].isin(BAD_WEATHER)
            wx = str(g.loc[bad, "tag_weather"].mode().iloc[0]) if bad.sum() * 2 > len(g) else ""
        sun = pd.to_numeric(g["sun_elev_deg"], errors="coerce").dropna()
        out[tok] = (wx if wx in BAD_WEATHER else "", float(sun.iloc[0]) if len(sun) else None)
    return out


def frame_scores(rare_objects: pd.DataFrame, gate_df: pd.DataFrame, context: pd.DataFrame | None,
                 index: pd.DataFrame, cfg: dict, ref: PredReference | None = None,
                 rare_cfg: RareDefV24 | None = None, concept_groups: dict | None = None) -> pd.DataFrame:
    """-> rare_frames (rank/selected/explore = None/False/False; select.py điền sau). Thứ tự dòng = `index`.

    `cfg`: w_obj/w_crowd/w_ctx. Không có `ref` => không sinh thẻ R1/R2; không có `rare_cfg` => không sinh R3/H/I.
    `concept_groups` (id khái niệm -> "R"|"I", chỉ profile multisensor): vật có concept_top thuộc nhóm R thêm thẻ R1, nhóm I
    thêm thẻ I (cùng luật OR với thẻ LiDAR). Frame outlier không đóng góp vật; s_frame = hạng phần trăm trên frame gate=valid."""
    w = {**DEFAULT_FRAME_W, **{k: cfg[k] for k in DEFAULT_FRAME_W if k in cfg}}
    gates = gate_df.set_index("sample_token")
    ctx = _context_by_frame(context)
    ok_obj = rare_objects[rare_objects["sample_token"].map(gates["gate"]) != "outlier"].copy()
    if ref is not None and len(ok_obj):
        ok_obj["_cell"] = object_cells(ok_obj, ref.edges_pred)
    per_frame = {t: g for t, g in ok_obj.groupby("sample_token")}
    rows = []
    for tok, scene in zip(index["sample_token"], index["scene_token"]):
        g = per_frame.get(tok)
        wx, sun = ctx.get(tok, ("", None))
        night = sun is not None and sun < NIGHT_SUN_DEG
        crowd, s_obj, ev, tags = 0, 0.0, {}, {}
        if g is not None and len(g):
            crowd = int(g["cls_pred"].isin(VRU_ALL).sum())
            top = g.loc[g["s_obj"].idxmax()]
            s_obj = float(top["s_obj"])
            ev = {"top_object": str(top["object_id"]), "s_obj_max": round(s_obj, 4), "n_vru": crowd}
            vis = g[g["cls_pred"].isin(VRU_ALL)]  # R1/R2 chỉ trên VRU (ref không chứa "other")
            if rare_cfg is not None:
                vis = vis[vis["pts"] >= rare_cfg.min_pts]
            if ref is not None and len(vis):
                u = [surprisal(ref, c, cell) for c, cell in zip(vis["cls_pred"], vis["_cell"])]
                u1, u2 = [a for a, _ in u], [b for _, b in u]
                if max(u1) > ref.thresholds["r1_class"]:
                    tags["R1"] = f"class {vis['cls_pred'].iloc[int(np.argmax(u1))]}"
                if max(u2) > ref.thresholds["r2_combo"]:
                    tags["R2"] = f"cell {vis['_cell'].iloc[int(np.argmax(u2))]}"
            if rare_cfg is not None:
                vru = g[g["cls_pred"].isin(VRU_ALL)]
                mover = vru[vru["speed_mps"].notna() & (vru["speed_mps"].astype(float) >= rare_cfg.v_min)]
                if len(mover) and (wx != "" or night):
                    tags["R3"] = f"{mover['object_id'].iloc[0]} speed={float(mover['speed_mps'].iloc[0]):.1f}"
                far = g[(g["dist_m"] > rare_cfg.hard_far_m) | (g["pts"] < rare_cfg.hard_few_pts)]
                if len(far):
                    tags["H"] = f"{far['object_id'].iloc[0]} dist={float(far['dist_m'].iloc[0]):.1f}"
                conflict = mover[(mover["cx"] > 0) & (mover["cx"] <= rare_cfg.corridor_x_max)
                                 & (mover["cy"].abs() <= rare_cfg.corridor_y_abs)]
                if len(conflict):
                    tags["I"] = f"{conflict['object_id'].iloc[0]} x={float(conflict['cx'].iloc[0]):.1f}"
        if concept_groups and g is not None and len(g):
            for oid, cid in zip(g["object_id"], g["concept_top"].fillna("")):
                grp = concept_groups.get(cid) if cid else None
                if grp == "R":
                    tags.setdefault("R1", f"concept {cid} {oid}")
                elif grp == "I":
                    tags.setdefault("I", f"concept {cid} {oid}")
        if wx != "" or night:
            tags["C"] = f"weather={wx or '-'} sun_elev={sun}"
        ev["tags_source"] = tags
        raw = (w["w_obj"] * s_obj + w["w_crowd"] * min(crowd / 5.0, 1.0)
               + w["w_ctx"] * (0.3 if (wx != "" or night) else 0.0))
        rows.append(dict(sample_token=tok, scene_token=scene, s_objects=s_obj, crowd=crowd, weather_pred=wx,
                         raw=raw, pred_tags="|".join(t for t in TAG_ORDER if t in tags),
                         evidence=json.dumps(ev, ensure_ascii=False)))
    df = pd.DataFrame(rows)
    df = df.merge(gate_df, on="sample_token", how="left")
    valid = (df["gate"] == "valid").to_numpy()
    df["s_frame"] = pct_rank(df["raw"].to_numpy(), valid)
    df["rank"] = pd.array([None] * len(df), dtype="Int32")
    df["selected"] = False
    df["explore"] = False
    return df.drop(columns="raw")
