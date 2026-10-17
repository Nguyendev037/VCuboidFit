"""Convert trusted PandaSet / AV2 sources into a nuScenes-compatible data root."""
import argparse
import json
import sys
from pathlib import Path

from c4.data.adapters.common import AdapterError
from c4.contracts import ContractError


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dataset", required=True, choices=["pandaset", "av2"])
    parser.add_argument("--src", required=True, type=Path)
    parser.add_argument("--out", required=True, type=Path)
    parser.add_argument("--logs", type=Path)
    parser.add_argument("--limit", type=int)
    parser.add_argument("--workers", type=int, default=8)
    args = parser.parse_args(argv)
    try:
        if args.limit is not None and args.limit < 1 or args.workers < 1:
            raise AdapterError("SOURCE_LAYOUT", "limit and workers must be positive", 2)
        if args.dataset == "pandaset" and not sys.flags.isolated:
            raise AdapterError("SOURCE_LAYOUT", "PandaSet requires python -I -m c4.cli.adapt", 2)
        from c4.data.adapters import av2, pandaset
        logs = None if args.logs is None else [s.strip() for s in args.logs.read_text(encoding="utf-8").splitlines() if s.strip()]
        report = {"av2": av2.adapt, "pandaset": pandaset.adapt}[args.dataset](
            args.src, args.out, logs=logs, limit=args.limit, workers=args.workers)
    except AdapterError as exc:
        print(json.dumps(dict(error=exc.code, message=str(exc))), file=sys.stderr)
        return exc.exit_code
    except ContractError as exc:
        print(json.dumps(dict(error="PROJ_FAIL", message=str(exc))), file=sys.stderr)
        return 3
    except (OSError, KeyError, ValueError, TypeError, IndexError) as exc:
        print(json.dumps(dict(error="SOURCE_LAYOUT", message=str(exc))), file=sys.stderr)
        return 2
    print(json.dumps(report, sort_keys=True))
    return 0


if __name__ == "__main__":
    sys.exit(main())
