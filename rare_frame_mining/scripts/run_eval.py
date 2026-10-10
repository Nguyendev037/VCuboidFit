#!/usr/bin/env python3
"""M6 — Đánh giá trên GT giấu từ artifacts đã lưu bởi run_pipeline.

  python scripts/run_eval.py --out outputs --report outputs/report.json
"""
import argparse
import os
import pickle
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from rare_mining.m6_evaluate import evaluate, print_report, save_report  # noqa: E402


def main():
    ap = argparse.ArgumentParser(description="M6 evaluation trên GT giấu")
    ap.add_argument("--out", default="outputs", help="thư mục outputs của run_pipeline")
    ap.add_argument("--report", default="", help="file report.json xuất ra")
    args = ap.parse_args()

    pkl = os.path.join(args.out, "artifacts.pkl")
    if not os.path.exists(pkl):
        raise SystemExit(f"Không tìm thấy {pkl} — hãy chạy run_pipeline trước.")
    with open(pkl, "rb") as f:
        art = pickle.load(f)

    report = evaluate(art["frames"], art["cands"], art["cfg"], art.get("gate"))
    print_report(report)
    out_path = args.report or os.path.join(args.out, "report.json")
    save_report(report, out_path)
    print(f"\nĐã lưu report: {out_path}")


if __name__ == "__main__":
    main()
