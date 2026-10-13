"""C0: độ cao mặt trời (độ) từ timestamp nuScenes (µs UTC) + vĩ/kinh độ. Thuần math, CPU.

Thuật toán NOAA rút gọn (Spencer/NOAA solar calculator: fractional year -> equation of time
và declination -> hour angle). Sai số điển hình < 0,3° (không tính khúc xạ khí quyển).
Chỉ đọc timestamp + vị trí log (bất biến B2): không đọc scene.description.
"""
import math


def sun_elevation_deg(timestamp_us: int, lat: float, lon: float) -> float:
    """Độ cao mặt trời (độ, >0 là trên chân trời). timestamp_us: micro-giây kể từ epoch UTC."""
    t = float(timestamp_us) / 1e6  # giây
    days = math.floor(t / 86400.0)
    sec_of_day = t - days * 86400.0
    # ngày thứ tự trong năm (UTC) và giờ UTC
    jd = days + 2440587.5  # JD lúc 00:00 UTC của ngày đó
    y, m, d = _civil_from_days(int(days))
    doy = int(days - _days_from_civil(y, 1, 1)) + 1
    ndays = 366 if (y % 4 == 0 and (y % 100 != 0 or y % 400 == 0)) else 365
    hour = sec_of_day / 3600.0
    g = 2.0 * math.pi / ndays * (doy - 1 + (hour - 12.0) / 24.0)  # fractional year (rad)
    eqtime = 229.18 * (0.000075 + 0.001868 * math.cos(g) - 0.032077 * math.sin(g)
                       - 0.014615 * math.cos(2 * g) - 0.040849 * math.sin(2 * g))  # phút
    decl = (0.006918 - 0.399912 * math.cos(g) + 0.070257 * math.sin(g)
            - 0.006758 * math.cos(2 * g) + 0.000907 * math.sin(2 * g)
            - 0.002697 * math.cos(3 * g) + 0.00148 * math.sin(3 * g))  # rad
    tst = (hour * 60.0 + eqtime + 4.0 * lon) % 1440.0  # true solar time (phút)
    ha = math.radians(tst / 4.0 - 180.0)
    la = math.radians(lat)
    sin_el = math.sin(la) * math.sin(decl) + math.cos(la) * math.cos(decl) * math.cos(ha)
    return math.degrees(math.asin(max(-1.0, min(1.0, sin_el))))


def _days_from_civil(y: int, m: int, d: int) -> int:
    """Số ngày kể từ 1970-01-01 (Howard Hinnant)."""
    y -= m <= 2
    era = (y if y >= 0 else y - 399) // 400
    yoe = y - era * 400
    doy = (153 * (m + (-3 if m > 2 else 9)) + 2) // 5 + d - 1
    doe = yoe * 365 + yoe // 4 - yoe // 100 + doy
    return era * 146097 + doe - 719468


def _civil_from_days(z: int) -> tuple[int, int, int]:
    z += 719468
    era = (z if z >= 0 else z - 146096) // 146097
    doe = z - era * 146097
    yoe = (doe - doe // 1460 + doe // 36524 - doe // 146096) // 365
    y = yoe + era * 400
    doy = doe - (365 * yoe + yoe // 4 - yoe // 100)
    mp = (5 * doy + 2) // 153
    d = doy - (153 * mp + 2) // 5 + 1
    m = mp + (3 if mp < 10 else -9)
    return y + (m <= 2), m, d
