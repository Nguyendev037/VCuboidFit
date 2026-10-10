"""Thời tiết / ngày-đêm (M3).

Kết luận từ phản biện domain, code tuân theo:
- LiDAR là cảm biến CHỦ ĐỘNG: ban đêm LiDAR gần như KHÔNG suy giảm (camera mới suy giảm).
  → Cờ "đêm" có giá trị vì (1) hệ AEB thực tế là fusion camera+LiDAR, nhãn LiDAR ban đêm
    cần để eval nhánh LiDAR trong fusion; (2) đêm là OOD gap về phân phối.
  → Nguồn tín hiệu "đêm": metadata scene (mô tả) HOẶC độ sáng camera. KHÔNG bao giờ
    suy ra "đêm" từ hình dạng point cloud.
- "Mưa" là biến CƯỜNG ĐỘ (mm/h), không phải nhị phân. Proxy cường độ từ chính point
  cloud: tỉ lệ điểm "trên không" intensity thấp (backscatter của giọt mưa).
"""
import math
import re
from typing import Optional

import numpy as np

_NIGHT_RE = re.compile(r"\b(night|midnight|after dark|dark|late evening|evening)\b", re.I)
_RAIN_RE = re.compile(r"\b(rain|rainy|raining|shower|drizzle|downpour|storm|wet)\b", re.I)
_SNOW_RE = re.compile(r"\b(snow|snowy|blizzard)\b", re.I)
_FOG_RE = re.compile(r"\b(fog|foggy|mist|haze)\b", re.I)


def parse_desc(desc: str) -> dict:
    """Parse mô tả scene tự do (nuScenes `scene.description`) thành cờ thời tiết.

    Đây là đường nguồn ƯU TIÊN vì nó là metadata có thật trong dataset.
    """
    d = "" if desc is None else str(desc)
    return {
        "night": bool(_NIGHT_RE.search(d)),
        "rain": bool(_RAIN_RE.search(d)),
        "snow": bool(_SNOW_RE.search(d)),
        "fog": bool(_FOG_RE.search(d)),
    }


def lidar_rain_proxy(points: np.ndarray) -> float:
    """Proxy cường độ mưa từ point cloud [0..1].

    Ý tưởng: giọt mưa tạo điểm backscatter trên không (z > 0.8 m, không thuộc vật thể)
    với intensity THẤP. Trong data sạch tỉ lệ này ≈ 0; mưa càng to càng cao.
    Chỉ dùng khi có kênh intensity (cột 4).
    """
    if points is None or points.ndim != 2 or points.shape[1] < 4 or points.shape[0] < 50:
        return 0.0
    x, y, z, inten = points[:, 0], points[:, 1], points[:, 2], points[:, 3]
    air = (z > 0.8) & (z < 4.0) & (x * x + y * y < 45.0 ** 2)
    n_air = int(air.sum())
    if n_air < 20:
        return 0.0
    low = inten[air] < 0.25
    frac = float(low.mean())
    # hiệu chỉnh: chuẩn hoá thô — 15% điểm air intensity thấp ≈ mưa đáng kể
    return float(min(1.0, frac / 0.15))


def camera_brightness(image_paths: tuple) -> Optional[float]:
    """Độ sáng trung bình [0..1] của ảnh camera (nếu có PIL). Proxy cho 'đêm'."""
    try:
        from PIL import Image
    except Exception:
        return None
    vals = []
    for p in image_paths[:3]:
        try:
            im = Image.open(p).convert("L").resize((64, 64))
            vals.append(np.asarray(im, dtype=float).mean() / 255.0)
        except Exception:
            continue
    return float(np.mean(vals)) if vals else None


def night_from_brightness(brightness: Optional[float], thresh: float = 0.18) -> float:
    if brightness is None:
        return 0.0
    return 1.0 if brightness < thresh else 0.0


def rain_score_combine(desc_rain: bool, proxy: float) -> float:
    """Kết hợp metadata + proxy LiDAR thành điểm mưa liên tục [0..1].

    Metadata mưa → nền 0.75 (kênh chính), proxy chỉ điều chỉnh cường độ.
    Metadata không mưa → proxy đơn thuần cho điểm yếu (0.4×) vì proxy dễ nhiễu.
    """
    if desc_rain:
        return float(min(1.0, 0.75 + 0.25 * min(1.0, proxy / 0.2)))
    return float(0.4 * min(1.0, proxy / 0.2))
