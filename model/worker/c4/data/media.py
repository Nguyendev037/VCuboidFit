"""S0c: media cho khung xem — thumbnail WebP 320×180 mỗi ảnh camera, point cloud LiDAR (hệ ego)."""
import os
import sys
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import numpy as np
import pandas as pd
from PIL import Image

from c4.contracts import ContractError
from c4.data.geometry import quat_to_mat
from c4.data.nusc import NuscTables

PCD_FIELDS = 5  # nuScenes .pcd.bin: float32 x, y, z, intensity, ring


def _thumb_one(src: Path, dst: Path, size: tuple[int, int]) -> int:
    if dst.exists():
        return 0
    tmp = dst.with_name(dst.name + ".tmp")
    try:
        with Image.open(src) as im:
            im.draft("RGB", size)  # JPEG giải mã ở độ phân giải thấp: nhanh hơn nhiều
            im.convert("RGB").resize(size, Image.Resampling.LANCZOS).save(
                tmp, format="WEBP", quality=70)
        os.replace(tmp, dst)  # ghi nguyên tử: file dở không bao giờ mang tên cuối
    except OSError as e:
        tmp.unlink(missing_ok=True)
        print(f"thumbnail bỏ qua {dst.stem}: {e}", file=sys.stderr)
        return 0
    return 1


def make_thumbs(frames: pd.DataFrame, data_root, out_dir, size=(320, 180), workers=4) -> int:
    """`<out_dir>/<sample_token>_<cam>.webp` cho từng dòng frames; bỏ qua file đã có (resume).
    Ảnh hỏng/0 byte: ghi tên ra stderr rồi bỏ qua. Trả số thumbnail GHI MỚI."""
    data_root, out_dir = Path(data_root), Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    jobs = [(data_root / p, out_dir / f"{s}_{c}.webp")
            for s, c, p in zip(frames["sample_token"], frames["cam"], frames["img_path"])]
    with ThreadPoolExecutor(max_workers=max(1, workers)) as ex:
        return sum(ex.map(lambda j: _thumb_one(j[0], j[1], tuple(size)), jobs))


def lidar_to_bin(pcd_path: Path, calib_lidar: dict, out_path: Path) -> int:
    """Điểm hệ cảm biến → hệ ego của sample LIDAR_TOP (`p_ego = R·p + t`), ghi float16
    x,y,z,intensity theo hàng. Trả số điểm."""
    pcd_path, out_path = Path(pcd_path), Path(out_path)
    if pcd_path.stat().st_size % (4 * PCD_FIELDS):  # np.fromfile sẽ lặng lẽ cắt phần dư
        raise ContractError(f"{pcd_path}: kích thước không chia hết cho {PCD_FIELDS} float32")
    pts = np.fromfile(pcd_path, dtype=np.float32).reshape(-1, PCD_FIELDS)
    rot = quat_to_mat(calib_lidar["rotation"])
    ego = pts[:, :3].astype(np.float64) @ rot.T + np.asarray(calib_lidar["translation"])
    out = np.column_stack([ego, pts[:, 3]]).astype(np.float16)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    tmp = out_path.with_name(out_path.name + ".tmp")
    out.tofile(tmp)
    os.replace(tmp, out_path)
    return len(out)


def export_lidar(t: NuscTables, frames: pd.DataFrame, data_root, out_dir) -> int:
    """`<out_dir>/<sample_token>.bin` cho từng sample của frames có keyframe LIDAR_TOP trên đĩa.
    Không có LIDAR_TOP ⇒ không làm gì (không tạo thư mục). Bỏ qua file đã có. Trả số file mới."""
    data_root, out_dir = Path(data_root), Path(out_dir)
    lidar = {}
    for sd in t.sample_data.values():
        cal = t.calibrated_sensor[sd["calibrated_sensor_token"]]
        if sd["is_key_frame"] and t.sensor[cal["sensor_token"]]["channel"] == "LIDAR_TOP":
            lidar[sd["sample_token"]] = (sd, cal)
    written = 0
    for sample in dict.fromkeys(frames["sample_token"]):
        if sample not in lidar:
            continue
        sd, cal = lidar[sample]
        src, dst = data_root / sd["filename"], out_dir / f"{sample}.bin"
        if dst.exists() or not src.is_file():
            continue
        try:
            lidar_to_bin(src, cal, dst)
        except ContractError as e:
            print(f"lidar bỏ qua {sample}: {e}", file=sys.stderr)
            continue
        written += 1
    return written
