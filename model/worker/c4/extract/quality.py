"""Chỉ số chất lượng ảnh: độ sáng trung bình và độ nét (phương sai Laplacian)."""
import cv2
import numpy as np

QUALITY_WH = (448, 252)


def quality_metrics(gray_u8: np.ndarray) -> tuple[float, float]:
    """(q_bright, q_blur) = mean luma, Laplacian(...).var() trên ảnh xám 448×252."""
    g = gray_u8
    if (g.shape[1], g.shape[0]) != QUALITY_WH:
        g = cv2.resize(g, QUALITY_WH, interpolation=cv2.INTER_AREA)
    return float(g.mean()), float(cv2.Laplacian(g, cv2.CV_64F).var())
