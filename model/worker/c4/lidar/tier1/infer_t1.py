"""M5 · suy luận model seed trên MỌI keyframe: z1 (BEV pooled), box gốc + box lật, tín hiệu
Tầng 1 và mAP seed trên T (SPEC-P02 §3). Chạy TRONG image vcf-tier1 sau train_seed.

python -m c4.lidar.tier1.infer_t1 --exp /exp [--batch 4]
Mã thoát: 0 ok · 2 contract · 3 không có GPU · 4 thiếu file.
"""
import argparse
import json
import logging
import pickle
import sys
from pathlib import Path

import numpy as np
import pandas as pd

from c4.contracts import write_table

log = logging.getLogger("c4.tier1")


def empty_pred(token: str) -> dict:
    return dict(sample_token=token, boxes=np.zeros((0, 7), np.float32),
                labels=np.zeros(0, np.int32), scores=np.zeros(0, np.float32))


def unflip(boxes: np.ndarray) -> np.ndarray:
    """Box dự đoán trên point cloud lật y → về hệ gốc: y → −y, yaw → −yaw, vy → −vy."""
    b = np.array(boxes, np.float32, copy=True)
    if len(b):
        b[:, 1] *= -1
        b[:, 6] *= -1
        if b.shape[1] >= 9:
            b[:, 8] *= -1
    return b


def run_pass(model, dataset, loader, flip: bool, score_thr: float, keep_annos: set):
    """Một lượt suy luận. Trả (preds theo token, z1 theo token, det_annos của token ∈ keep)."""
    import torch
    from pcdet.models import load_data_to_gpu

    orig_get = dataset.get_lidar_with_sweeps

    def flipped(index, max_sweeps=1):
        pts = orig_get(index, max_sweeps=max_sweeps)
        pts[:, 1] *= -1
        return pts

    dataset.get_lidar_with_sweeps = flipped if flip else orig_get
    feats = {}
    hook = model.backbone_2d.register_forward_hook(
        lambda m, i, out: feats.__setitem__("z", out["spatial_features_2d"].mean(dim=(2, 3))))
    preds, z1, annos = {}, {}, []
    np.random.seed(0)  # chọn sweep + shuffle_points tất định
    try:
        with torch.no_grad():
            for batch in loader:
                load_data_to_gpu(batch)
                pred_dicts, _ = model(batch)
                z = feats["z"].float().cpu().numpy()
                for i, pd_ in enumerate(pred_dicts):
                    tok = batch["metadata"][i]["token"]
                    sc = pd_["pred_scores"].cpu().numpy()
                    k = sc >= score_thr
                    boxes = pd_["pred_boxes"].cpu().numpy()[k]
                    if flip:
                        boxes = unflip(boxes)
                    preds[tok] = dict(sample_token=tok, boxes=boxes[:, :7].astype(np.float32),
                                      labels=pd_["pred_labels"].cpu().numpy()[k].astype(np.int32),
                                      scores=sc[k].astype(np.float32))
                    z1[tok] = z[i]
                if not flip and keep_annos:
                    for a in dataset.generate_prediction_dicts(batch, pred_dicts,
                                                               dataset.class_names):
                        if a["metadata"]["token"] in keep_annos:
                            annos.append(a)
    finally:
        hook.remove()
        dataset.get_lidar_with_sweeps = orig_get
    return preds, z1, annos


def seed_eval(dataset, annos, out_dir: Path) -> dict | None:
    """mAP/NDS của model seed trên T bằng evaluation của OpenPCDet (nuscenes-devkit)."""
    if not annos or not any(len(a["name"]) for a in annos):
        return dict(error="model seed không dự đoán box nào trên T (cold start)")
    try:
        res_str, res = dataset.evaluation(annos, dataset.class_names, output_path=out_dir)
        (out_dir / "seed_eval.txt").write_text(res_str, encoding="utf-8")
        return {k: float(v) for k, v in res.items() if isinstance(v, (int, float))}
    except Exception as e:  # noqa: BLE001 — eval hỏng không được chặn tín hiệu Tầng 1
        return dict(error=f"{type(e).__name__}: {e}")


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--exp", type=Path, default=Path("/exp"))
    ap.add_argument("--batch", type=int, default=4)
    a = ap.parse_args(argv)
    import torch

    from c4.lidar.tier1.repro import set_determinism
    set_determinism(0)

    if not torch.cuda.is_available():
        print("cần GPU", file=sys.stderr)
        return 3
    from easydict import EasyDict
    from pcdet.config import cfg_from_yaml_file
    from pcdet.datasets import build_dataloader
    from pcdet.models import build_network

    from c4.lidar import load_lidar_config
    from c4.lidar.t1_signals import compute_t1_signals

    t1 = a.exp / "t1"
    cfg_p, ckpt = t1 / "cfg" / "pp_seed.yaml", t1 / "ckpt" / "seed_latest.pth"
    for p in (cfg_p, ckpt, a.exp / "index.parquet"):
        if not p.is_file():
            print(f"thiếu {p}", file=sys.stderr)
            return 4
    logging.basicConfig(level=logging.INFO)
    import os

    cwd = os.getcwd()
    os.chdir(os.environ.get("PCDET_ROOT", "/opt/OpenPCDet") + "/tools")  # cfg cũ còn _BASE_CONFIG_
    try:
        cfg = cfg_from_yaml_file(str(cfg_p.resolve()), EasyDict())
    finally:
        os.chdir(cwd)
    sweeps = cfg.DATA_CONFIG.MAX_SWEEPS
    cfg.DATA_CONFIG.INFO_PATH["test"] = [str(t1 / "pcdet" / f"infos_index_{sweeps}sweeps.pkl")]
    index = pd.read_parquet(a.exp / "index.parquet")
    tokens = index["sample_token"].tolist()
    dataset, loader, _ = build_dataloader(
        dataset_cfg=cfg.DATA_CONFIG, class_names=cfg.CLASS_NAMES, batch_size=a.batch, dist=False,
        workers=0, training=False, logger=log)
    model = build_network(model_cfg=cfg.MODEL, num_class=len(cfg.CLASS_NAMES), dataset=dataset)
    model.load_params_from_file(filename=str(ckpt), logger=log, to_cpu=False)
    model.cuda().eval()
    lcfg = load_lidar_config()
    thr = lcfg["t1"]["score_thr"]
    test_toks = set(index.loc[index["split"] == "T", "sample_token"])
    po, zo, annos = run_pass(model, dataset, loader, False, thr, test_toks)
    pf, _, _ = run_pass(model, dataset, loader, True, thr, set())
    missing = [t for t in tokens if t not in po or t not in pf]
    if missing:  # điền 0 sẽ cho Nov = min‖z_seed‖ giả ⇒ frame lỗi lên top; dừng thay vì đoán
        print(f"vi phạm contract: {len(missing)} frame của index không có info/preds "
              f"(vd {missing[:3]})", file=sys.stderr)
        return 2
    dim = len(next(iter(zo.values())))
    preds_o = [po.get(t, empty_pred(t)) for t in tokens]
    preds_f = [pf.get(t, empty_pred(t)) for t in tokens]
    z1 = np.stack([zo.get(t, np.zeros(dim, np.float32)) for t in tokens]).astype(np.float32)
    for name, obj in (("preds_orig.pkl", preds_o), ("preds_flip.pkl", preds_f)):
        with open(t1 / name, "wb") as f:
            pickle.dump(obj, f, protocol=4)
    np.save(t1 / "z1.npy", z1)
    sig = compute_t1_signals(index, preds_o, preds_f, z1, (index["split"] == "S").to_numpy(), lcfg)
    write_table(sig, str(t1 / "signals.parquet"), "t1_signals",
                missing=len([t for t in tokens if t not in po]))
    ev = seed_eval(dataset, annos, t1)
    (t1 / "seed_eval.json").write_text(json.dumps(ev, indent=1), encoding="utf-8")
    print(json.dumps(dict(frames=len(tokens), with_pred=len(po), z1_dim=dim,
                          mean_det=float(sig["n_det"].mean()), seed_eval=ev), ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
