import math
from datetime import datetime, timezone
from pathlib import Path

import yaml

from c4.context.sun import sun_elevation_deg

LOC = yaml.safe_load((Path(__file__).resolve().parents[2] / "configs" / "locations.yaml").read_text("utf-8"))


def _us(*a) -> int:
    return int(datetime(*a, tzinfo=timezone.utc).timestamp()) * 1_000_000


def _almanac(dt: datetime, lat: float, lon: float) -> float:
    """Công thức độc lập: Astronomical Almanac low-precision (n từ J2000), không dùng chung mã với sun.py."""
    n = dt.timestamp() / 86400.0 + 2440587.5 - 2451545.0
    L = (280.460 + 0.9856474 * n) % 360
    g = math.radians((357.528 + 0.9856003 * n) % 360)
    lam = math.radians(L + 1.915 * math.sin(g) + 0.020 * math.sin(2 * g))
    eps = math.radians(23.439 - 0.0000004 * n)
    ra = math.atan2(math.cos(eps) * math.sin(lam), math.cos(lam))
    dec = math.asin(math.sin(eps) * math.sin(lam))
    gmst = (280.46061837 + 360.98564736629 * n) % 360
    ha = math.radians(gmst + lon) - ra
    la = math.radians(lat)
    return math.degrees(math.asin(math.sin(la) * math.sin(dec) + math.cos(la) * math.cos(dec) * math.cos(ha)))


CASES = [
    ((2018, 11, 21, 11, 38), "singapore-onenorth"),
    ((2018, 7, 24, 3, 22), "singapore-queenstown"),
    ((2018, 7, 24, 16, 0), "boston-seaport"),
]


def test_sun_elevation():
    lat, lon = LOC["singapore-onenorth"]["lat"], LOC["singapore-onenorth"]["lon"]
    t_night, t_noon = (2018, 11, 21, 11, 38), (2018, 7, 24, 3, 22)
    for t in (t_night, t_noon):
        assert abs(sun_elevation_deg(_us(*t), lat, lon) - _almanac(datetime(*t, tzinfo=timezone.utc), lat, lon)) <= 0.5
    assert sun_elevation_deg(_us(*t_night), lat, lon) < -6.0
    assert sun_elevation_deg(_us(*t_noon), lat, lon) > 30.0
