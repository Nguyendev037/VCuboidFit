"""L0: python -m c4.cli.lidar_index --data-root D --job-dir J
→ lidar/index.parquet (keyframe LIDAR_TOP, đã chia S/V/P/T) + gt/gt_rare_lidar.parquet,
gt/cell_freq.csv (chỉ khi dataset có annotation) + phần HIỂN THỊ cho web (không tham gia chọn):
media/lidar/*.bin (point cloud viewer), index/{frames,cam_poses}.parquet + media/thumbs (camera nếu
có), gt/{gt_boxes_2d,boxes_3d}.parquet (hộp nhãn trong viewer, chỉ khi có annotation).

Mã thoát: 0 ok · 2 vi phạm contract · 4 thiếu file đầu vào (kể cả không có LIDAR_TOP).
"""
import sys
from pathlib import Path

from c4.cli.build_index import make_parser
from c4.config import load_config
from c4.contracts import ContractError, read_table, write_table
from c4.data.index import build_frames, cam_poses
from c4.data.media import export_lidar, make_thumbs
from c4.data.nusc import NuscTables
from c4.data.project import project_boxes
from c4.lidar import load_gt_config, load_lidar_config
from c4.lidar.gt import build_gt
from c4.lidar.index import build_lidar_index
from c4.lidar.splits import assign_splits


def write_gt(t: NuscTables, index, job_dir: Path) -> bool:
    """gt/gt_rare_lidar.parquet + gt/cell_freq.csv. Không có annotation ⇒ không ghi (trả False).

    Đúng mẫu `write_gt` của `build_index.py` + `c4.lidar.experiment.prepare`.
    """
    if not t.has_annotations:
        print("không có sample_annotation/instance: bỏ qua gt/")
        return False
    gdir = Path(job_dir) / "gt"
    gdir.mkdir(parents=True, exist_ok=True)
    gcfg = load_gt_config()
    gt, cell_freq = build_gt(t, index, gcfg)
    write_table(gt, gdir / "gt_rare_lidar.parquet", "gt_rare_lidar", tau=gcfg["tau"])
    cell_freq.to_csv(gdir / "cell_freq.csv", index=False)
    print(f"gt lidar: {int(gt['is_rare'].sum())} frame hiếm / {len(gt)} · "
          f"{len(cell_freq)} cell")
    return True


def write_display(t: NuscTables, index, data_root, job_dir: Path, workers: int) -> None:
    """Dữ liệu chỉ để XEM trên web (viewer 3D, ảnh camera, hộp nhãn) — cùng hàm với stage `index`
    của pipeline camera. Engine chọn LiDAR không đọc các file này (test_no_leakage_lidar)."""
    job_dir = Path(job_dir)
    n_lidar = export_lidar(t, index, data_root, job_dir / "media" / "lidar")
    frames = build_frames(t, Path(data_root))
    frames = frames[frames["sample_token"].isin(set(index["sample_token"]))].reset_index(drop=True)
    n_thumbs = 0
    if len(frames):
        idir = job_dir / "index"
        idir.mkdir(parents=True, exist_ok=True)
        write_table(frames, idir / "frames.parquet", "frames")
        write_table(cam_poses(t, frames), idir / "cam_poses.parquet", "cam_poses")
        n_thumbs = make_thumbs(frames, data_root, job_dir / "media" / "thumbs", workers=workers)
        if t.has_annotations:
            b2, b3 = project_boxes(t, frames)
            gdir = job_dir / "gt"
            gdir.mkdir(parents=True, exist_ok=True)
            write_table(b2, gdir / "gt_boxes_2d.parquet", "gt_boxes_2d")
            write_table(b3, gdir / "boxes_3d.parquet", "boxes_3d")
    print(f"hiển thị: {n_lidar} point cloud mới · {len(frames)} ảnh camera · "
          f"{n_thumbs} thumbnail mới")


def main(argv=None) -> int:
    for st in (sys.stdout, sys.stderr):  # Windows cp1252 làm crash khi in tiếng Việt
        st.reconfigure(encoding="utf-8", errors="replace")
    args = make_parser(__doc__.splitlines()[0]).parse_args(argv)
    out = Path(args.job_dir) / "lidar" / "index.parquet"
    try:
        t = NuscTables.load(args.data_root)
        if args.resume and out.is_file():
            print(f"skip: {out} đã có (--resume)")
            index = read_table(out, "lidar_index")
        else:
            index = build_lidar_index(t, args.data_root)
            if index.empty:
                raise FileNotFoundError(f"{args.data_root}: không có keyframe LIDAR_TOP nào")
            index = assign_splits(index, load_lidar_config())
            out.parent.mkdir(parents=True, exist_ok=True)
            write_table(index, out, "lidar_index")
        write_gt(t, index, Path(args.job_dir))
        write_display(t, index, args.data_root, Path(args.job_dir),
                      load_config(args.profile).workers)
    except FileNotFoundError as e:
        print(f"thiếu đầu vào: {e}", file=sys.stderr)
        return 4
    except ContractError as e:
        print(f"vi phạm contract: {e}", file=sys.stderr)
        return 2
    print(f"lidar_index: {len(index)} keyframe · " + ", ".join(
        f"{k}={v}" for k, v in index.groupby("split").size().items()))
    return 0


if __name__ == "__main__":
    sys.exit(main())
