"""Pipeline chọn 5% keyframe LiDAR (planning/04). Chỉ `gt` (ghi) và `eval` (đọc) chạm nhãn."""
import yaml

from c4.config import CONFIG_DIR


def load_lidar_config() -> dict:
    return yaml.safe_load((CONFIG_DIR / "lidar.yaml").read_text(encoding="utf-8"))


def load_gt_config() -> dict:
    return yaml.safe_load((CONFIG_DIR / "gt.yaml").read_text(encoding="utf-8"))
