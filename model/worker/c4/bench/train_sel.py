"""Fixed-recipe JA training and scene-cluster AP50 evaluation (SPEC-P05)."""
from contextvars import ContextVar
import json
import math
from pathlib import Path
import random

import numpy as np
import pandas as pd
from PIL import Image

from c4.bench.aeb import aeb_objects
from c4.bench.gate import BenchGateError, check_selections, require
from c4.bench.judge import (
    COCO91, GROUP_BY_NAME, _boxes, _iou_matrix, _load_rgb, _to_tensor, struggle_table,
)
from c4.contracts import read_table

RECIPE = dict(lr=0.005, momentum=0.9, weight_decay=1e-4, batch=8, epochs=12,
              cameras=6, warmup=200, width=1600, height=900, workers=0)
# CLI context preserves the public job-only contracts, including calls from notebooks.
_DATA_ROOT = ContextVar("train_selection_data_root", default=None)
LABELS = {"person": 1, "bicycle": 2, "car": 3, "motorcycle": 4, "bus": 6, "truck": 8}


def _label(category):
    if category.startswith("human.pedestrian."):
        return 1
    if category.startswith("vehicle.bus."):
        return 6
    return LABELS.get(category.removeprefix("vehicle."))


def _write_json(path, payload):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_suffix(path.suffix + ".tmp")
    temp.write_text(json.dumps(payload, sort_keys=True, indent=1, allow_nan=False),
                    encoding="utf-8")
    temp.replace(path)


def _frames(job, tokens):
    frames = read_table(require(Path(job) / "index/frames.parquet"), "frames")
    frames = frames.loc[frames.sample_token.isin(tokens)].copy()
    root = _DATA_ROOT.get() or Path(job)
    frames["img_path"] = frames.img_path.map(lambda p: str(Path(root) / str(p)))
    for path in frames.img_path:
        require(Path(path))
        with Image.open(path) as image:
            if image.size != (RECIPE["width"], RECIPE["height"]):
                raise BenchGateError("MISSING_INPUT", f"expected 1600x900: {path}")
            image.verify()
    return frames.sort_values(["sample_token", "cam"], kind="stable")


def build_train_set(job: Path, tokens: list[str]) -> pd.DataFrame:
    """All available cameras, including images without any mapped boxes."""
    job = Path(job)
    frames = _frames(job, tokens)
    gt = read_table(require(job / "gt/gt_boxes_2d.parquet"), "gt_boxes_2d")
    grouped = {key: rows for key, rows in gt.groupby(["sample_token", "cam"], sort=False)}
    rows = []
    for frame in frames.itertuples():
        boxes, labels = [], []
        for obj in grouped.get((frame.sample_token, frame.cam), gt.iloc[:0]).itertuples():
            label = _label(obj.category)
            if label is not None and obj.y2 - obj.y1 >= 8 and obj.x2 > obj.x1:
                boxes.append([obj.x1, obj.y1, obj.x2, obj.y2])
                labels.append(label)
        rows.append(dict(img_path=frame.img_path, boxes=boxes, labels=labels))
    return pd.DataFrame(rows, columns=["img_path", "boxes", "labels"])


def training_steps(budget, recipe=RECIPE):
    return int(recipe["epochs"] * math.ceil(budget * recipe["cameras"] / recipe["batch"]))


def _seed_worker(worker_id):
    import torch

    seed = torch.initial_seed() % (2 ** 32)
    random.seed(seed)
    np.random.seed(seed)


def _collate(batch):
    return tuple(zip(*batch))


class _FixedBatches:
    """Cycle shuffled images so even the last batch has exactly eight images."""
    def __init__(self, size, steps, batch, generator):
        self.size, self.steps, self.batch, self.generator = size, steps, batch, generator

    def __len__(self):
        return self.steps

    def __iter__(self):
        import torch

        pending = []
        for _ in range(self.steps):
            while len(pending) < self.batch:
                pending.extend(torch.randperm(self.size, generator=self.generator).tolist())
            yield pending[:self.batch]
            del pending[:self.batch]


class _Images:
    def __init__(self, table):
        self.rows = table.to_dict("records")

    def __len__(self):
        return len(self.rows)

    def __getitem__(self, index):
        import torch

        row = self.rows[index]
        image = _to_tensor(_load_rgb(row["img_path"]))
        boxes = torch.tensor(row["boxes"], dtype=torch.float32).reshape(-1, 4)
        if random.random() < 0.5:
            image = image.flip(-1)
            boxes[:, [0, 2]] = image.shape[-1] - boxes[:, [2, 0]]
        return image, dict(boxes=boxes, labels=torch.tensor(row["labels"], dtype=torch.int64))


def _model(model_factory=None):
    if model_factory is not None:
        return model_factory()
    from torchvision.models.detection import (
        FasterRCNN_ResNet50_FPN_V2_Weights, fasterrcnn_resnet50_fpn_v2,
    )

    return fasterrcnn_resnet50_fpn_v2(
        weights=FasterRCNN_ResNet50_FPN_V2_Weights.COCO_V1,
        box_score_thresh=0.05, box_detections_per_img=300)


def finetune(job: Path, tokens: list[str], seed: int, out: Path,
             recipe: dict = RECIPE, *, model_factory=None) -> Path:
    """Save only the terminal checkpoint; never inspect EVAL during training."""
    import torch
    from torch.utils.data import DataLoader

    for key, value in RECIPE.items():
        if recipe.get(key) != value:
            raise BenchGateError("ORDER_VIOLATION", f"fixed recipe: {key}={value}")
    random.seed(seed)
    np.random.seed(seed)
    torch.manual_seed(seed)
    if torch.cuda.is_available():
        torch.cuda.manual_seed_all(seed)
    torch.backends.cudnn.benchmark = False
    torch.backends.cudnn.deterministic = True
    table = build_train_set(job, tokens)
    if table.empty or not tokens:
        raise BenchGateError("MISSING_INPUT", "empty training selection/images")
    out = Path(out)
    out.mkdir(parents=True, exist_ok=True)
    steps = training_steps(len(tokens), recipe)
    device = "cuda" if torch.cuda.is_available() else "cpu"
    amp = device == "cuda" and torch.cuda.is_bf16_supported()
    model = _model(model_factory).to(device).train()
    optimizer = torch.optim.SGD(model.parameters(), lr=recipe["lr"],
                                momentum=recipe["momentum"], weight_decay=recipe["weight_decay"])
    generator = torch.Generator().manual_seed(seed)
    batches = _FixedBatches(len(table), steps, recipe["batch"], generator)
    loader = DataLoader(_Images(table), batch_sampler=batches,
                        num_workers=recipe["workers"], collate_fn=_collate,
                        worker_init_fn=_seed_worker, generator=generator)
    iterator = iter(loader)
    n_vru = sum(sum(label in {1, 2, 4} for label in labels) for labels in table.labels)
    with (out / "train_log.jsonl").open("w", encoding="utf-8") as log:
        for step in range(steps):
            images, targets = next(iterator)
            warmup = recipe["warmup"]
            factor = ((step + 1) / warmup if step < warmup else
                      0.5 * (1 + math.cos(math.pi * (step - warmup) /
                                         max(1, steps - warmup - 1))))
            for group in optimizer.param_groups:
                group["lr"] = recipe["lr"] * factor
            images = [image.to(device) for image in images]
            targets = [{k: v.to(device) for k, v in target.items()} for target in targets]
            optimizer.zero_grad(set_to_none=True)
            with torch.autocast(device_type=device, dtype=torch.bfloat16, enabled=amp):
                loss = sum(model(images, targets).values())
            value = float(loss.detach().cpu())
            record = dict(step=step + 1, S=steps, loss=value if math.isfinite(value) else None,
                          lr=optimizer.param_groups[0]["lr"], n_vru_boxes=n_vru)
            log.write(json.dumps(record, allow_nan=False) + "\n")
            log.flush()
            if not math.isfinite(value):
                raise BenchGateError("NAN_LOSS", f"seed={seed}, step={step + 1}")
            loss.backward()
            optimizer.step()
    ckpt = out / "ckpt.pt"
    temp = out / "ckpt.pt.tmp"
    torch.save(dict(model=model.state_dict(), recipe=RECIPE, seed=seed, steps=steps,
                    n_vru_boxes=n_vru), temp)
    temp.replace(ckpt)
    return ckpt


def ap101(tp, fp, scores, n_gt):
    """COCO 101-point interpolated AP after stable global score ordering."""
    if n_gt == 0:
        return None
    order = np.argsort(-np.asarray(scores, dtype=float), kind="stable")
    tp = np.cumsum(np.asarray(tp, dtype=float)[order])
    fp = np.cumsum(np.asarray(fp, dtype=float)[order])
    recall = tp / n_gt
    precision = tp / np.maximum(tp + fp, 1)
    precision = np.maximum.accumulate(precision[::-1])[::-1]
    values = [float(precision[i]) if i < len(precision) else 0.0
              for i in np.searchsorted(recall, np.linspace(0, 1, 101), side="left")]
    return float(np.mean(values))


def _events(det, gt, scenes, group, valid):
    per_scene = {str(scene): dict(tp=[], fp=[], scores=[], n_gt=0) for scene in scenes}
    valid_keys = set(zip(valid.sample_token, valid.cam, valid.ann_token))
    grouped = {key: rows for key, rows in gt.loc[gt.group == group].groupby(
        ["sample_token", "cam"], sort=False)}
    for rows in grouped.values():
        for obj in rows.itertuples():
            if (obj.sample_token, obj.cam, obj.ann_token) in valid_keys:
                per_scene[str(obj.scene_token)]["n_gt"] += 1
    for key, detections in det.loc[det.group == group].groupby(
            ["sample_token", "cam"], sort=True):
        objects = grouped.get(key, gt.iloc[:0]).reset_index(drop=True)
        used = set()
        positive = [(r.sample_token, r.cam, r.ann_token) in valid_keys
                    for r in objects.itertuples()]
        for detection in detections.sort_values("score", ascending=False,
                                                kind="stable").itertuples():
            box = np.asarray([[detection.x1, detection.y1, detection.x2, detection.y2]])
            ious = _iou_matrix(box, _boxes(objects))[0]
            candidates = [i for i, ok in enumerate(positive)
                          if ok and i not in used and ious[i] >= 0.5]
            tp = bool(candidates)
            if tp:
                used.add(max(candidates, key=lambda i: ious[i]))
            elif any(not ok and ious[i] >= 0.5 for i, ok in enumerate(positive)):
                continue  # Ignore regions absorb detections, including on other cameras.
            scene = str(detection.scene_token)
            events = per_scene[scene]
            events["tp"].append(int(tp))
            events["fp"].append(int(not tp))
            events["scores"].append(float(detection.score))
    return per_scene


def _merged_ap(events):
    return ap101([x for e in events for x in e["tp"]],
                 [x for e in events for x in e["fp"]],
                 [x for e in events for x in e["scores"]], sum(e["n_gt"] for e in events))


def _eval_data(job, split):
    job = Path(job)
    splits = read_table(require(job / "bench/bench_split.parquet"), "bench_split")
    scenes = splits.loc[splits.bench_split == split.upper(), "scene_token"].tolist()
    index = read_table(require(job / "lidar/index.parquet"), "lidar_index")
    tokens = index.loc[index.scene_token.isin(scenes), "sample_token"].tolist()
    frames = _frames(job, tokens)
    gt = read_table(require(job / "gt/gt_boxes_2d.parquet"), "gt_boxes_2d")
    gt = gt.loc[gt.sample_token.isin(tokens)].copy()
    root = _DATA_ROOT.get() or job
    paths = sorted(Path(root).glob("v*/sample_annotation.json"))
    if not paths:
        raise BenchGateError("MISSING_INPUT", f"{root}/v*/sample_annotation.json")
    meta = pd.DataFrame(json.loads(paths[0].read_text(encoding="utf-8")))
    meta["scene_token"] = meta.sample_token.map(index.set_index("sample_token").scene_token)
    boxes3d = read_table(require(job / "gt/boxes_3d.parquet"), "boxes_3d")
    valid = aeb_objects(gt, boxes3d, meta)
    # All projections remain available as ignore regions (including categories JA cannot train).
    gt["group"] = gt.category.map(lambda c: "vru" if c.startswith("human.pedestrian.")
                                 or c in {"vehicle.bicycle", "vehicle.motorcycle"}
                                 else "vehicle" if c in {"vehicle.car", "vehicle.truck",
                                                        "vehicle.trailer"}
                                 or c.startswith(("vehicle.bus.", "vehicle.emergency.")) else "")
    gt["scene_token"] = gt.sample_token.map(index.set_index("sample_token").scene_token)
    return frames, gt, valid, scenes


def _predict(frames, ckpt, model_factory=None):
    import torch

    device = "cuda" if torch.cuda.is_available() else "cpu"
    model = _model(model_factory)
    if ckpt is not None:
        state = torch.load(require(Path(ckpt)), map_location="cpu", weights_only=True)
        model.load_state_dict(state["model"])
    model.to(device).eval()
    rows = []
    with torch.inference_mode():
        for frame in frames.itertuples():
            image = _to_tensor(_load_rgb(frame.img_path)).to(device)
            try:
                result = model([image])[0]
            except RuntimeError as exc:
                if "out of memory" in str(exc).lower():
                    raise BenchGateError("GPU_OOM", "JA evaluation at batch 1") from exc
                raise
            for box, score, label in zip(result["boxes"].detach().cpu().tolist(),
                                         result["scores"].detach().cpu().tolist(),
                                         result["labels"].detach().cpu().tolist()):
                name = COCO91[label] if 0 <= label < len(COCO91) else ""
                if name in GROUP_BY_NAME and score >= 0.05:
                    rows.append(dict(sample_token=frame.sample_token, cam=frame.cam,
                                     scene_token=frame.scene_token, group=GROUP_BY_NAME[name],
                                     score=score, x1=box[0], y1=box[1], x2=box[2], y2=box[3]))
    return pd.DataFrame(rows, columns=["sample_token", "cam", "scene_token", "group", "score",
                                       "x1", "y1", "x2", "y2"])


def eval_ap(job: Path, ckpt: Path | None, split: str = "EVAL",
            tau_file: Path | None = None, *, model_factory=None) -> dict:
    frames, gt, valid, scenes = _eval_data(job, split)
    tau_file = tau_file or Path(job) / "bench/judge/judge_calib.json"
    calib = json.loads(require(Path(tau_file)).read_text(encoding="utf-8"))["JA"]
    # Compute the hard slice using the ORIGINAL JA, never the fine-tuned checkpoint.
    baseline = _predict(frames, None, model_factory)
    st = struggle_table(baseline, valid, calib["tau"], calib.get("iou_thr", 0.5), judge="JA")
    hard = valid.loc[st.struggle.to_numpy()].copy()
    det = baseline if ckpt is None else _predict(frames, ckpt, model_factory)
    groups = {"vru": _events(det, gt, scenes, "vru", valid),
              "vehicle": _events(det, gt, scenes, "vehicle", valid),
              "vru_hard": _events(det, gt, scenes, "vru", hard)}
    per_scene = {str(s): dict(**groups["vru"][str(s)],
                              vehicle=groups["vehicle"][str(s)],
                              vru_hard=groups["vru_hard"][str(s)]) for s in scenes}
    return dict(ap50_vru=_merged_ap(list(groups["vru"].values())),
                ap50_vehicle=_merged_ap(list(groups["vehicle"].values())),
                ap50_vru_hard=_merged_ap(list(groups["vru_hard"].values())),
                n_obj=len(valid), n_obj_hard=len(hard), per_scene=per_scene)


def bootstrap_delta(left, right, n_boot=2000, seed=20261017):
    """Paired scene resampling; recompute pooled AP separately for every seed."""
    if not left or not right:
        return dict(delta=None, lo=None, hi=None, n_boot=n_boot, n_valid=0)
    scene_sets = [set(run["per_scene"]) for run in left + right]
    if any(s != scene_sets[0] for s in scene_sets):
        raise BenchGateError("ORDER_VIOLATION", "inconsistent EVAL scenes")
    scenes = sorted(scene_sets[0])
    rng = np.random.default_rng(seed)
    samples = []
    for _ in range(n_boot):
        picked = rng.choice(scenes, len(scenes), replace=True).tolist()
        a = [_merged_ap([run["per_scene"][s] for s in picked]) for run in left]
        b = [_merged_ap([run["per_scene"][s] for s in picked]) for run in right]
        if all(value is not None for value in a + b):
            samples.append(float(np.mean(a) - np.mean(b)))
    delta = (float(np.mean([r["ap50_vru"] for r in left]) -
                   np.mean([r["ap50_vru"] for r in right]))
             if all(r["ap50_vru"] is not None for r in left + right) else None)
    lo, hi = np.quantile(samples, [0.025, 0.975]).tolist() if samples else (None, None)
    return dict(delta=delta, lo=lo, hi=hi, n_boot=n_boot, n_valid=len(samples), seed=seed)


def _tokens(sels, method, seed):
    entry = sels["methods"][method]
    if method == "X0":
        tokens = entry["seeds"][str(seed)][:sels["B"]]
    elif "by_frac" in entry:
        tokens = entry["by_frac"]["0.05"]
        if isinstance(tokens, dict):
            tokens = tokens["tokens"]
    else:
        tokens = entry["tokens"][:sels["B"]]
    if len(tokens) != sels["B"] or len(set(tokens)) != len(tokens):
        raise BenchGateError("ORDER_VIOLATION", f"{method}: expected B unique frames")
    return tokens


def run_train_eval(job, methods, seeds, *, data_root=None, open_eval=None, exploratory=False):
    """Resume terminal pairs; invoke the CLI gate immediately before the first EVAL read."""
    job = Path(job)
    sels = check_selections(job)
    if (not methods or len(set(methods)) != len(methods) or "X0" not in methods
            or not set(methods) <= set(sels["methods"])):
        raise BenchGateError("ORDER_VIOLATION", "unique frozen methods including X0 required")
    if sorted(seeds) != [0, 1, 2]:
        raise BenchGateError("ORDER_VIOLATION", "training seeds must be 0,1,2")
    plan = [(method, seed, _tokens(sels, method, seed)) for method in methods for seed in seeds]
    pool_split = read_table(require(job / "bench/bench_split.parquet"), "bench_split")
    index = read_table(require(job / "lidar/index.parquet"), "lidar_index")
    pool = set(index.loc[index.scene_token.isin(pool_split.loc[
        pool_split.bench_split == "POOL", "scene_token"]), "sample_token"])
    if any(not set(tokens) <= pool for _, _, tokens in plan):
        raise BenchGateError("ORDER_VIOLATION", "training selections must belong to POOL")
    from c4.bench.gate import open_once

    context = _DATA_ROOT.set(Path(data_root) if data_root is not None else None)
    # resume sau ngắt: marker đã ghi ở lần mở đầu, report chưa có ⇒ KHÔNG mở lại cổng EVAL
    resuming = (job / "bench/eval_opened.json").is_file() and not (
        job / "bench/report/report_train.json").is_file()
    runs, failed, opened = {method: [] for method in methods}, 0, resuming
    try:
        for method, seed, tokens in plan:
            out = job / "bench/train" / f"{method}_s{seed}"
            done = out / "done.json"
            if done.is_file():
                result = json.loads(done.read_text(encoding="utf-8"))
                if (result["seed"] != seed or result["tokens"] != tokens
                        or result["recipe"] != RECIPE):
                    raise BenchGateError("ORDER_VIOLATION", f"resume mismatch: {done}")
            else:
                try:
                    ckpt = finetune(job, tokens, seed, out)
                    if not opened:
                        (open_eval or (lambda: open_once(job, "eval")))()
                        opened = True
                    result = dict(seed=seed, tokens=tokens, recipe=RECIPE, failed=False,
                                  metrics=eval_ap(job, ckpt))
                except BenchGateError as exc:
                    if exc.code != "NAN_LOSS":
                        raise
                    result = dict(seed=seed, tokens=tokens, recipe=RECIPE, failed=True,
                                  error=str(exc))
                _write_json(done, result)
            failed += int(result["failed"])
            runs[method].append(result)
            if failed > 1:
                raise BenchGateError("TRAIN_FAILED", "more than one failed training pair")
        # A complete resume is allowed, but still cannot silently reopen the EVAL gate.
        if not opened:
            (open_eval or (lambda: open_once(job, "eval")))()
        baseline_file = job / "bench/train/baseline.json"
        if baseline_file.is_file():
            baseline = json.loads(baseline_file.read_text(encoding="utf-8"))
        else:
            baseline = eval_ap(job, None)
            _write_json(baseline_file, baseline)
        good = {m: [r["metrics"] for r in rs if not r["failed"]] for m, rs in runs.items()}
        summary = {}
        for method, metrics in good.items():
            values = [r["ap50_vru"] for r in metrics if r["ap50_vru"] is not None]
            summary[method] = dict(n_success=len(metrics),
                                   mean_ap50_vru=float(np.mean(values)) if values else None,
                                   seed_std=float(np.std(values, ddof=1)) if len(values) > 1 else None,
                                   delta_vs_X0=bootstrap_delta(metrics, good["X0"]))
            summary[method]["metrics"] = {}
            for key in ("ap50_vru", "ap50_vehicle", "ap50_vru_hard"):
                vals = [r[key] for r in metrics if r.get(key) is not None]
                summary[method]["metrics"][key] = dict(
                    mean=float(np.mean(vals)) if vals else None,
                    seed_std=float(np.std(vals, ddof=1)) if len(vals) > 1 else None)
        competitors = [m for m in methods if m not in {"OURS", "X0"}
                       and summary[m]["mean_ap50_vru"] is not None]
        best = max(competitors, key=lambda m: summary[m]["mean_ap50_vru"]) if competitors else None
        phase3_file = job / "bench/report/report_judge.json"
        phase3 = (json.loads(phase3_file.read_text(encoding="utf-8"))
                  if phase3_file.is_file() else {})
        ours_lo = summary.get("OURS", {}).get("delta_vs_X0", {}).get("lo")
        report = dict(schema="bench-train/1", label="exploratory" if exploratory else
                      phase3.get("label", "preliminary"), recipe=RECIPE, B=sels["B"],
                      steps=training_steps(sels["B"]), runs=runs, methods=summary,
                      baseline=baseline, failed_pairs=failed, strongest_third_party=best,
                      delta_ours_vs_third_party=(bootstrap_delta(good.get("OURS", []), good[best])
                                                 if best else None),
                      strong_win=bool(not exploratory and failed == 0
                                      and ours_lo is not None and ours_lo > 0
                                      and phase3.get("verdict", {}).get("win", False)))
        path = job / "bench/report/report_train.json"
        _write_json(path, report)
        return dict(report=str(path), failed_pairs=failed, strong_win=report["strong_win"])
    finally:
        _DATA_ROOT.reset(context)
