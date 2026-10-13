"""GT "hiếm" v2.4 theo trục RHCIO, đếm theo instance (planning/10 SPEC-P01). MODULE DUY NHẤT của engine
`rare_v24` được đọc annotation, attribute và scene.description. Kết quả chỉ `c4.rare.eval` được đọc.

Thuật toán port từ script thẩm định độc lập của hồ sơ 10 (evidence/H01/base_rates.txt, sha a34e067d…):
surprisal `u = -ln p`, ngưỡng = phân vị (1-alpha) `method="higher"` trên V, so sánh strict `>`, không tách tie.
"""
import hashlib
import json
import math
from collections import Counter, defaultdict
from dataclasses import asdict, dataclass, field

import numpy as np
import pandas as pd

from c4.contracts import validate
from c4.data.nusc import NuscTables
from c4.lidar.index import lidar_keyframes
from c4.rare.config import RareDefV24

AXES = ("r1_class", "r2_combo", "r3_behavior", "i_conflict", "h_hard", "c_night", "c_rain")


class RareDefNotFrozen(RuntimeError):
    """Chấm khi chưa có reference đóng băng."""


class RefSplitEmpty(ValueError):
    """Tập V rỗng — không fallback sang T."""


def _quant(x, q: float) -> float:
    return float(np.quantile(np.asarray(x, float), q, method="higher"))


def _yaw(q) -> float:
    w, x, y, z = q
    return math.atan2(2 * (w * z + x * y), 1 - 2 * (y * y + z * z))


def _vru_group(cat: str) -> str | None:
    if cat.startswith("human.pedestrian."):
        return "pedestrian"
    return {"vehicle.bicycle": "bicycle", "vehicle.motorcycle": "motorcycle"}.get(cat)


def instance_speed(ann: dict, ann_by_token: dict, ts: dict) -> float | None:
    """m/s từ box prev/next cùng instance (sai phân trung tâm); None nếu track chỉ 1 box."""
    prev, nxt = ann_by_token.get(ann.get("prev") or ""), ann_by_token.get(ann.get("next") or "")
    a, b = (prev or ann), (nxt or ann)
    if a is b:
        return None
    dt = (ts[b["sample_token"]] - ts[a["sample_token"]]) / 1e6
    if dt <= 0:
        return None
    return math.hypot(b["translation"][0] - a["translation"][0],
                      b["translation"][1] - a["translation"][1]) / dt


def load_boxes(t: NuscTables, tokens) -> dict[str, list[dict]]:
    """sample_token → box VRU (mọi số điểm) với dist ngang tới ego, toạ độ hệ ego, speed, attrs."""
    if not t.has_annotations:
        raise FileNotFoundError("dataset không có sample_annotation/instance — không dựng được GT")
    lid = lidar_keyframes(t)
    ts = {tok: s["timestamp"] for tok, s in t.sample.items()}
    out: dict[str, list[dict]] = {tok: [] for tok in tokens}
    for a in t.sample_annotation.values():
        tok = a["sample_token"]
        if tok not in out:
            continue
        cat = t.category[t.instance[a["instance_token"]]["category_token"]]["name"]
        grp = _vru_group(cat)
        if grp is None:
            continue
        ego = t.ego_pose[lid[tok]["ego_pose_token"]]
        dx = a["translation"][0] - ego["translation"][0]
        dy = a["translation"][1] - ego["translation"][1]
        yaw = _yaw(ego["rotation"])
        out[tok].append(dict(
            instance=a["instance_token"], cls=cat, group=grp, pts=int(a["num_lidar_pts"]),
            dist=math.hypot(dx, dy),
            x=math.cos(-yaw) * dx - math.sin(-yaw) * dy, y=math.sin(-yaw) * dx + math.cos(-yaw) * dy,
            speed=instance_speed(a, t.sample_annotation, ts),
            attrs=tuple(sorted(t.attribute[x]["name"] for x in a["attribute_tokens"]))))
    return out


def frame_context(t: NuscTables, tokens) -> dict[str, str]:
    """GT bối cảnh cấp scene từ scene.description (CHỈ dùng để chấm)."""
    out = {}
    for tok in tokens:
        d = t.scene[t.sample[tok]["scene_token"]]["description"].lower()
        out[tok] = f"night={int('night' in d)},rain={int('rain' in d)}"
    return out


@dataclass
class FrozenReference:
    cfg: dict
    n_frames: int
    edges: dict = field(default_factory=dict)        # cls → {"dist": [...], "pts": [...]}
    cell_p: dict = field(default_factory=dict)       # cell → p (frame V chứa cell / frame V)
    class_p: dict = field(default_factory=dict)      # cls → p (instance thấy được / tổng instance thấy được)
    behavior_p: dict = field(default_factory=dict)   # "z|cls|attr" → p(e|z) theo instance
    thresholds: dict = field(default_factory=dict)   # r1_class / r2_combo / r3_behavior → ngưỡng u

    def to_json(self) -> str:
        return json.dumps(asdict(self), ensure_ascii=False, sort_keys=True)

    @property
    def sha256(self) -> str:
        return hashlib.sha256(self.to_json().encode("utf-8")).hexdigest()

    @classmethod
    def from_json(cls, s: str) -> "FrozenReference":
        return cls(**json.loads(s))


def _visible(boxes: dict[str, list[dict]], cfg: RareDefV24) -> dict[str, list[dict]]:
    return {tok: [b for b in bs if b["pts"] >= cfg.min_pts] for tok, bs in boxes.items()}


def _cell(b: dict, edges: dict) -> str | None:
    e = edges.get(b["cls"])
    if e is None:
        return None
    return (f'{b["cls"]}|d{int(np.searchsorted(e["dist"], b["dist"], side="right"))}'
            f'|p{int(np.searchsorted(e["pts"], b["pts"], side="right"))}')


def _scores(vis: dict, ctx: dict, ref: FrozenReference):
    """→ (u_class, u_combo, u_behavior, unknown, per-instance u) cho mỗi frame. Chưa thấy ở V ⇒ unknown."""
    out = {}
    for tok, bs in vis.items():
        u1 = u2 = u3 = 0.0
        unknown = False
        inst_u: dict[str, dict] = defaultdict(dict)
        for b in bs:
            pc = ref.class_p.get(b["cls"])
            if pc is None:
                unknown = True
            else:
                u = -math.log(pc)
                u1 = max(u1, u)
                inst_u[b["instance"]]["r1_class"] = max(inst_u[b["instance"]].get("r1_class", 0.0), u)
            c = _cell(b, ref.edges)
            pcell = ref.cell_p.get(c) if c else None
            if pcell is None:
                unknown = True
            else:
                u = -math.log(pcell)
                u2 = max(u2, u)
                inst_u[b["instance"]]["r2_combo"] = max(inst_u[b["instance"]].get("r2_combo", 0.0), u)
            for a in b["attrs"]:
                pb = ref.behavior_p.get(f'{ctx[tok]}|{b["cls"]}|{a}')
                if pb is None:
                    unknown = True
                    continue
                u = -math.log(pb)
                u3 = max(u3, u)
                inst_u[b["instance"]]["r3_behavior"] = max(inst_u[b["instance"]].get("r3_behavior", 0.0), u)
        out[tok] = (u1, u2, u3, unknown, inst_u)
    return out


def fit_reference(boxes_V: dict[str, list[dict]], ctx_V: dict[str, str], cfg: RareDefV24) -> FrozenReference:
    """Fit trên V: cạnh tứ phân vị (dist, pts) mỗi lớp, p(cell), p(c), p(e|z), ngưỡng Q(1-alpha) từng nhãn R."""
    if not boxes_V:
        raise RefSplitEmpty("V rỗng")
    vis = _visible(boxes_V, cfg)
    n = len(vis)
    ref = FrozenReference(cfg=asdict(cfg), n_frames=n)
    inst_by_cls: dict[str, set] = defaultdict(set)
    for bs in vis.values():
        for b in bs:
            inst_by_cls[b["cls"]].add(b["instance"])
    denom = sum(len(s) for s in inst_by_cls.values())
    ref.class_p = {c: len(s) / denom for c, s in sorted(inst_by_cls.items())} if denom else {}
    for c in sorted(inst_by_cls):
        rows = [b for bs in vis.values() for b in bs if b["cls"] == c]
        ref.edges[c] = {k: sorted({_quant([b[k] for b in rows], q) for q in (.25, .5, .75)})
                        for k in ("dist", "pts")}
    cf = Counter(c for bs in vis.values() for c in {_cell(b, ref.edges) for b in bs})
    ref.cell_p = {c: k / n for c, k in sorted(cf.items())}
    ev: dict[str, set] = defaultdict(set)
    ctx_inst: dict[str, set] = defaultdict(set)
    for tok, bs in vis.items():
        for b in bs:
            ctx_inst[ctx_V[tok]].add(b["instance"])
            for a in b["attrs"]:
                ev[f'{ctx_V[tok]}|{b["cls"]}|{a}'].add(b["instance"])
    ref.behavior_p = {k: len(s) / len(ctx_inst[k.split("|", 1)[0]]) for k, s in sorted(ev.items())}
    sc = _scores(vis, ctx_V, ref)
    q = 1 - cfg.alpha
    for i, name in enumerate(("r1_class", "r2_combo", "r3_behavior")):
        ref.thresholds[name] = _quant([v[i] for v in sc.values()], q)
    return ref


def label_gt(t: NuscTables, tokens, ref: FrozenReference | None, cfg: RareDefV24,
             split: dict[str, str] | None = None) -> tuple[pd.DataFrame, pd.DataFrame]:
    """→ (gt_rhcio_frame, gt_rhcio_instance) cho `tokens`. Ngưỡng strict `>` theo `ref` (fit trên V)."""
    if ref is None:
        raise RareDefNotFrozen("chưa có reference đóng băng (fit_reference trên V)")
    tokens = list(tokens)
    boxes = load_boxes(t, tokens)
    ctx = frame_context(t, tokens)
    vis = _visible(boxes, cfg)
    sc = _scores(vis, ctx, ref)
    thr = ref.thresholds
    rows, inst_axes, inst_frames, inst_cat = [], defaultdict(set), defaultdict(set), {}
    for tok in tokens:
        u1, u2, u3, unknown, inst_u = sc[tok]
        bs = vis[tok]
        lab = dict(r1_class=u1 > thr["r1_class"], r2_combo=u2 > thr["r2_combo"],
                   r3_behavior=u3 > thr["r3_behavior"])
        movers = [b for b in bs if b["speed"] is not None and b["speed"] >= cfg.v_min
                  and 0 < b["x"] <= cfg.corridor_x_max and abs(b["y"]) <= cfg.corridor_y_abs]
        lab["i_conflict"] = bool(movers)
        lab["h_hard"] = any(b["dist"] > cfg.hard_far_m or b["pts"] < cfg.hard_few_pts for b in bs)
        lab["c_night"] = ctx[tok].startswith("night=1")
        lab["c_rain"] = ctx[tok].endswith("rain=1")
        target = sorted(i for i, u in inst_u.items() if u.get("r2_combo", 0.0) > thr["r2_combo"])
        for b in bs:
            inst_frames[b["instance"]].add(tok)
            inst_cat[b["instance"]] = (b["cls"], b["group"])
            for name in ("r1_class", "r2_combo", "r3_behavior"):
                if inst_u[b["instance"]].get(name, 0.0) > thr[name]:
                    inst_axes[b["instance"]].add(name)
        for b in movers:
            inst_axes[b["instance"]].add("i_conflict")
        s = t.sample[tok]
        rows.append(dict(sample_token=tok, scene_token=s["scene_token"],
                         split=(split or {}).get(tok, "pool"), **lab, unknown=unknown,
                         is_target=lab["r2_combo"], target_instances="|".join(target),
                         n_vru_visible=len(bs)))
    frame = validate(pd.DataFrame(rows), "gt_rhcio_frame")
    inst = pd.DataFrame([dict(instance_token=i, category=inst_cat[i][0], vru_group=inst_cat[i][1],
                              axes="|".join(sorted(inst_axes[i])), n_frames_visible=len(fr),
                              frames="|".join(sorted(fr)))
                         for i, fr in sorted(inst_frames.items())],
                        columns=["instance_token", "category", "vru_group", "axes",
                                 "n_frames_visible", "frames"])
    return frame, validate(inst, "gt_rhcio_instance")


def base_rates(frame: pd.DataFrame) -> dict:
    """Base rate + số scene có nhãn, mỗi trục (kiểm cap/support — SPEC-P01 §4)."""
    out = {}
    for ax in AXES:
        hit = frame[frame[ax]]
        out[ax] = dict(hit=int(len(hit)), n=int(len(frame)), rate=float(len(hit) / max(len(frame), 1)),
                       scenes=int(hit["scene_token"].nunique()))
    return out
