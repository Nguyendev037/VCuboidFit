"""S4: python -m c4.cli.merge_features --job-dir J --data-root D [--profile P]
→ cache/features_cache.parquet (frames + feat_dino + feat_det + feat_clip, thêm q_ok).

Mã thoát: 0 ok · 2 vi phạm contract · 4 thiếu file đầu vào.
"""
import sys
from pathlib import Path

import numpy as np
import pandas as pd

from c4.cli.build_index import make_parser
from c4.config import load_config
from c4.contracts import FEATURES_CACHE, ContractError, read_table, validate, write_table

KEY = ["sample_token", "cam"]
FRAME_COLS = ["scene_token", "split", "frame_idx", "img_path"]
PARTS = dict(  # tên bảng trung gian -> cột lấy vào features_cache
    feat_dino=["emb_row", "nov_knn", "q_bright", "q_blur"],
    feat_det=["det_n", "det_n_conf", "det_ent", "det_tmp", "unc"],
    feat_clip=["qry_max", "qry_best"])


def _rows(path: Path) -> int:
    if not path.is_file():
        raise FileNotFoundError(f"thiếu {path} (chạy stage trước)")
    return int(np.load(path, mmap_mode="r").shape[0])


def _part(cache: Path, name: str, frames: pd.DataFrame) -> pd.DataFrame:
    path = cache / f"{name}.parquet"
    if not path.is_file():
        raise FileNotFoundError(f"thiếu {path} (chạy stage trước)")
    df = pd.read_parquet(path)
    missing = [c for c in KEY + PARTS[name] if c not in df.columns]
    if missing:
        raise ContractError(f"{name}: thiếu cột {missing}")
    if len(df) != len(frames):
        raise ContractError(f"{name}: {len(df)} dòng ≠ frames {len(frames)}")
    if df.duplicated(KEY).any():
        raise ContractError(f"{name}: trùng khóa {KEY}")
    return df[KEY + PARTS[name]]


def merge_features(job_dir, cfg=None) -> pd.DataFrame:
    """Gộp bảng trung gian theo (sample_token, cam), ghi cache/features_cache.parquet, trả bảng."""
    job = Path(job_dir)
    cache = job / "cache"
    cfg = cfg or load_config()
    frames_path = job / "index" / "frames.parquet"
    if not frames_path.is_file():
        raise FileNotFoundError(f"thiếu {frames_path} (chạy c4.cli.build_index trước)")
    frames = read_table(frames_path, "frames")
    n_dino, n_clip = _rows(cache / "dino_cls.npy"), _rows(cache / "clip_img.npy")
    if not len(frames) == n_dino == n_clip:
        raise ContractError(f"số dòng không khớp: frames={len(frames)} dino_cls={n_dino} "
                            f"clip_img={n_clip}")

    out = frames[KEY + FRAME_COLS]
    for name in PARTS:
        out = out.merge(_part(cache, name, frames), on=KEY, how="left", validate="1:1")
    if out.isna().any().any():
        raise ContractError(f"features_cache: thiếu dòng khi ghép theo {KEY}")
    if not (out["emb_row"].to_numpy() == np.arange(len(out))).all():
        raise ContractError("emb_row không trùng thứ tự dòng của frames")
    out["q_ok"] = ((out["q_bright"] >= cfg.quality["min_luma"])
                   & (out["q_blur"] >= cfg.quality["min_blur_var"]) & (out["det_n"] >= 1))
    out = validate(out[list(FEATURES_CACHE)], "features_cache")
    write_table(out, cache / "features_cache.parquet", "features_cache", n_images=len(out))
    return out


def main(argv=None) -> int:
    args = make_parser(__doc__.splitlines()[0]).parse_args(argv)
    try:
        out = merge_features(args.job_dir, load_config(args.profile))
    except FileNotFoundError as e:
        print(f"thiếu đầu vào: {e}", file=sys.stderr)
        return 4
    except ContractError as e:
        print(f"vi phạm contract: {e}", file=sys.stderr)
        return 2
    print(f"merge: {len(out)} ảnh · {int(out['q_ok'].sum())} q_ok → "
          f"{args.job_dir}/cache/features_cache.parquet")
    return 0


if __name__ == "__main__":
    sys.exit(main())
