"""S2: python -m c4.cli.extract_det --job-dir J --data-root D [--profile P --resume --limit N]
→ cache/detections.parquet + cache/feat_det.parquet.

Mã thoát: 0 ok · 2 vi phạm contract · 3 hết VRAM ở batch 1 · 4 thiếu file đầu vào/trọng số.
"""
import sys

from c4.cli.build_index import make_parser
from c4.contracts import ContractError
from c4.extract.det import extract_det


def main(argv=None) -> int:
    args = make_parser(__doc__.splitlines()[0]).parse_args(argv)
    try:
        det, feat = extract_det(args.job_dir, args.data_root, profile=args.profile,
                                resume=args.resume, limit=args.limit, device=args.device)
    except FileNotFoundError as e:
        print(f"thiếu đầu vào: {e}", file=sys.stderr)
        return 4
    except ContractError as e:
        print(f"vi phạm contract: {e}", file=sys.stderr)
        return 2
    print(f"det: {len(feat)} ảnh · {len(det)} detection → {args.job_dir}/cache/detections.parquet")
    return 0


if __name__ == "__main__":
    sys.exit(main())
