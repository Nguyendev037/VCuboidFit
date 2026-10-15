"""Chấm một checkpoint PointPillars trên một split của index (mặc định T = VAL giữ lại) bằng
nuscenes-devkit (mAP/NDS, detection_cvpr_2019). Chạy TRONG image vcuboidfit_pointpillars.

python -m c4.lidar.tier1.eval_ckpt --ckpt /w/seed_latest.pth --cfg /w/pp_seed.yaml \
    --index /w/index.parquet --nusc /nusc --out /exp/eval_e6 [--split T] [--batch 2]

Devkit mặc định đòi dự đoán phủ TOÀN BỘ split chính thức (val = 6019 frame) ⇒ ở đây GT được
lọc về đúng các sample của split chấm (subset eval) — con số KHÔNG phải full-val mAP/NDS.
Infos chỉ dựng cho các sample cần chấm (không quét cả trainval).
Mã thoát: 0 ok · 2 contract (split rỗng / thiếu lidar) · 3 không có GPU · 4 thiếu file.
"""
import argparse
import json
import logging
import os
import pickle
import sys
import time
from pathlib import Path

import pandas as pd

log = logging.getLogger("c4.tier1.eval")


def build_subset_infos(nusc_root: Path, version: str, tokens: set, sweeps: int, out: Path) -> Path:
    from nuscenes.nuscenes import NuScenes
    from pcdet.datasets.nuscenes import nuscenes_utils

    nu = NuScenes(version=version, dataroot=str(nusc_root), verbose=False)
    nu.sample = [s for s in nu.sample if s["token"] in tokens]  # chỉ dựng info cho split chấm
    nu._token2ind["sample"] = {s["token"]: i for i, s in enumerate(nu.sample)}  # get() dùng chỉ mục
    scenes = {s["scene_token"] for s in nu.sample}
    infos, _ = nuscenes_utils.fill_trainval_infos(
        data_path=nusc_root, nusc=nu, train_scenes=scenes, val_scenes=set(), test=False,
        max_sweeps=sweeps, with_cam=False)
    out.parent.mkdir(parents=True, exist_ok=True)
    with open(out, "wb") as f:
        pickle.dump(infos, f)
    return out


def restrict_gt_to(tokens: set) -> None:
    """Vá load_gt của devkit: giữ GT của đúng các sample được chấm (subset eval)."""
    from nuscenes.eval.common.data_classes import EvalBoxes
    from nuscenes.eval.detection import evaluate

    orig = evaluate.load_gt

    def load_gt_subset(*args, **kwargs):
        full = orig(*args, **kwargs)
        sub = EvalBoxes()
        for t in full.sample_tokens:
            if t in tokens:
                sub.add_boxes(t, full[t])
        return sub

    evaluate.load_gt = load_gt_subset


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--ckpt", type=Path, required=True)
    ap.add_argument("--cfg", type=Path, required=True, help="pp_seed.yaml đi kèm trọng số")
    ap.add_argument("--index", type=Path, required=True)
    ap.add_argument("--split", default="T")
    ap.add_argument("--nusc", type=Path, default=Path("/nusc"))
    ap.add_argument("--out", type=Path, required=True)
    ap.add_argument("--batch", type=int, default=2)
    a = ap.parse_args(argv)
    import torch

    from c4.lidar.tier1.repro import set_determinism
    set_determinism(0)
    if not torch.cuda.is_available():
        print("cần GPU", file=sys.stderr)
        return 3
    for p in (a.ckpt, a.cfg, a.index):
        if not p.is_file():
            print(f"thiếu {p}", file=sys.stderr)
            return 4
    logging.basicConfig(level=logging.INFO)
    from easydict import EasyDict
    from pcdet.config import cfg_from_yaml_file
    from pcdet.datasets import build_dataloader
    from pcdet.models import build_network, load_data_to_gpu

    from c4.lidar.tier1.infer_t1 import devkit_view
    from c4.lidar.tier1.train_seed import data_root, detect_version

    index = pd.read_parquet(a.index)
    tokens = set(index.loc[index["split"] == a.split, "sample_token"])
    if not tokens:
        print(f"vi phạm contract: split {a.split} rỗng", file=sys.stderr)
        return 2
    a.out.mkdir(parents=True, exist_ok=True)
    cwd = os.getcwd()
    os.chdir(os.environ.get("PCDET_ROOT", "/opt/OpenPCDet") + "/tools")
    try:
        cfg = cfg_from_yaml_file(str(a.cfg.resolve()), EasyDict())
    finally:
        os.chdir(cwd)
    version = detect_version(a.nusc)
    sweeps = cfg.DATA_CONFIG.MAX_SWEEPS
    view = devkit_view(a.out, a.nusc, version)  # thiếu maps/*.png ⇒ mask giả, chỉ để devkit mở
    t0 = time.time()
    p_infos = a.out / "pcdet" / f"infos_{a.split}_{sweeps}sweeps.pkl"
    if not p_infos.is_file():
        build_subset_infos(view, version, tokens, sweeps, p_infos)
    with open(p_infos, "rb") as f:
        got = {i["token"] for i in pickle.load(f)}
    if got != tokens:
        print(f"vi phạm contract: info {len(got)}/{len(tokens)} sample", file=sys.stderr)
        return 2
    t_infos = time.time() - t0
    cfg.DATA_CONFIG.DATA_PATH = str(data_root(a.out, view, version))
    cfg.DATA_CONFIG.VERSION = version
    cfg.DATA_CONFIG.INFO_PATH = {"train": [], "test": [str(p_infos)]}
    dataset, loader, _ = build_dataloader(
        dataset_cfg=cfg.DATA_CONFIG, class_names=cfg.CLASS_NAMES, batch_size=a.batch, dist=False,
        workers=0, training=False, logger=log)
    model = build_network(model_cfg=cfg.MODEL, num_class=len(cfg.CLASS_NAMES), dataset=dataset)
    model.load_params_from_file(filename=str(a.ckpt), logger=log, to_cpu=False)
    model.cuda().eval()
    annos = []
    t1 = time.time()
    with torch.no_grad():
        for batch in loader:
            load_data_to_gpu(batch)
            pred_dicts, _ = model(batch)
            annos += dataset.generate_prediction_dicts(batch, pred_dicts, dataset.class_names)
    torch.cuda.synchronize()
    t_infer = time.time() - t1
    restrict_gt_to(tokens)
    res_str, res = dataset.evaluation(annos, dataset.class_names, output_path=a.out)
    (a.out / "eval.txt").write_text(res_str, encoding="utf-8")
    summary = dict(ckpt=str(a.ckpt), split=a.split, frames=len(annos), sweeps=sweeps,
                   subset_eval=True, sec_infos=round(t_infos, 1), sec_infer=round(t_infer, 1),
                   ms_per_frame=round(1000 * t_infer / max(len(annos), 1), 1),
                   gpu=torch.cuda.get_device_name(0),
                   max_vram_mb=round(torch.cuda.max_memory_allocated() / 2**20),
                   metrics={k: float(v) for k, v in res.items() if isinstance(v, (int, float))})
    (a.out / "eval_summary.json").write_text(json.dumps(summary, indent=1), encoding="utf-8")
    print(res_str)
    print(json.dumps({k: v for k, v in summary.items() if k != "metrics"}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
