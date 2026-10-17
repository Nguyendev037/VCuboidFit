"""Họ kiến trúc dùng để kiểm độc lập selector/giám khảo."""
from c4.bench.gate import BenchGateError

FAMILIES: dict[str, set[str]] = {
    "OURS": {"openclip", "opencv", "lidar_statistics", "pointpillars"},
    "M3": {"openclip", "opencv", "lidar_statistics", "pointpillars"},
    "M2": {"pointpillars", "lidar_statistics"}, "M1": {"lidar_statistics"},
    "X0": set(), "X1": {"dinov2"}, "X2": {"yolo11"}, "X3": {"yolo11"},
    "N1": {"opencv"}, "N2": {"opencv"},
    "JA": {"fasterrcnn"}, "JB": {"rtdetr", "detr"},
}


def assert_independent(selectors: list[str], judges: list[str]) -> None:
    for s in selectors:
        for j in judges:
            if s not in FAMILIES or j not in FAMILIES:
                raise BenchGateError("NOT_INDEPENDENT", f"undeclared family: {s}/{j}")
            if FAMILIES[s] & FAMILIES[j]:
                raise BenchGateError("NOT_INDEPENDENT", f"{s}/{j}")
