"""S1: python -m c4.cli.extract_dino --job-dir J --data-root D [--profile P --resume --limit N]
→ cache/dino_cls.npy + cache/feat_dino.parquet.

Mã thoát: 0 ok · 2 vi phạm contract · 3 hết VRAM ở batch 1 · 4 thiếu file đầu vào/trọng số.
"""
import sys

from c4.cli.build_index import make_parser
from c4.contracts import ContractError
from c4.extract.dino import extract_dino


def main(argv=None) -> int:
    args = make_parser(__doc__.splitlines()[0]).parse_args(argv)
    try:
        feat = extract_dino(args.job_dir, args.data_root, profile=args.profile,
                            resume=args.resume, limit=args.limit, device=args.device)
    except FileNotFoundError as e:
        print(f"thiếu đầu vào: {e}", file=sys.stderr)
        return 4
    except ContractError as e:
        print(f"vi phạm contract: {e}", file=sys.stderr)
        return 2
    print(f"dino: {len(feat)} ảnh → {args.job_dir}/cache/dino_cls.npy")
    return 0


if __name__ == "__main__":
    sys.exit(main())
