"""Giám khảo AEB JA/JB: chấm toàn bộ ảnh, struggle theo đối tượng, hiệu chỉnh τ.

Thư viện nặng (torch, torchvision, transformers) chỉ được nạp MUỘN bên trong
`run_judge`/`_make_predictor`: test CPU truyền `predictor` giả nên không cần tải
trọng số. Predictor giả theo đúng hợp đồng của `c4/extract/det.py::_fake_predictor`:
`predictor(paths, batch) -> list[ndarray (n, 6)] = cls, conf, x1, y1, x2, y2`.
"""
import hashlib
from contextlib import nullcontext

import numpy as np
import pandas as pd
from PIL import Image

from c4.bench.gate import BenchGateError
from c4.contracts import CAMS, JUDGE_DET, validate

CONF_MIN = 0.05
JA_ID = "torchvision:fasterrcnn_resnet50_fpn_v2/COCO_V1"
JB_ID = "PekingU/rtdetr_r50vd"
TAU_GRID = tuple(round(0.05 + 0.01 * i, 2) for i in range(91))
IOU_ORDER = (0.5, 0.4, 0.3)
GROUP_BY_NAME = {"person": "vru", "bicycle": "vru", "motorcycle": "vru",
                 "car": "vehicle", "truck": "vehicle", "bus": "vehicle"}
KEYS = ["sample_token", "cam", "group"]

# Tên lớp COCO-91 của torchvision COCO_V1 (JA) và COCO-80 của RT-DETR (JB).
# Ánh xạ nhóm theo TÊN, không theo chỉ số: person JA=1 / JB=0.
COCO91 = (
    "__background__", "person", "bicycle", "car", "motorcycle", "airplane", "bus", "train",
    "truck", "boat", "traffic light", "fire hydrant", "street sign", "stop sign",
    "parking meter", "bench", "bird", "cat", "dog", "horse", "sheep", "cow", "elephant",
    "bear", "zebra", "giraffe", "hat", "backpack", "umbrella", "shoe", "eye glasses",
    "handbag", "tie", "suitcase", "frisbee", "skis", "snowboard", "sports ball", "kite",
    "baseball bat", "baseball glove", "skateboard", "surfboard", "tennis racket", "bottle",
    "plate", "wine glass", "cup", "fork", "knife", "spoon", "bowl", "banana", "apple",
    "sandwich", "orange", "broccoli", "carrot", "hot dog", "pizza", "donut", "cake",
    "chair", "couch", "potted plant", "bed", "mirror", "dining table", "window", "desk",
    "toilet", "door", "tv", "laptop", "mouse", "remote", "keyboard", "cell phone",
    "microwave", "oven", "toaster", "sink", "refrigerator", "blender", "book", "clock",
    "vase", "scissors", "teddy bear", "hair drier", "toothbrush", "hair brush",
)
COCO80 = (
    "person", "bicycle", "car", "motorcycle", "airplane", "bus", "train", "truck", "boat",
    "traffic light", "fire hydrant", "stop sign", "parking meter", "bench", "bird", "cat",
    "dog", "horse", "sheep", "cow", "elephant", "bear", "zebra", "giraffe", "backpack",
    "umbrella", "handbag", "tie", "suitcase", "frisbee", "skis", "snowboard",
    "sports ball", "kite", "baseball bat", "baseball glove", "skateboard", "surfboard",
    "tennis racket", "bottle", "wine glass", "cup", "fork", "knife", "spoon", "bowl",
    "banana", "apple", "sandwich", "orange", "broccoli", "carrot", "hot dog", "pizza",
    "donut", "cake", "chair", "couch", "potted plant", "bed", "dining table", "toilet",
    "tv", "laptop", "mouse", "remote", "keyboard", "cell phone", "microwave", "oven",
    "toaster", "sink", "refrigerator", "book", "clock", "vase", "scissors", "teddy bear",
    "hair drier", "toothbrush",
)


# ---- Ảnh và trọng số -----------------------------------------------------------
def _load_rgb(path) -> Image.Image:
    with Image.open(path) as image:
        return image.convert("RGB")


def _to_tensor(image: Image.Image):
    import torch

    arr = np.asarray(image, dtype=np.float32) / 255.0
    return torch.from_numpy(np.ascontiguousarray(arr.transpose(2, 0, 1)))


def _state_sha(model) -> str:
    """Vân tay trọng số: sha256 trên tên + giá trị từng tensor (không phụ thuộc cache)."""
    import torch

    digest = hashlib.sha256()
    for name, tensor in model.state_dict().items():
        digest.update(name.encode("utf-8"))
        digest.update(np.ascontiguousarray(
            tensor.detach().to(torch.float32).cpu().numpy()).tobytes())
    return digest.hexdigest()


def _resolve_device(device: str) -> str:
    import torch

    if device != "cpu" and not torch.cuda.is_available():
        return "cpu"
    return device


def _empty_cache() -> None:
    try:
        import torch
    except ImportError:
        return
    if torch.cuda.is_available():
        torch.cuda.empty_cache()


def _inference_guard(real_model: bool):
    """`torch.inference_mode()` cho model thật; predictor giả không cần torch."""
    if not real_model:
        return nullcontext()
    try:
        import torch
    except ImportError:
        return nullcontext()
    return torch.inference_mode()


def _ja_predictor(device: str):
    import torch
    import torchvision
    from torchvision.models.detection import (
        FasterRCNN_ResNet50_FPN_V2_Weights, fasterrcnn_resnet50_fpn_v2,
    )

    dev = _resolve_device(device)
    torch.manual_seed(0)
    model = fasterrcnn_resnet50_fpn_v2(weights=FasterRCNN_ResNet50_FPN_V2_Weights.COCO_V1,
                                       box_score_thresh=CONF_MIN, box_detections_per_img=300)
    model.eval()
    fingerprint = _state_sha(model)
    model.to(dev)

    def predict(paths, batch):
        out, step = [], max(1, int(batch))
        for lo in range(0, len(paths), step):
            tensors = [_to_tensor(_load_rgb(p)).to(dev) for p in paths[lo:lo + step]]
            with torch.inference_mode():
                results = model(tensors)
            for result in results:
                boxes = result["boxes"].detach().cpu().numpy()
                scores = result["scores"].detach().cpu().numpy()
                labels = result["labels"].detach().cpu().numpy()
                keep = scores >= CONF_MIN
                out.append(np.column_stack([labels[keep], scores[keep], boxes[keep]])
                           .astype(np.float32))
        return out

    versions = dict(judge="JA", model=JA_ID, device=dev, predictor="torchvision",
                    torch=torch.__version__, torchvision=torchvision.__version__,
                    transformers="", hf_revision="", weights_sha256=fingerprint)
    return predict, versions


def _jb_predictor(device: str):
    import torch
    import transformers
    from transformers import RTDetrForObjectDetection, RTDetrImageProcessor

    dev = _resolve_device(device)
    torch.manual_seed(0)
    processor = RTDetrImageProcessor.from_pretrained(JB_ID)
    model = RTDetrForObjectDetection.from_pretrained(JB_ID).eval()
    fingerprint = _state_sha(model)
    revision = str(getattr(model.config, "_commit_hash", "") or "")
    model.to(dev)

    def predict(paths, batch):
        out, step = [], max(1, int(batch))
        for lo in range(0, len(paths), step):
            images = [_load_rgb(p) for p in paths[lo:lo + step]]
            sizes = [(image.height, image.width) for image in images]
            inputs = processor(images=images, return_tensors="pt")
            inputs = {key: value.to(dev) for key, value in inputs.items()}
            with torch.inference_mode():
                outputs = model(**inputs)
            results = processor.post_process_object_detection(
                outputs, threshold=CONF_MIN, target_sizes=sizes)
            for result in results:
                boxes = result["boxes"].detach().cpu().numpy()
                scores = result["scores"].detach().cpu().numpy()
                labels = result["labels"].detach().cpu().numpy()
                keep = scores >= CONF_MIN
                out.append(np.column_stack([labels[keep], scores[keep], boxes[keep]])
                           .astype(np.float32))
        return out

    versions = dict(judge="JB", model=JB_ID, device=dev, predictor="transformers",
                    torch=torch.__version__, torchvision="",
                    transformers=transformers.__version__, hf_revision=revision,
                    weights_sha256=fingerprint)
    return predict, versions


def _make_predictor(judge: str, device: str):
    return _ja_predictor(device) if judge == "JA" else _jb_predictor(device)


# ---- run_judge -----------------------------------------------------------------
def _is_oom(exc: RuntimeError) -> bool:
    return exc.__class__.__name__ == "OutOfMemoryError" or "out of memory" in str(exc).lower()


def _det_rows(judge: str, names: tuple, preds, samples, cams):
    rows = []
    for i, raw in enumerate(preds):
        dets = np.asarray(raw, dtype=np.float32).reshape(-1, 6)
        for label, score, x1, y1, x2, y2 in dets:
            if not np.isfinite([label, score, x1, y1, x2, y2]).all() or score < CONF_MIN:
                continue
            index = int(label)
            if index < 0 or index >= len(names):
                continue
            group = GROUP_BY_NAME.get(names[index])
            if group is None:
                continue
            rows.append(dict(judge=judge, sample_token=samples[i], cam=cams[i],
                             coco_label=index, group=group, score=float(score),
                             x1=float(x1), y1=float(y1), x2=float(x2), y2=float(y2)))
    return rows


def _det_frame(rows) -> pd.DataFrame:
    """Ép đúng schema JUDGE_DET mà KHÔNG gọi `validate()`.

    `contracts.validate` gọi `df.duplicated([])` cho bảng không khóa; pandas 3 ném
    `ValueError: not enough values to unpack` với bảng không rỗng (blocker R01 #1,
    `contracts.py` ngoài phạm vi H04). Nội dung/dtype ở đây trùng đúng schema.
    """
    if not rows:
        return pd.DataFrame({name: pd.Series(dtype=kind)
                             for name, kind in JUDGE_DET.items()})
    out = pd.DataFrame(rows, columns=list(JUDGE_DET))
    out = out.astype(dict(JUDGE_DET)).reset_index(drop=True)
    if len(out) and not out["cam"].isin(CAMS).all():
        raise ValueError("judge_det: tên camera lạ")
    return out


def run_judge(judge: str, frames: pd.DataFrame, *, device: str = "cuda",
              batch: int = 16, predictor=None) -> pd.DataFrame:
    """Chấm JA/JB trên TOÀN BỘ ảnh trong `frames` (I2: không nhận selection)."""
    if judge not in {"JA", "JB"}:
        raise ValueError(f"judge lạ: {judge!r}")
    missing = [c for c in ("sample_token", "cam", "img_path") if c not in frames.columns]
    if missing:
        raise ValueError(f"frames thiếu cột {missing}")
    injected = predictor is not None
    if injected:
        versions = dict(judge=judge, model="predictor", device=device, predictor="injected",
                        torch="", torchvision="", transformers="", hf_revision="",
                        weights_sha256="")
    else:
        predictor, versions = _make_predictor(judge, device)
    names = COCO91 if judge == "JA" else COCO80
    paths = frames["img_path"].astype(str).tolist()
    samples = frames["sample_token"].astype(str).tolist()
    cams = frames["cam"].astype(str).tolist()
    rows, pos, current = [], 0, max(1, int(batch))
    while pos < len(paths):
        chunk = paths[pos:pos + current]
        try:
            with _inference_guard(not injected):
                preds = predictor(chunk, current)
        except RuntimeError as exc:
            if not _is_oom(exc):
                raise
            if current == 1:
                raise BenchGateError("GPU_OOM", f"{judge}: hết VRAM ở batch 1") from exc
            current = max(1, current // 2)
            _empty_cache()
            continue
        if len(preds) != len(chunk):
            raise ValueError(f"predictor trả {len(preds)} kết quả cho {len(chunk)} ảnh")
        rows.extend(_det_rows(judge, names, preds,
                              samples[pos:pos + len(chunk)], cams[pos:pos + len(chunk)]))
        pos += len(chunk)
    out = _det_frame(rows)
    out.attrs["judge"] = judge
    out.attrs["versions"] = versions
    return out


# ---- Khớp đối tượng và struggle -------------------------------------------------
def _iou_matrix(a: np.ndarray, b: np.ndarray) -> np.ndarray:
    if len(a) == 0 or len(b) == 0:
        return np.zeros((len(a), len(b)), np.float64)
    x1 = np.maximum(a[:, None, 0], b[None, :, 0])
    y1 = np.maximum(a[:, None, 1], b[None, :, 1])
    x2 = np.minimum(a[:, None, 2], b[None, :, 2])
    y2 = np.minimum(a[:, None, 3], b[None, :, 3])
    inter = np.clip(x2 - x1, 0, None) * np.clip(y2 - y1, 0, None)
    area_a = np.clip(a[:, 2] - a[:, 0], 0, None) * np.clip(a[:, 3] - a[:, 1], 0, None)
    area_b = np.clip(b[:, 2] - b[:, 0], 0, None) * np.clip(b[:, 3] - b[:, 1], 0, None)
    union = area_a[:, None] + area_b[None, :] - inter
    return np.divide(inter, union, out=np.zeros_like(inter), where=union > 0)


def _boxes(df: pd.DataFrame) -> np.ndarray:
    return df[["x1", "y1", "x2", "y2"]].to_numpy(np.float64)


def _best_match(det: pd.DataFrame, objs: pd.DataFrame, iou_thr: float):
    """Trả (best_score, best_iou) thẳng hàng với `objs`; không có ứng viên ⇒ 0, 0."""
    n = len(objs)
    best_score = np.zeros(n, np.float64)
    best_iou = np.zeros(n, np.float64)
    if n == 0 or len(det) == 0:
        return best_score, best_iou
    det = det.reset_index(drop=True)
    objs = objs.reset_index(drop=True)
    det_groups = {key: frame for key, frame in det.groupby(KEYS, sort=False)}
    for key, group in objs.groupby(KEYS, sort=False):
        dets = det_groups.get(key)
        if dets is None or dets.empty:
            continue
        iou = _iou_matrix(_boxes(group), _boxes(dets))
        scores = dets["score"].to_numpy(np.float64)
        valid = iou >= float(iou_thr)
        if not valid.any():
            continue
        masked = np.where(valid, scores[None, :], -np.inf)
        pick = masked.argmax(axis=1)
        index = group.index.to_numpy()
        row = np.arange(len(group))
        hit = valid[row, pick]
        best_score[index[hit]] = scores[pick[hit]]
        best_iou[index[hit]] = iou[row[hit], pick[hit]]
    return best_score, best_iou


def _matched_detections(det: pd.DataFrame, objs: pd.DataFrame, iou_thr: float) -> int:
    if len(det) == 0 or len(objs) == 0:
        return 0
    obj_groups = {key: frame for key, frame in objs.groupby(KEYS, sort=False)}
    hits = 0
    for key, dets in det.groupby(KEYS, sort=False):
        group = obj_groups.get(key)
        if group is None or group.empty:
            continue
        iou = _iou_matrix(_boxes(dets), _boxes(group))
        hits += int((iou.max(axis=1) >= float(iou_thr)).sum())
    return hits


def struggle_table(det: pd.DataFrame, objs: pd.DataFrame, tau: float,
                   iou_thr: float = 0.5, *, judge: str | None = None) -> pd.DataFrame:
    """`struggle = best_score < τ`; `unc = 1 − best_score` (không khớp ⇒ unc = 1)."""
    if judge is None:
        judge = str(det["judge"].iloc[0]) if len(det) else ""
    best_score, best_iou = _best_match(det, objs, iou_thr)
    out = pd.DataFrame(dict(
        judge=np.full(len(objs), judge, dtype=object),
        sample_token=objs["sample_token"].to_numpy(),
        ann_token=objs["ann_token"].to_numpy(),
        instance_token=objs["instance_token"].to_numpy(),
        scene_token=objs["scene_token"].to_numpy(),
        group=objs["group"].to_numpy(),
        best_iou=np.asarray(best_iou, np.float32),
        best_score=np.asarray(best_score, np.float32),
        struggle=best_score < float(tau),
        unc=np.asarray(1.0 - best_score, np.float32),
    ))
    return validate(out, "judge_struggle")


# ---- Hiệu chỉnh và kiểm hợp lệ ---------------------------------------------------
def _easy_mask(objs: pd.DataFrame) -> np.ndarray:
    if len(objs) == 0:
        return np.zeros(0, bool)
    height = (objs["y2"] - objs["y1"]).to_numpy(np.float64)
    return ((objs["dist_m"].to_numpy(np.float64) <= 20.0) & (height >= 50.0)
            & (objs["num_lidar_pts"].to_numpy(np.float64) >= 20))


def _largest_tau(easy_scores: np.ndarray, target: float) -> float | None:
    if len(easy_scores) == 0:
        return None
    for tau in reversed(TAU_GRID):
        if float((easy_scores >= tau).mean()) >= target:
            return float(tau)
    return None


def calibrate_tau(det_cal: pd.DataFrame, objs_cal: pd.DataFrame,
                  target_recall_easy: float = 0.90, iou_thr: float = 0.5) -> dict:
    """τ lớn nhất đạt recall trên tập DỄ ≥ `target_recall_easy` (SPEC-P03 §4).

    Thử iou 0.5 → 0.4 → 0.3, lấy giá trị ĐẦU TIÊN hiệu chỉnh được.
    """
    target = float(target_recall_easy)
    objs = objs_cal.reset_index(drop=True)
    easy = _easy_mask(objs)
    candidates = [float(iou_thr)] + [t for t in IOU_ORDER if t != float(iou_thr)]
    chosen_iou, chosen_tau, found = float(candidates[-1]), float(TAU_GRID[0]), False
    best_score = np.zeros(len(objs), np.float64)
    for thr in candidates:
        scores, _ = _best_match(det_cal, objs, thr)
        tau = _largest_tau(scores[easy], target)
        chosen_iou, best_score = thr, scores
        if tau is not None:
            chosen_tau, found = tau, True
            break
    easy_scores = best_score[easy]
    recall_easy = float((easy_scores >= chosen_tau).mean()) if easy.any() else 0.0
    recall = float((best_score >= chosen_tau).mean()) if len(best_score) else 0.0
    kept = det_cal.loc[det_cal["score"] >= chosen_tau] if len(det_cal) else det_cal
    n_det = int(len(kept))
    precision = (_matched_detections(kept, objs, chosen_iou) / n_det) if n_det else 0.0
    return dict(tau=chosen_tau, iou_thr=chosen_iou, precision=float(precision),
                recall=recall, recall_easy=recall_easy, target=target, found=found,
                n_det=n_det, n_obj=int(len(objs)))


def _auroc(scores: np.ndarray, labels: np.ndarray) -> float:
    positive = labels.astype(bool)
    n_pos, n_neg = int(positive.sum()), int((~positive).sum())
    if n_pos == 0 or n_neg == 0:
        return 0.5
    ranks = pd.Series(scores).rank(method="average").to_numpy()
    return float((ranks[positive].sum() - n_pos * (n_pos + 1) / 2.0) / (n_pos * n_neg))


def validity(st_cal: pd.DataFrame, *, objs: pd.DataFrame | None = None,
             calibration: dict | None = None) -> dict:
    """V1 (hiệu chỉnh được), V2 (tỉ lệ struggle khó/dễ ≥ 2.0), AUROC(unc → struggle).

    V3 (Cohen κ JA/JB) do CLI tính sau khi có đủ hai bảng; hàm này không tự loại ai.
    `objs` cần cho V1/V2 vì bảng struggle không mang `dist_m`/chiều cao/số điểm LiDAR.
    """
    st = st_cal.reset_index(drop=True)
    out = dict(auroc_unc_vs_miss=0.5, recall_easy=0.0, n_obj=int(len(st)), n_easy=0,
               n_hard=0, struggle_rate_easy=0.0, struggle_rate_hard=0.0, v2_ratio=None,
               v1_calibration=False, v2_ok=False, ok=False)
    if len(st) == 0:
        return out
    labels = st["struggle"].astype(bool).to_numpy()
    out["auroc_unc_vs_miss"] = _auroc(st["unc"].to_numpy(np.float64), labels)
    easy = hard = np.zeros(len(st), bool)
    if objs is not None and len(objs):
        cols = ["sample_token", "ann_token", "dist_m", "num_lidar_pts", "x1", "y1", "x2", "y2"]
        joined = st[["sample_token", "ann_token"]].merge(
            objs[cols], on=["sample_token", "ann_token"], how="left", validate="one_to_one")
        dist = joined["dist_m"].to_numpy(np.float64)
        pts = joined["num_lidar_pts"].to_numpy(np.float64)
        height = (joined["y2"] - joined["y1"]).to_numpy(np.float64)
        easy = (dist <= 20.0) & (height >= 50.0) & (pts >= 20.0)
        hard = ((dist > 30.0) & (dist <= 40.0)) | (pts < 10.0) | (height < 40.0)
    n_easy, n_hard = int(easy.sum()), int(hard.sum())
    out.update(n_easy=n_easy, n_hard=n_hard)
    if n_easy:
        out["struggle_rate_easy"] = float(labels[easy].mean())
        out["recall_easy"] = 1.0 - out["struggle_rate_easy"]
    if n_hard:
        out["struggle_rate_hard"] = float(labels[hard].mean())
    if n_easy and n_hard:
        rate_easy, rate_hard = out["struggle_rate_easy"], out["struggle_rate_hard"]
        if rate_easy == 0.0:
            out["v2_ratio"] = None
            out["v2_ok"] = bool(rate_hard > 0.0)
        else:
            out["v2_ratio"] = rate_hard / rate_easy
            out["v2_ok"] = bool(out["v2_ratio"] >= 2.0)
    if calibration is not None:
        out["v1_calibration"] = bool(calibration.get("found", True))
    else:
        out["v1_calibration"] = bool(n_easy and out["recall_easy"] >= 0.90)
    out["ok"] = bool(out["v1_calibration"] and out["v2_ok"])
    return out
