"""rare_mining — Khai thác frame hiếm & vật thể hiếm trong LiDAR không nhãn (AEB-VRU).

Pipeline 2 cấp (v2 sau phản biện):
  M0 dữ liệu/metadata → M1 sinh ứng viên vật thể (cluster + detection)
  → M2 điểm vật thể → M3 điểm frame → M4 rank/dedup/đa dạng hoá
  → M5 chọn theo ngân sách → M6 đánh giá trên GT giấu (rule filter).
"""

__version__ = "2.2.0"

from .config import PipelineConfig
from .data import Frame, GTBox, BinDirSource, NuscenesSource
from .synthetic import SyntheticSource
from .pipeline import run_pipeline
from .m6_evaluate import evaluate

__all__ = [
    "PipelineConfig", "Frame", "GTBox",
    "SyntheticSource", "BinDirSource", "NuscenesSource",
    "run_pipeline", "evaluate", "__version__",
]