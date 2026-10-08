"""Thí nghiệm LiDAR (PDF §6): python -m c4.cli.lidar_experiment --data-root D --out runs/mini
[--split V] [--tune] [--bootstrap 200] [--n-jobs -1]

--split P chỉ chạy khi có configs/final.yaml (tham số đã đóng băng, cổng G4) và đúng MỘT lần
(đã có <out>/P/metrics.json ⇒ từ chối). Mã thoát: 0 ok · 2 contract · 3 vi phạm cổng · 4 thiếu file.
"""
import argparse
import json
import sys
import time
from pathlib import Path

import yaml

from c4.config import CONFIG_DIR
from c4.contracts import ContractError
from c4.lidar import load_gt_config, load_lidar_config
from c4.lidar.experiment import prepare, run_split


def main(argv=None) -> int:
    for s in (sys.stdout, sys.stderr):
        s.reconfigure(encoding="utf-8", errors="replace")
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--data-root", required=True)
    ap.add_argument("--out", required=True, type=Path)
    ap.add_argument("--split", default="V", choices=["V", "P", "S", "T", "pool"])
    ap.add_argument("--tune", action="store_true", help="dò lưới trên split này (chỉ V)")
    ap.add_argument("--bootstrap", type=int, default=0)
    ap.add_argument("--n-jobs", type=int, default=-1)
    args = ap.parse_args(argv)
    cfg, gcfg = load_lidar_config(), load_gt_config()
    params = None
    if args.split == "P":
        final = CONFIG_DIR / "final.yaml"
        if not final.is_file():
            print("Cổng G4: chưa có configs/final.yaml — KHÔNG chấm P trước khi đóng băng",
                  file=sys.stderr)
            return 3
        if (args.out / "P" / "metrics.json").is_file():
            print("P đã được chấm một lần — không chấm lại (PDF §5.3)", file=sys.stderr)
            return 3
        params = yaml.safe_load(final.read_text(encoding="utf-8"))["params"]
        args.tune = False
    if args.tune and args.split != "V":
        print("Chỉ tune trên V", file=sys.stderr)
        return 3
    t0 = time.time()
    try:
        prepare(args.data_root, args.out, cfg, gcfg, n_jobs=args.n_jobs)
        t1 = time.time()
        r = run_split(args.out, args.split, cfg, params, args.tune, args.bootstrap)
    except FileNotFoundError as e:
        print(f"thiếu đầu vào: {e}", file=sys.stderr)
        return 4
    except ContractError as e:
        print(f"vi phạm contract: {e}", file=sys.stderr)
        return 2
    print(json.dumps(dict(split=args.split, B=r["B"], params=r["params"],
                          prepare_s=round(t1 - t0, 1), select_eval_s=round(time.time() - t1, 1)),
                     ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
