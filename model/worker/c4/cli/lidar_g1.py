"""Bảng đếm cổng G1: python -m c4.cli.lidar_g1 --data-root D --out E [--taus 0.005,0.01,0.02,0.05]
In bảng số frame rare theo τ và tỉ lệ nhóm C theo từng định nghĩa, ghi E/gt/g1_table.csv.
Cần E/index.parquet (chạy lidar_experiment trước). Mã thoát: 0 ok · 4 thiếu file / không có nhãn.
"""
import argparse
import sys
from pathlib import Path

from c4.contracts import read_table
from c4.data.nusc import NuscTables
from c4.lidar import load_gt_config
from c4.lidar.gt import g1_table


def main(argv=None) -> int:
    for st in (sys.stdout, sys.stderr):
        st.reconfigure(encoding="utf-8", errors="replace")
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--data-root", required=True)
    ap.add_argument("--out", required=True, type=Path)
    ap.add_argument("--taus", default="0.005,0.01,0.02,0.05")
    a = ap.parse_args(argv)
    try:
        t = NuscTables.load(a.data_root)
        index = read_table(str(a.out / "index.parquet"), "lidar_index")
    except FileNotFoundError as e:
        print(f"thiếu đầu vào: {e}", file=sys.stderr)
        return 4
    if not t.has_annotations:
        print("dataset không có nhãn", file=sys.stderr)
        return 4
    df = g1_table(t, index, load_gt_config(), tuple(float(x) for x in a.taus.split(",")))
    (a.out / "gt").mkdir(parents=True, exist_ok=True)
    df.to_csv(a.out / "gt" / "g1_table.csv", index=False)
    print(df.to_string(index=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
