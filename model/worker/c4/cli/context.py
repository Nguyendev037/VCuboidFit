"""Tầng bối cảnh: python -m c4.cli.context cv --job-dir J --data-root D [--limit N] [--workers K]
→ cache/quality_cv.parquet (C1). `fit`, `run` sẽ thêm ở gói sau.

Mã thoát (OPERATIONS §2): 0 ok · 2 thiếu đầu vào · 3 config sai · 1 lỗi khác.
"""
import argparse
import sys
from pathlib import Path

from c4.contracts import ContractError


def make_parser() -> argparse.ArgumentParser:
    ap = argparse.ArgumentParser(prog="c4.cli.context", description=__doc__.splitlines()[0])
    sub = ap.add_subparsers(dest="cmd", required=True)
    cv = sub.add_parser("cv", help="C1: đặc trưng OpenCV → cache/quality_cv.parquet")
    cv.add_argument("--job-dir", required=True)
    cv.add_argument("--data-root", required=True, help="thư mục chứa samples/")
    cv.add_argument("--limit", type=int, default=None)
    cv.add_argument("--workers", type=int, default=0)
    return ap


def _cmd_cv(args) -> int:
    from c4.context.quality_cv import extract_quality_cv
    df = extract_quality_cv(Path(args.job_dir), Path(args.data_root),
                            limit=args.limit, workers=args.workers)
    bad = int((~df["img_ok"]).sum())
    print(f"quality_cv: {len(df)} ảnh ({bad} hỏng) → {args.job_dir}/cache/quality_cv.parquet")
    return 0


def main(argv=None) -> int:
    args = make_parser().parse_args(argv)
    try:
        return {"cv": _cmd_cv}[args.cmd](args)
    except FileNotFoundError as e:
        print(f"thiếu đầu vào: {e}", file=sys.stderr)
        return 2
    except ContractError as e:
        print(f"vi phạm contract: {e}", file=sys.stderr)
        return 2
    except Exception as e:  # noqa: BLE001 — mã 1 = lỗi khác
        print(f"lỗi: {type(e).__name__}: {e}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
