#!/usr/bin/env python3
"""Chạy pipeline M0→M5 trên nguồn dữ liệu thật.

Ví dụ:
  # nuScenes (cần nuscenes-devkit + dữ liệu):
  python scripts/run_pipeline.py --source nuscenes --dataroot /data/nuScenes \
      --version v1.0-mini --budget 200 --out outputs_nuscenes

  # data công ty (thư mục .npy/.bin + meta.json + gt.json tuỳ chọn):
  python scripts/run_pipeline.py --source bindir --dataroot /data/company_lidar --budget 200
"""
import argparse
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from rare_mining import PipelineConfig, run_pipeline  # noqa: E402
from rare_mining.m5_select import frame_reasons  # noqa: E402


def main():
    ap = argparse.ArgumentParser(description="Rare-frame mining pipeline (M0-M5)")
    ap.add_argument("--source", required=True, choices=["synthetic", "bindir", "nuscenes"])
    ap.add_argument("--dataroot", default="")
    ap.add_argument("--version", default="v1.0-mini")
    ap.add_argument("--split", default="auto",
                    help="auto = val chính thức (trainval) / mini_val (mini); all; hoặc tên split nuScenes")
    ap.add_argument("--model-provenance", default="", choices=["", "nuscenes_train", "seed", "external"],
                    help="model train trên gì: nuscenes_train (checkpoint công khai, mặc định) | seed | external")
    ap.add_argument("--model-mode", default="", choices=["", "frozen", "seed"],
                    help="frozen = checkpoint công khai (lõi); seed = model Seed tự train (bước 0 tuỳ chọn)")
    ap.add_argument("--config", default="", help="file JSON ghi đè tham số")
    ap.add_argument("--budget", type=int, default=100)
    ap.add_argument("--out", default="outputs")
    ap.add_argument("--exclude-fids", default="",
                    help="file JSON (list các fid hoặc dict) — frame pilot/đã gán nhãn, "
                         "sẽ bị ép split=PILOT và loại khỏi V/T (chống leak)")
    ap.add_argument("--seed-manifest", default="",
                    help="seed_manifest.json từ train_seed.py — frame Seed bị loại khỏi V/T (bước 0 tuỳ chọn)")
    ap.add_argument("--retrain", action="store_true",
                    help="bật công tắc retrain: frame chọn + gán nhãn sẽ được thêm vào Seed ở vòng sau")
    ap.add_argument("--explore-frac", type=float, default=-1.0,
                    help="phương án B: tỉ lệ (theo B) frame ngẫu nhiên ngoài lô chọn, gán nhãn để train (cần --retrain)")
    ap.add_argument("--max-frames", type=int, default=0)
    ap.add_argument("--tune", default="none", choices=["none", "rule_v"],
                    help="none = label-free (trọng số đều); rule_v = tune trên GT của V (khai báo rõ)")
    ap.add_argument("--detector", default="", choices=["", "heuristic", "mmdet3d", "openpcdet"])
    ap.add_argument("--checkpoint", default="")
    ap.add_argument("--model-config", default="")
    args = ap.parse_args()

    cfg = PipelineConfig.from_json(args.config) if args.config else PipelineConfig()
    cfg.out_dir = args.out
    if args.detector:
        cfg.detector.backend = args.detector
    if args.checkpoint:
        cfg.detector.checkpoint = args.checkpoint
    if args.model_config:
        cfg.detector.config_path = args.model_config
    if args.model_mode:
        cfg.model.mode = args.model_mode
        if args.model_mode == "seed" and not args.model_provenance:
            cfg.model.provenance = "seed"
    if args.model_provenance:
        cfg.model.provenance = args.model_provenance
    if args.retrain:
        cfg.model.retrain = True
    if args.explore_frac >= 0:
        cfg.model.explore_frac = args.explore_frac
    if args.seed_manifest:
        cfg.model.seed_manifest = args.seed_manifest

    if args.source == "synthetic":
        from rare_mining import SyntheticSource
        src = SyntheticSource()
    elif args.source == "bindir":
        from rare_mining import BinDirSource
        src = BinDirSource(args.dataroot)
    else:
        from rare_mining import NuscenesSource
        src = NuscenesSource(args.dataroot, args.version, args.split,
                             model_provenance=cfg.model.provenance)

    exclude = []
    if args.exclude_fids:
        import json
        with open(args.exclude_fids, "r", encoding="utf-8") as f:
            data = json.load(f)
        if isinstance(data, dict) and "pilot_fids" in data:
            exclude = list(data["pilot_fids"])      # file pilot_fids.json của run_pilot batch
        elif isinstance(data, dict):
            exclude = [k for k, v in data.items() if v]  # {"fid": true, ...}
        else:
            exclude = list(data)                      # ["fid", ...]
        print(f"Ledger: loại {len(exclude)} frame (split=PILOT) theo {args.exclude_fids}")
    if cfg.model.seed_manifest:
        import json
        with open(cfg.model.seed_manifest, "r", encoding="utf-8") as f:
            seed_fids = list(json.load(f).get("fids", []))
        exclude = sorted(set(exclude) | set(seed_fids))
        print(f"Seed: loại {len(seed_fids)} frame Seed khỏi V/T theo {cfg.model.seed_manifest}")
    if cfg.model.mode == "seed" and not cfg.model.seed_manifest:
        print("CẢNH BÁO: --model-mode seed nhưng thiếu --seed-manifest → frame Seed có thể lọt vào V/T")
    artifacts = run_pipeline(src, cfg, budget=args.budget,
                             max_frames=args.max_frames or None, tune=args.tune,
                             exclude_fids=exclude)
    print("\n=== TOP 10 FRAME NÊN GÁN NHÃN TRƯỚC (tập T) ===")
    for f in artifacts["ranked_T"][:10]:
        print(f"#{f['rank']:<4} {f['fid']:<28} s={f['s_frame']:.3f} "
              f"[{f['slice_primary']}] {frame_reasons(f, cfg.frame)}")
    print(f"\nĐầu ra đầy đủ: {cfg.out_dir}/frames_ranked_T.csv, objects_T.csv, summary.json")


if __name__ == "__main__":
    main()
