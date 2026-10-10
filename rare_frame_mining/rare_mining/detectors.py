"""Detector adapters + TTA (M1, đường nguồn b).

- PointPillars CHỈ inference (đề bài: không train lại). Ba backend:
    * heuristic  : detector giả lập từ clustering (chạy được mọi nơi, dùng cho demo/test)
    * mmdet3d    : PointPillars pretrained nuScenes của mmdetection3d (checkpoint công khai)
    * openpcdet  : PointPillar-MultiHead của OpenPCDet
  Hai backend thật cần torch + GPU và KHÔNG được chạy trong sandbox khi đóng gói
  (đã ghi rõ trong README) — code defensive, lỗi rõ ràng nếu thiếu môi trường.
- TTA: xoay/flip/jitter điểm → chạy lại detector → biến đổi ngược box →
  phương sai + entropy = s_unc (đường thay thế rẻ cho consistency nhiều detector).
"""
import math
from dataclasses import dataclass, field
from typing import List, Optional, Tuple

import numpy as np

from .utils import rot2d

CLASSES = ["pedestrian", "bicycle", "motorcycle", "vehicle", "other"]


@dataclass
class Detection:
    center: np.ndarray            # (x, y, z)
    size: np.ndarray              # (L, W, H)
    yaw: float
    score: float
    class_name: str
    probs: Optional[np.ndarray] = None   # xác suất theo CLASSES
    n_points: int = 0


class BaseDetector:
    name = "base"

    def detect(self, points: np.ndarray) -> List[Detection]:
        raise NotImplementedError


# ---------------------------------------------------------------------------
# Backend heuristic (demo/offline — không cần torch)
# ---------------------------------------------------------------------------

_TEMPLATES = {
    "pedestrian": (0.6, 0.6, 1.75),
    "bicycle": (1.75, 0.65, 1.5),
    "motorcycle": (2.1, 0.85, 1.5),
    "vehicle": (4.3, 1.85, 1.7),
}


class HeuristicDetector(BaseDetector):
    """Detector giả lập: cluster → box → pseudo-class theo khớp template hình học.

    Dùng để chạy end-to-end không cần GPU; score/entropy là hàm của số điểm và
    độ khớp template nên TTA vẫn tạo ra variance có nghĩa.
    """
    name = "heuristic"

    def __init__(self, cluster_cfg, roi_cfg, score_thresh: float = 0.25):
        from . import features as F
        self.F = F
        self.ccfg = cluster_cfg
        self.roi = roi_cfg
        self.score_thresh = score_thresh

    def detect(self, points: np.ndarray) -> List[Detection]:
        pts = self.F.crop_roi(points, self.roi)
        if pts.shape[0] < 10:
            return []
        fg = self.F.remove_ground(pts, self.ccfg.ground_cell, self.ccfg.ground_h_thresh)
        labels = self.F.cluster_points(fg, self.ccfg)
        dets: List[Detection] = []
        if fg.shape[0] == 0:
            return dets
        ground_ref = float(np.percentile(fg[:, 2], 5))
        for lab in np.unique(labels):
            if lab < 0:
                continue
            cpts = fg[labels == lab]
            if cpts.shape[0] < self.ccfg.min_cluster_points:
                continue
            f = self.F.cluster_features(cpts, ground_ref)
            dims = np.array([f["L"], f["W"], f["H"]])
            fits = []
            for (tl, tw, th) in _TEMPLATES.values():
                t = np.array([tl, tw, th])
                fits.append(float(np.exp(-0.5 * np.sum(((dims - t) / np.array([0.5, 0.3, 0.35])) ** 2))))
            fits = np.array(fits)
            dist = math.hypot(f["centroid"][0], f["centroid"][1])
            if fits.max() < 0.25:
                cls = "other"
                probs = np.full(len(CLASSES), 0.2)
            else:
                e = np.exp(3.5 * (fits - fits.max()))
                sm = e / e.sum()
                probs = np.concatenate([sm * 0.9, [0.1]])
                cls = list(_TEMPLATES.keys())[int(fits.argmax())]
            score = min(0.9, 0.25 + 0.55 / (1.0 + math.exp(-(f["n_points"] - 25) / 22)) + 0.1 * float(fits.max()))
            score *= float(np.exp(-dist / 80.0))
            if score < self.score_thresh:
                continue
            dets.append(Detection(
                center=np.array(f["centroid"]), size=np.array([f["L"], f["W"], f["H"]]),
                yaw=f["yaw"], score=float(score), class_name=cls,
                probs=probs, n_points=f["n_points"],
            ))
        return dets


# ---------------------------------------------------------------------------
# Backend thật (cần torch + model zoo) — adapter mỏng, defensive
# ---------------------------------------------------------------------------

class MMDet3DPointPillars(BaseDetector):
    """PointPillars pretrained trên nuScenes từ mmdetection3d (SECFPN/FPN).

    Chỉ inference. Cần: pip install torch mmdet3d (bản khớp CUDA/spconv) + checkpoint.
    Xem README mục "Cắm PointPillars thật".
    """
    name = "mmdet3d"

    def __init__(self, config_path: str, checkpoint: str, device: str = "cuda:0",
                 score_thresh: float = 0.25, roi_cfg=None, class_map: Optional[dict] = None):
        try:
            from mmdet3d.apis import init_model  # noqa
        except Exception as e:
            raise RuntimeError(
                "Backend mmdet3d cần môi trường torch+mmdet3d (không có trong sandbox). "
                f"Lỗi gốc: {e}") from e
        self.model = init_model(config_path, checkpoint, device=device)
        self.score_thresh = score_thresh
        self.roi = roi_cfg
        self.class_map = class_map  # label_id → tên lớp chuẩn hoá (bicycle/motorcycle/pedestrian/...)

    def detect(self, points: np.ndarray) -> List[Detection]:
        from mmdet3d.apis import inference_detector
        from . import features as F
        pts = F.crop_roi(points, self.roi) if self.roi is not None else points
        result = inference_detector(self.model, pts[:, :3].astype(np.float32))
        dets: List[Detection] = []
        try:
            boxes = result[0][0].tensor.numpy()   # (N, 9): x,y,z,w?,l?,h?,yaw,score,label — KIỂM TRA trên máy thật
        except Exception:
            boxes = result[0][0].numpy()
        # LƯU Ý (phải verify trên máy có GPU): thứ tự cột kích thước có thể là (w, l, h)
        # tùy phiên bản mmdet3d; kiểm chứng bằng 1 frame có GT trước khi chạy toàn bộ.
        for row in boxes:
            x, y, z, d1, d2, d3, yaw, sc, lab = row[:9]
            if sc < self.score_thresh:
                continue
            cls = self.class_map.get(int(lab), "other") if self.class_map else f"label_{int(lab)}"
            dets.append(Detection(center=np.array([x, y, z]),
                                  size=np.array([d1, d2, d3]),
                                  yaw=float(yaw), score=float(sc), class_name=cls))
        return dets


class OpenPCDetPointPillars(BaseDetector):
    """PointPillar-MultiHead (OpenPCDet) — nuScenes. Chỉ inference."""
    name = "openpcdet"

    def __init__(self, config_path: str, checkpoint: str, score_thresh: float = 0.25,
                 roi_cfg=None, class_map: Optional[dict] = None):
        try:
            from pcdet.config import cfg, cfg_from_yaml_file
            from pcdet.datasets import build_dataloader
            from pcdet.models import build_network, load_checkpoint  # noqa
        except Exception as e:
            raise RuntimeError(
                "Backend openpcdet cần môi trường torch+OpenPCDet (không có trong sandbox). "
                f"Lỗi gốc: {e}") from e
        cfg_from_yaml_file(config_path, cfg)
        import torch  # noqa
        self.net = build_network(model_cfg=cfg.MODEL, num_class=len(cfg.CLASS_NAMES), dataset=None)
        self.net.load_params_from_file(checkpoint, logger=None, to_cpu=False)
        self.net.eval()
        self.class_names = list(cfg.CLASS_NAMES)
        self.score_thresh = score_thresh
        self.roi = roi_cfg
        self.class_map = class_map

    def detect(self, points: np.ndarray) -> List[Detection]:
        import torch
        from . import features as F
        pts = F.crop_roi(points, self.roi) if self.roi is not None else points
        d = {"points": torch.from_numpy(pts.astype(np.float32)).unsqueeze(0)}
        with torch.no_grad():
            pred = self.net.forward(d)[0]
        dets = []
        for i in range(pred["boxes_3d"] if isinstance(pred, dict) else len(pred["boxes"])):
            pass  # kiến trúc output tùy phiên bản — xem docs/CUSTOM_DATASET_TUTORIAL.md của OpenPCDet
        raise RuntimeError("OpenPCDet adapter: cần map output theo phiên bản — xem README trước khi dùng.")
        return dets


def make_detector(cfg):
    b = cfg.detector.backend
    if b == "heuristic":
        return HeuristicDetector(cfg.cluster, cfg.roi, cfg.detector.score_thresh)
    if b == "mmdet3d":
        return MMDet3DPointPillars(cfg.detector.config_path, cfg.detector.checkpoint,
                                   cfg.detector.device, cfg.detector.score_thresh, cfg.roi)
    if b == "openpcdet":
        return OpenPCDetPointPillars(cfg.detector.config_path, cfg.detector.checkpoint,
                                     cfg.detector.score_thresh, cfg.roi)
    raise ValueError(f"Backend không hỗ trợ: {b}")


# ---------------------------------------------------------------------------
# TTA
# ---------------------------------------------------------------------------

def tta_passes(tta_cfg) -> List[Tuple[float, bool]]:
    if not tta_cfg.enabled:
        return [(0.0, False)]
    passes = []
    for rot in tta_cfg.rots_deg:
        for flip in tta_cfg.flips:
            passes.append((float(rot), bool(flip)))
    if (0.0, False) not in [(r, f) for r, f in passes]:
        passes.insert(0, (0.0, False))
    return passes


def augment_points(points: np.ndarray, rot_deg: float, flip: bool,
                   jitter_std: float, rng: np.random.Generator) -> np.ndarray:
    q = points.copy()
    if flip:
        q[:, 1] *= -1.0
    if rot_deg != 0.0:
        q[:, :2] = q[:, :2] @ rot2d(rot_deg).T
    if jitter_std > 0:
        q[:, :3] += rng.normal(0.0, jitter_std, q[:, :3].shape)
    return q


def untransform_box(center: np.ndarray, yaw: float, rot_deg: float, flip: bool):
    """Biến đổi ngược box từ frame augmented về frame gốc.
    Quy ước: p' = R(rot) @ F @ p  (cột); row-equivalent: p'row = (p row * F) @ R.T."""
    c2 = center[:2] @ rot2d(rot_deg)
    d = np.array([math.cos(yaw), math.sin(yaw)]) @ rot2d(rot_deg)
    if flip:
        c2[1] *= -1.0
        d[1] *= -1.0
    return np.array([c2[0], c2[1], center[2]]), float(math.atan2(d[1], d[0]))
