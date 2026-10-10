"""M4 — Rank, dedup, đa dạng hoá.

Sửa theo phản biện:
- Dedup giữ TOP-K (mặc định k=2) mỗi nhóm — không co hoàn toàn cảnh kéo dài.
- Tiêu chuẩn dedup: |Δt| < window HOẶC ego dịch < disp_m (bền với frame rate 20 Hz
  của data công ty, không phụ thuộc "số giây" cứng).
- Đa dạng hoá theo quota slice (không để bảng xếp hạng rơi hết vào 1 kiểu cảnh).
"""
import math
from typing import List


def rank_and_dedup(frame_dicts: List[dict], dedup_cfg, score_key: str = "s_frame") -> tuple:
    """Sắp xếp theo score → chia nhóm dedup → đánh dấu kept (top-k mỗi nhóm).

    Trả về (ranked_all, ranked_kept): ranked_all giữ thứ tự đầy đủ (dùng đo
    tác động của dedup lên recall), ranked_kept chỉ còn frame sống sót.
    """
    # Frame qua cổng ngoại lai (gate_tier 0) luôn đứng trước Nghi ngờ (1) và Ngoại lai (2)
    ranked = sorted(frame_dicts, key=lambda f: (f.get("gate_tier", 0), -f[score_key], f["fid"]))
    groups: List[List[dict]] = []          # mỗi nhóm: các frame đã gộp
    gidx: dict = {}
    for f in ranked:
        s = f["scene"]
        t = f["t"]
        ego = f["ego"]
        target = None
        for gi in gidx.get(s, []):
            # frame bám gần NHÓM nếu gần bất kỳ thành viên (dedup dạng chuỗi)
            hit = any(abs(t - m["t"]) < dedup_cfg.window_s
                      or math.hypot(ego[0] - m["ego"][0], ego[1] - m["ego"][1]) < dedup_cfg.disp_m
                      for m in groups[gi]["members"])
            if hit:
                target = gi
                break
        if target is None:
            gidx.setdefault(s, []).append(len(groups))
            groups.append({"members": [f]})
        else:
            groups[target]["members"].append(f)
    for gi, g in enumerate(groups):
        for k, m in enumerate(g["members"]):
            m["kept"] = k < dedup_cfg.keep_topk
    ranked_all = ranked
    ranked_kept = [f for f in ranked if f["kept"]]
    for i, f in enumerate(ranked_kept):
        f["rank"] = i + 1
    for i, f in enumerate(ranked_all):
        f["rank_nodedup"] = i + 1
    return ranked_all, ranked_kept


def diversify_select(ranked_kept: List[dict], budget: int, div_cfg) -> List[dict]:
    """Chọn top-B có quota theo slice: pass 1 tôn trọng cap, pass 2 lấp đầy theo rank."""
    if not div_cfg.enabled:
        return ranked_kept[:budget]
    caps = {s: int(math.ceil(q * budget)) for s, q in div_cfg.quotas.items()}
    counts = {s: 0 for s in caps}
    sel, chosen = [], set()
    for f in ranked_kept:
        if len(sel) >= budget:
            break
        s = f.get("slice_primary", "typical")
        cap = caps.get(s, budget)
        if counts.get(s, 0) < cap:
            sel.append(f)
            chosen.add(f["fid"])
            counts[s] = counts.get(s, 0) + 1
    for f in ranked_kept:
        if len(sel) >= budget:
            break
        if f["fid"] not in chosen:
            sel.append(f)
            chosen.add(f["fid"])
    return sel
