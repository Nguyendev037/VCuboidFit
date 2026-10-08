# python -m c4.cli.select --job-dir PATH · chạy S5-S7 + analysis, in đường dẫn result.json
import argparse
import sys
from pathlib import Path

from c4.config import load_config
from c4.contracts import ContractError
from c4.params import SelectParams
from c4.pipeline import run_selection


def main(argv=None) -> int:
    for stream in (sys.stdout, sys.stderr):
        stream.reconfigure(encoding="utf-8")  # thông báo tiếng Việt không vỡ trên Windows
    ap = argparse.ArgumentParser()
    ap.add_argument("--job-dir", required=True, type=Path)
    ap.add_argument("--budget", type=float, default=0.05)
    ap.add_argument("--preset", default="balanced")
    ap.add_argument("--diversity", default="medium")
    ap.add_argument("--profile", default=None)
    a = ap.parse_args(argv)
    try:
        res = run_selection(a.job_dir, SelectParams(budget=a.budget, preset=a.preset,
                                                    diversity=a.diversity),
                            cfg=load_config(a.profile))
    except FileNotFoundError as e:
        print(f"Thiếu file đầu vào: {e}", file=sys.stderr)
        return 4
    except (ContractError, ValueError) as e:
        print(f"Vi phạm contract: {e}", file=sys.stderr)
        return 2
    print(a.job_dir / "out" / "selections" / res["selectionId"] / "result.json")
    return 0


if __name__ == "__main__":
    sys.exit(main())
