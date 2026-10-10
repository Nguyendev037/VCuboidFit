#!/usr/bin/env python3
"""M0.5 — Pilot driver (bổ sung cập nhật 10/10).

Hai lệnh:
  # (a) Sanity check model trên tập nhỏ CÓ nhãn → go/no-go:
  python scripts/run_pilot.py sanity --source nuscenes --dataroot /data/nuScenes \
      --version v1.0-mini --n-random 150 --n-strat 50 --out pilot_sanity.json

  # (b) Lô thử nghiệm: chạy pipeline trên ~800 frame, xuất 2 lô gán tay:
  python scripts/run_pilot.py batch --source nuscenes --dataroot /data/nuScenes \
      --version v1.0-mini --n-frames 800 --budget 60 --out pilot_output

Sau khi đội gán tay hoàn thành 2 lô (pilot_labeling_top.csv và
pilot_labeling_random.csv), chạy:
  python scripts/run_eval.py --out pilot_output
→ so yield pipeline vs random để ra quyết định mở rộng toàn pool.

LƯU Ý chống leak: fids trong pilot_output/pilot_fids.json phải được truyền vào
run_pipeline (--exclude-fids) khi chạy FULL POOL sau này → các frame đó bị ép
split='PILOT' và không bao giờ lọt vào tập báo cáo T.
"""
import argparse
import json
import os
import random
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from rare_mining import PipelineConfig, run_pipeline  # noqa: E402
from rare_mining.detectors import make_detector  # noqa: E402
from rare_mining.m05_pilot import pick_pilot, print_sanity, run_sanity  # noqa: E402
from rare_mining.m5_select import frame_reasons  # noqa: E402
from rare_mining.utils import save_csv, save_json  # noqa: E402


def build_source(args, cfg):
    if args.source == "synthetic":
        from rare_mining import SyntheticSource
        return SyntheticSource()
    if args.source == "bindir":
        from rare_mining import BinDirSource
        return BinDirSource(args.dataroot)
    from rare_mining import NuscenesSource
    return NuscenesSource(args.dataroot, args.version, args.split,
                             model_provenance=cfg.model.provenance)


def add_common(ap):
    ap.add_argument("--source", required=True, choices=["synthetic", "bindir", "nuscenes"])
    ap.add_argument("--dataroot", default="")
    ap.add_argument("--version", default="v1.0-mini")
    ap.add_argument("--split", default="auto",
                    help="auto = val chính thức (trainval) / mini_val (mini); all; hoặc tên split nuScenes")
    ap.add_argument("--model-provenance", default="", choices=["", "nuscenes_train", "seed", "external"],
                    help="model train trên gì: nuscenes_train (checkpoint công khai, mặc định) | seed | external")
    ap.add_argument("--model-mode", default="", choices=["", "frozen", "seed"],
                    help="frozen = checkpoint công khai (lõi); seed = model Seed tự train (bước 0 tuỳ chọn)")
    ap.add_argument("--config", default="", help="JSON ghi đè tham số pipeline")
    ap.add_argument("--detector", default="", choices=["", "heuristic", "mmdet3d", "openpcdet"])
    ap.add_argument("--checkpoint", default="")
    ap.add_argument("--model-config", default="")


def make_cfg(args, out_dir: str):
    cfg = PipelineConfig.from_json(args.config) if args.config else PipelineConfig()
    cfg.out_dir = out_dir
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
    return cfg


def main():
    ap = argparse.ArgumentParser(description="M0.5 Pilot: sanity check + lô thử nghiệm")
    sub = ap.add_subparsers(dest="mode", required=True)

    ap_s = sub.add_parser("sanity", help="M0.5a — kiểm định model trên tập nhỏ có nhãn")
    add_common(ap_s)
    ap_s.add_argument("--n-random", type=int, default=150)
    ap_s.add_argument("--n-strat", type=int, default=50)
    ap_s.add_argument("--max-scan", type=int, default=1200)
    ap_s.add_argument("--out", default="pilot_sanity.json")

    ap_b = sub.add_parser("batch", help="M0.5b — lô thử nghiệm + xuất 2 lô gán tay")
    add_common(ap_b)
    ap_b.add_argument("--n-frames", type=int, default=800)
    ap_b.add_argument("--budget", type=int, default=60, help="B' cho MỖI lô (top + random)")
    ap_b.add_argument("--out", default="pilot_output")

    args = ap.parse_args()
    cfg = make_cfg(args, args.out if args.mode == "batch" else "pilot_tmp")

    if args.mode == "sanity":
        src = build_source(args, cfg)
        frames = src.frames()
        det = make_detector(cfg)
        picks = pick_pilot(frames, cfg, args.n_random, args.n_strat,
                           seed=cfg.split.seed, max_scan=args.max_scan)
        fids = picks["random"] + picks["stratified"]
        print(f"Pilot sanity: random={len(picks['random'])} + phân tầng={len(picks['stratified'])} "
              f"= {len(fids)} frame")
        report = run_sanity(frames, fids, det, cfg)
        report["picks"] = picks
        print_sanity(report)
        save_json(report, args.out)
        print(f"\nĐã lưu: {args.out}")
        return

    # --- batch ---
    src = build_source(args, cfg)
    frames = src.frames()
    picks = pick_pilot(frames, cfg, args.n_frames, 0, seed=cfg.split.seed)
    subset = picks["random"]
    if not subset:
        raise SystemExit("Không chọn được frame nào cho pilot batch")
    os.makedirs(args.out, exist_ok=True)
    save_json({"pilot_fids": subset,
               "note": "Truyền file này vào --exclude-fids của run_pipeline FULL RUN chống leak"},
              os.path.join(args.out, "pilot_fids.json"))
    print(f"Pilot batch: {len(subset)} frame → {args.out}/pilot_fids.json")

    artifacts = run_pipeline(src, cfg, budget=args.budget, subset_fids=subset)
    ranked_T = artifacts["ranked_T"]
    top = ranked_T[: args.budget]
    fids_T = [f["fid"] for f in ranked_T]
    rnd = random.Random(cfg.split.seed + 1)
    random_tasks = rnd.sample(fids_T, min(args.budget, len(fids_T)))

    def rows(fs):
        return [{"fid": f["fid"], "scene": f["scene"], "rank": f.get("rank", ""),
                 "s_frame": round(f["s_frame"], 4), "slice": f["slice_primary"],
                 "reasons": frame_reasons(f, cfg.frame),
                 "task": "gán nhãn TẤT CẢ vật thể VRU trong frame"} for f in fs]

    save_csv(rows(top), os.path.join(args.out, "pilot_labeling_top.csv"))
    save_csv([{"fid": fid, "task": "gán nhãn TẤT CẢ vật thể VRU trong frame"}
              for fid in random_tasks],
             os.path.join(args.out, "pilot_labeling_random.csv"))
    print(f"\nĐã xuất 2 lô gán tay: pilot_labeling_top.csv ({len(top)}) + "
          f"pilot_labeling_random.csv ({len(random_tasks)})")
    print("BƯỚC TIẾP: đội gán nhãn xử lý 2 lô → cập nhật gt.json/meta → "
          "chạy `python scripts/run_eval.py --out " + args.out + "` → so yield.")


if __name__ == "__main__":
    main()
