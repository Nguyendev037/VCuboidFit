"""L2: python -m c4.cli.lidar_t1 --job-dir J --data-root D [--resume]
→ t1/signals.parquet (suy luận seed đã train qua Docker; lỗi không chặn job).

Mã thoát: 0 ok hoặc skip có lý do · 2 vi phạm contract · 4 thiếu lidar/index.parquet · 5 Docker lỗi.
"""
import os
import subprocess
import sys
from pathlib import Path

import pandas as pd

from c4.cli.build_index import make_parser
from c4.contracts import ContractError, read_table, write_table

WORKER = Path(__file__).resolve().parents[2]  # .../model/worker


def main(argv=None) -> int:
    for st in (sys.stdout, sys.stderr):  # Windows cp1252 làm crash khi in tiếng Việt
        st.reconfigure(encoding="utf-8", errors="replace")
    args = make_parser(__doc__.splitlines()[0]).parse_args(argv)
    job = Path(args.job_dir)
    out = job / "t1" / "signals.parquet"
    if args.resume and out.is_file():
        print("skip: đã có")
        return 0
    exp_s = os.environ.get("VCF_T1_EXP", "").strip()
    if not exp_s:
        print("skip: VCF_T1_EXP chưa đặt")
        return 0
    exp = Path(exp_s)
    for rel in (("index.parquet",), ("t1", "cfg", "pp_seed.yaml"), ("t1", "ckpt", "seed_latest.pth")):
        p = exp.joinpath(*rel)
        if not p.is_file():
            print(f"skip: thiếu {p}")
            return 0
    try:
        job_idx = read_table(job / "lidar" / "index.parquet", "lidar_index")
    except FileNotFoundError as e:
        print(f"thiếu đầu vào: {e}", file=sys.stderr)
        return 4
    except ContractError as e:
        print(f"vi phạm contract: {e}", file=sys.stderr)
        return 2
    exp_idx = pd.read_parquet(exp / "index.parquet")
    missing = set(job_idx["sample_token"]) - set(exp_idx["sample_token"])
    if missing:
        print(f"skip: {len(missing)} frame của job không có trong thí nghiệm seed")
        return 0
    exp_sig = exp / "t1" / "signals.parquet"
    if not (args.resume and exp_sig.is_file()):
        compose = WORKER.parent / "docker" / "tier1" / "docker-compose.yml"
        env = dict(os.environ, NUSC=str(args.data_root), EXP=str(exp))
        try:
            rc = subprocess.run(["docker", "compose", "-f", str(compose), "run", "--rm", "infer"],
                                env=env).returncode
        except OSError as e:
            print(f"docker lỗi ({e})", file=sys.stderr)
            return 5
        if rc != 0:
            print(f"docker lỗi ({rc})", file=sys.stderr)
            return 5
    try:
        sig = read_table(exp_sig, "t1_signals")
    except FileNotFoundError as e:
        print(f"docker lỗi: không có {e}", file=sys.stderr)
        return 5
    except ContractError as e:
        print(f"vi phạm contract: {e}", file=sys.stderr)
        return 2
    sig = sig.drop_duplicates("sample_token").set_index("sample_token")
    toks = job_idx["sample_token"].tolist()
    if any(t not in sig.index for t in toks):
        print("vi phạm contract: thiếu sample_token trong signals", file=sys.stderr)
        return 2
    sig = sig.reindex(toks).reset_index()
    (job / "t1").mkdir(parents=True, exist_ok=True)
    try:
        write_table(sig, str(out), "t1_signals")
    except ContractError as e:
        print(f"vi phạm contract: {e}", file=sys.stderr)
        return 2
    print(f"t1: {len(sig)} frame → {out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
