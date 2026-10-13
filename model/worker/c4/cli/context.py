"""Tầng bối cảnh: python -m c4.cli.context cv --job-dir J --data-root D [--limit N] [--workers K]
→ cache/quality_cv.parquet (C1).
        fit --job-dir J --split V [--split-manifest S.csv] [--data-root D] [--out P]
→ cache/context_thresholds_v1.json (chỉ nhận V).
        run --job-dir J --data-root D [--profile multisensor] [--thresholds P]
→ cache/context_frame.parquet (C0+C1+C2+C3; chưa có ngưỡng ⇒ tag null).

Mã thoát (OPERATIONS §2): 0 ok · 2 thiếu đầu vào · 3 config sai · 1 lỗi khác.
"""
import argparse
import sys
from pathlib import Path

from c4.context.clip_axes import ContextConfigError
from c4.contracts import ContractError


def make_parser() -> argparse.ArgumentParser:
    ap = argparse.ArgumentParser(prog="c4.cli.context", description=__doc__.splitlines()[0])
    sub = ap.add_subparsers(dest="cmd", required=True)
    cv = sub.add_parser("cv", help="C1: đặc trưng OpenCV → cache/quality_cv.parquet")
    cv.add_argument("--job-dir", required=True)
    cv.add_argument("--data-root", required=True, help="thư mục chứa samples/")
    cv.add_argument("--limit", type=int, default=None)
    cv.add_argument("--workers", type=int, default=0)
    fit = sub.add_parser("fit", help="C3: fit ngưỡng trên V → cache/context_thresholds_v1.json")
    fit.add_argument("--job-dir", required=True)
    fit.add_argument("--split", required=True, help="chỉ nhận V")
    fit.add_argument("--split-manifest", default=None, help="mặc định <job-dir>/split_manifest.csv")
    fit.add_argument("--data-root", default=None, help="có ⇒ tính sun_elev để fit night_v_mean")
    fit.add_argument("--out", default=None)
    run = sub.add_parser("run", help="C0+C1+C2+C3 → cache/context_frame.parquet")
    run.add_argument("--job-dir", required=True)
    run.add_argument("--data-root", required=True)
    run.add_argument("--profile", default="multisensor", choices=["multisensor", "lidar_only"])
    run.add_argument("--thresholds", default=None)
    return ap


def _cmd_fit(args) -> int:
    from c4.context import pipeline
    manifest = args.split_manifest or str(Path(args.job_dir) / "split_manifest.csv")
    thr, sha, path = pipeline.fit_context(
        args.job_dir, args.split, manifest, data_root=args.data_root, out=args.out,
        encoder=pipeline.default_text_encoder())
    print(f"thresholds: n_frames={thr['n_frames']} clip_pct={thr['clip_margin_pct']} "
          f"sha256={sha[:12]} → {path}")
    if thr["cv"]["night_v_mean"] == 0.0:
        print("cảnh báo: không có frame đêm (sun_elev < -6) trên V ⇒ NIGHT_CV tắt", file=sys.stderr)
    return 0


def _cmd_run(args) -> int:
    from c4.context import pipeline
    df = pipeline.run_context(args.job_dir, args.data_root, profile=args.profile,
                              thresholds_path=args.thresholds)
    warn = df.attrs.get("warningCodes", [])
    print(f"context_frame: {len(df)} hàng · review={int(df['review'].sum()) if len(df) else 0} "
          f"· warnings={warn} → {args.job_dir}/cache/context_frame.parquet")
    return 0


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
        return {"cv": _cmd_cv, "fit": _cmd_fit, "run": _cmd_run}[args.cmd](args)
    except ContextConfigError as e:
        print(f"config sai: {e}", file=sys.stderr)
        return 3
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
