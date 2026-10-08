"""python -m c4.cli.run_job --data-root D --job-dir J --profile local-4060
Chạy tuần tự index → dino → det → clip → merge dưới khoá GPU; ghi J/status.json.

Mã thoát: 0 job done · mã của stage lỗi (2 contract · 3 hết VRAM · 4 thiếu đầu vào) · 1 khác/huỷ.
"""
import argparse
import sys

from c4.jobs.runner import run_job


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--data-root", required=True, help="thư mục chứa v1.0-*/ và samples/")
    ap.add_argument("--job-dir", required=True)
    ap.add_argument("--profile", default="local-4060", choices=["local-4060", "cloud"])
    args = ap.parse_args(argv)
    try:
        st = run_job(args.job_dir, args.data_root, args.profile)
    except KeyboardInterrupt:
        print("đã huỷ (Ctrl-C)", file=sys.stderr)
        return 1
    print(f"job {st['jobId']}: {st['state']} · stage {st['stage']}")
    if st["state"] == "done":
        return 0
    if st["error"]:
        print(st["error"]["message"], file=sys.stderr)
        return st["error"]["code"] if st["error"]["code"] in (2, 3, 4) else 1
    return 1


if __name__ == "__main__":
    sys.exit(main())
