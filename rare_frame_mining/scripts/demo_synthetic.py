#!/usr/bin/env python3
"""Demo END-TO-END không cần nuScenes/GPU: dữ liệu tổng hợp → pipeline M0-M5 → M6.

Chạy:  python scripts/demo_synthetic.py
Kết quả: bảng so sánh Pipeline vs Random vs Rule-only vs Confidence-only,
         theo slice, object-level, yield, bootstrap CI — ghi trong demo_output/.
"""
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from rare_mining import PipelineConfig, SyntheticSource, run_pipeline, evaluate  # noqa: E402
from rare_mining.m6_evaluate import print_report, save_report  # noqa: E402
from rare_mining.m5_select import frame_reasons  # noqa: E402


def main():
    cfg = PipelineConfig()
    cfg.out_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                               "demo_output")
    # demo chạy nhanh: 2 pass TTA thay vì 4
    cfg.tta.rots_deg = (0.0, 15.0)
    cfg.tta.flips = (False,)
    cfg.evalcfg.budgets = (50, 100, 150)

    src = SyntheticSource(n_scenes=8, frames_per_scene=50, seed=0)
    print(f"Demo: {8} scenes x 50 keyframes = 400 frames (synthetic)")
    t0 = time.time()
    artifacts = run_pipeline(src, cfg, budget=100)
    t1 = time.time()
    print(f"\nPipeline M0-M5 xong trong {t1 - t0:.1f}s\n=== TOP 10 FRAME ===")
    for f in artifacts["ranked_T"][:10]:
        print(f"#{f['rank']:<4} {f['fid']:<24} s={f['s_frame']:.3f} "
              f"[{f['slice_primary']:<10}] {frame_reasons(f, cfg.frame)}")

    report = evaluate(artifacts["frames"], artifacts["cands"], cfg, artifacts.get("gate"))
    print_report(report)
    save_report(report, os.path.join(cfg.out_dir, "report.json"))
    print(f"\nFile đầu ra trong {cfg.out_dir}/: frames_ranked_T.csv, objects_T.csv, "
          f"summary.json, report.json, config_used.json")


if __name__ == "__main__":
    main()
