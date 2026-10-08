"""L1: python -m c4.cli.lidar_t0 --data-root D --job-dir J
→ lidar/{desc_raw.npz, filter.parquet, z0.npy}, media/bev/*.png, progress/t0.json.

Mã thoát: 0 ok · 2 vi phạm contract · 4 thiếu file đầu vào / không có frame hợp lệ.
"""
import sys
from pathlib import Path

import numpy as np

from c4.cli.build_index import make_parser
from c4.contracts import ContractError, read_table
from c4.lidar import load_lidar_config
from c4.lidar.extract import StageProgress, embed_split, extract_all


def main(argv=None) -> int:
    for st in (sys.stdout, sys.stderr):  # Windows cp1252 làm crash khi in tiếng Việt
        st.reconfigure(encoding="utf-8", errors="replace")
    args = make_parser(__doc__.splitlines()[0]).parse_args(argv)
    job = Path(args.job_dir)
    lid = job / "lidar"
    try:
        index = read_table(lid / "index.parquet", "lidar_index")
        if args.resume and (lid / "z0.npy").is_file() and (lid / "filter.parquet").is_file():
            print(f"skip: {lid / 'z0.npy'} đã có (--resume)")
            return 0
        cfg = load_lidar_config()
        raw, filt = extract_all(index, args.data_root, lid, cfg, n_jobs=-1,
                                progress=StageProgress(job, "t0", len(index)),
                                bev_dir=job / "media" / "bev")
        keep = filt["keep"].to_numpy(bool)
    except FileNotFoundError as e:
        print(f"thiếu đầu vào: {e}", file=sys.stderr)
        return 4
    except ContractError as e:
        print(f"vi phạm contract: {e}", file=sys.stderr)
        return 2
    if keep.sum() < 2:
        print("Không có frame LiDAR hợp lệ", file=sys.stderr)
        return 4
    z0 = embed_split(raw, keep, cfg)
    np.save(lid / "z0.npy", z0)
    print(f"t0: {int(keep.sum())}/{len(keep)} frame · z0 {z0.shape} → {lid / 'z0.npy'}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
