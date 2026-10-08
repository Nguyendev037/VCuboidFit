"""S0: python -m c4.cli.build_index --data-root D --job-dir J
→ index/frames.parquet + index/cam_poses.parquet, gt/* (chỉ khi có annotation),
media/thumbs/*.webp, media/lidar/*.bin (chỉ khi có LIDAR_TOP).

Mã thoát: 0 ok · 2 vi phạm contract · 4 thiếu file đầu vào.
"""
import argparse
import sys
from pathlib import Path

from c4.config import load_config
from c4.contracts import ContractError, read_table, write_table
from c4.data.index import build_frames, cam_poses
from c4.data.media import export_lidar, make_thumbs
from c4.data.nusc import NuscTables
from c4.data.project import project_boxes
from c4.data.rare_gt import group_frequencies, load_rare_def, rare_flags


def make_parser(description: str) -> argparse.ArgumentParser:
    ap = argparse.ArgumentParser(description=description)
    ap.add_argument("--job-dir", required=True)
    ap.add_argument("--data-root", required=True, help="thư mục chứa v1.0-*/ và samples/")
    ap.add_argument("--profile", default="local-4060", choices=["local-4060", "cloud"])
    ap.add_argument("--resume", action="store_true")
    ap.add_argument("--limit", type=int, default=None, help="chỉ giữ N dòng ảnh đầu tiên")
    ap.add_argument("--device", default="cuda", choices=["cuda", "cpu"])
    return ap


def write_gt(t: NuscTables, frames, job_dir: Path) -> bool:
    """gt/gt_rare + gt_boxes_2d + boxes_3d. Không có annotation ⇒ không ghi gì (trả False)."""
    if not t.has_annotations:
        print("không có sample_annotation/instance: bỏ qua gt/")
        return False
    rare_def = load_rare_def()
    flags = rare_flags(t, frames, rare_def)
    boxes_2d, boxes_3d = project_boxes(t, frames)
    gdir = Path(job_dir) / "gt"
    gdir.mkdir(parents=True, exist_ok=True)
    write_table(flags, gdir / "gt_rare.parquet", "gt_rare",
                group_frequencies=group_frequencies(flags), rare_max_freq=rare_def["rare_max_freq"])
    write_table(boxes_2d, gdir / "gt_boxes_2d.parquet", "gt_boxes_2d")
    write_table(boxes_3d, gdir / "boxes_3d.parquet", "boxes_3d")
    print(f"gt: {len(flags)} frame · {int(flags['is_rare'].sum())} hiếm · "
          f"{len(boxes_2d)} hộp 2D · {len(boxes_3d)} hộp 3D")
    return True


def write_media(t: NuscTables, frames, data_root, job_dir: Path, workers: int) -> None:
    """media/thumbs (mỗi ảnh camera) rồi media/lidar (chỉ khi có LIDAR_TOP); bỏ qua file đã có."""
    mdir = Path(job_dir) / "media"
    n_thumbs = make_thumbs(frames, data_root, mdir / "thumbs", workers=workers)
    n_lidar = export_lidar(t, frames, data_root, mdir / "lidar")
    print(f"media: {n_thumbs} thumbnail mới · {n_lidar} point cloud mới")


def main(argv=None) -> int:
    args = make_parser(__doc__.splitlines()[0]).parse_args(argv)
    job = Path(args.job_dir)
    out = job / "index"
    frames_p, poses_p = out / "frames.parquet", out / "cam_poses.parquet"
    try:
        t = NuscTables.load(args.data_root)
        if args.resume and frames_p.is_file() and poses_p.is_file():
            print(f"skip: {frames_p} đã có (--resume)")
            frames = read_table(frames_p, "frames")
        else:
            frames = build_frames(t, Path(args.data_root))
            if args.limit is not None:
                frames = frames.head(args.limit).reset_index(drop=True)
            poses = cam_poses(t, frames)
            out.mkdir(parents=True, exist_ok=True)
            write_table(frames, frames_p, "frames")
            write_table(poses, poses_p, "cam_poses")
            print(f"frames: {len(frames)} ảnh · {frames['sample_token'].nunique()} frame · "
                  f"{frames['scene_token'].nunique()} scene · cam_poses: {len(poses)}")
        write_gt(t, frames, job)
        write_media(t, frames, args.data_root, job, load_config(args.profile).workers)
    except FileNotFoundError as e:
        print(f"thiếu đầu vào: {e}", file=sys.stderr)
        return 4
    except ContractError as e:
        print(f"vi phạm contract: {e}", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main())
