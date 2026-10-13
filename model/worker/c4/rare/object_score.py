"""M2b · tham chiếu dự đoán trên V + chấm điểm từng vật (planning/11 SPEC-P05 §5). Không đọc nhãn/GT:
tần suất "mode" fit bằng DỰ ĐOÁN (10/SPEC-P01 §5); CẤM fit trên T (caller chỉ truyền V hoặc `all` in-sample)."""
import hashlib
import json
import math
from collections import Counter, defaultdict
from dataclasses import asdict, dataclass, field

import numpy as np
import pandas as pd

from c4.lidar.score import pct_rank
from c4.lidar.uncertainty import unc_score
from c4.rare.config import RareDefV24

VRU_PRED = ("pedestrian", "bicycle", "motorcycle")
DEFAULT_WEIGHTS = {"w_shape": 0.15, "w_slice": 0.35, "w_vru": 0.30, "w_unc": 0.20}
COMPONENTS = (("score_shape", "shape"), ("score_slice", "slice"), ("score_vru", "vru"), ("score_unc", "unc"))
SIGMA_FLOOR_M = 0.05


@dataclass
class PredReference:
    """Tương đương FrozenReference nhưng dùng DỰ ĐOÁN (cls_pred + bin dự đoán), fit trên frame V."""
    n_frames_v: int
    edges_pred: dict = field(default_factory=dict)    # cls_pred -> {"dist": [...], "pts": [...]}
    cell_p_pred: dict = field(default_factory=dict)   # cell_pred -> p (frame V chứa cell / frame V)
    class_p_pred: dict = field(default_factory=dict)  # cls_pred -> p (object / tổng object thấy được)
    thresholds: dict = field(default_factory=dict)    # {"r1_class", "r2_combo"} = Q(1-alpha) của u_pred trên V
    cfg: dict = field(default_factory=dict)
    size_med: dict = field(default_factory=dict)      # cls_pred -> [med_l, med_w, med_h]
    size_sig: dict = field(default_factory=dict)      # cls_pred -> [std_l, std_w, std_h]

    def to_json(self) -> str:
        return json.dumps(asdict(self), ensure_ascii=False, sort_keys=True)

    @property
    def sha256(self) -> str:
        return hashlib.sha256(self.to_json().encode("utf-8")).hexdigest()


def _quant(x, q: float) -> float:
    return float(np.quantile(np.asarray(x, float), q, method="higher"))


def cell_of(cls: str, dist: float, pts: float, edges: dict) -> str | None:
    e = edges.get(cls)
    if e is None:
        return None
    return (f"{cls}|d{int(np.searchsorted(e['dist'], dist, side='right'))}"
            f"|p{int(np.searchsorted(e['pts'], pts, side='right'))}")


def object_cells(df: pd.DataFrame, edges: dict) -> list[str | None]:
    return [cell_of(c, d, p, edges) for c, d, p in zip(df["cls_pred"], df["dist_m"], df["pts"])]


def surprisal(ref: PredReference, cls: str, cell: str | None) -> tuple[float, float]:
    """(u_class, u_cell). Lớp/cell chưa thấy ở V => +inf (hiếm hơn mọi thứ đã thấy)."""
    pc, pcell = ref.class_p_pred.get(cls), (ref.cell_p_pred.get(cell) if cell else None)
    return (-math.log(pc) if pc else math.inf), (-math.log(pcell) if pcell else math.inf)


def fit_pred_reference(rare_objects_v: pd.DataFrame, rare_cfg: RareDefV24, n_frames: int | None = None,
                       vru_only: bool = False) -> PredReference:
    """Fit trên rare_objects của frame V (SPEC-P05 §5.1). bins = tứ phân vị mỗi cls_pred (dist_m, pts).

    `n_frames` = số frame V (kể cả frame không có vật; mặc định = số frame có vật). `vru_only=True` bỏ cls_pred="other"
    khỏi tham chiếu (chẩn đoán, KHÔNG phải mặc định). Không dùng nhãn."""
    obj = rare_objects_v[rare_objects_v["pts"] >= rare_cfg.min_pts]
    if vru_only:
        obj = obj[obj["cls_pred"] != "other"]
    n = int(n_frames) if n_frames is not None else int(rare_objects_v["sample_token"].nunique())
    ref = PredReference(n_frames_v=n, cfg=asdict(rare_cfg))
    total = len(obj)
    for c, g in obj.groupby("cls_pred"):
        ref.class_p_pred[c] = len(g) / total
        ref.edges_pred[c] = {k: sorted({_quant(g[col], q) for q in (.25, .5, .75)})
                             for k, col in (("dist", "dist_m"), ("pts", "pts"))}
        sz = g[["l", "w", "h"]].to_numpy(np.float64)
        ref.size_med[c] = np.median(sz, 0).tolist()
        ref.size_sig[c] = np.maximum(sz.std(0), SIGMA_FLOOR_M).tolist()
    cells = object_cells(obj, ref.edges_pred)
    frame_cells = Counter(c for _, cs in pd.Series(cells, index=obj["sample_token"].to_numpy()).groupby(level=0)
                          for c in set(cs))
    ref.cell_p_pred = {c: k / max(n, 1) for c, k in sorted(frame_cells.items())}
    u1, u2 = defaultdict(float), defaultdict(float)
    for tok, cls, cell in zip(obj["sample_token"], obj["cls_pred"], cells):
        a, b = surprisal(ref, cls, cell)
        u1[tok], u2[tok] = max(u1[tok], a), max(u2[tok], b)
    pad = [0.0] * max(n - len(u1), 0)
    q = 1 - rare_cfg.alpha
    ref.thresholds = {"r1_class": _quant(list(u1.values()) + pad, q) if n else 0.0,
                      "r2_combo": _quant(list(u2.values()) + pad, q) if n else 0.0}
    return ref


def score_objects(rare_objects: pd.DataFrame, ref: PredReference, unc_signals: pd.DataFrame | None,
                  keep, weights: dict | None = None, slice_vru_only: bool = False) -> pd.DataFrame:
    """Bản mới của rare_objects với score_*, s_obj, reasons (SPEC-P05 §5.2).

    `keep`: pd.Series/dict sample_token -> bool (None = mọi frame keep). `unc_signals`: bảng t1_signals căn theo
    index (None = Tầng 0 => score_unc = 0). `slice_vru_only`: chẩn đoán, score_slice của "other" = 0."""
    w = {**DEFAULT_WEIGHTS, **(weights or {})}
    df = rare_objects.copy()
    n = len(df)
    if n == 0:
        return df
    keep_s = pd.Series(keep) if keep is not None else None
    in_keep = df["sample_token"].map(keep_s).fillna(False).to_numpy(bool) if keep_s is not None \
        else np.ones(n, bool)
    cls = df["cls_pred"].to_numpy()
    # shape
    shape = np.zeros(n, np.float32)
    for c in set(cls) - {"other"}:
        if c not in ref.size_med:
            continue
        m = cls == c
        z = np.abs(df.loc[m, ["l", "w", "h"]].to_numpy(np.float64) - np.array(ref.size_med[c])) \
            / np.array(ref.size_sig[c])
        shape[m] = 1.0 - np.exp(-0.5 * z.max(1) ** 2)
    # slice
    cells = object_cells(df, ref.edges_pred)
    u = np.array([surprisal(ref, c, cell)[1] for c, cell in zip(cls, cells)], np.float64)
    unseen = ~np.isfinite(u)
    slc = pct_rank(np.where(unseen, 1e6, u), in_keep)
    slc[unseen & in_keep] = 1.0
    if slice_vru_only:
        slc[cls == "other"] = 0.0
    slc = np.where(in_keep, slc, 0.0).astype(np.float32)
    # vru
    vru = np.where(np.isin(cls, VRU_PRED), 1.0, np.where(cls == "vru_unknown", 0.5, 0.0)).astype(np.float32)
    # unc (cấp frame -> gán đều cho vật)
    unc = np.zeros(n, np.float32)
    if unc_signals is not None:
        k = (keep_s.reindex(unc_signals["sample_token"]).fillna(False).to_numpy(bool) if keep_s is not None
             else np.ones(len(unc_signals), bool))
        fu = dict(zip(unc_signals["sample_token"], unc_score(unc_signals, k)))
        unc = df["sample_token"].map(fu).fillna(0.0).to_numpy(np.float32)
    df["score_shape"], df["score_slice"], df["score_vru"], df["score_unc"] = shape, slc, vru, unc
    df["s_obj"] = np.clip(w["w_shape"] * shape + w["w_slice"] * slc + w["w_vru"] * vru + w["w_unc"] * unc,
                          0.0, 1.0).astype(np.float32)
    active = [(c, nm) for (c, nm), k in zip(COMPONENTS, ("w_shape", "w_slice", "w_vru", "w_unc")) if w[k] > 0]
    mat = df[[c for c, _ in active]].to_numpy(np.float64)
    top = mat.argmax(1)
    df["reasons"] = [f"{active[j][1]} p{int(round(100 * mat[i, j]))}" for i, j in enumerate(top)]
    return df
