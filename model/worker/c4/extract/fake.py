"""Model giả chạy CPU (C4_FAKE_MODELS=1): tất định theo đường dẫn ảnh, không cần trọng số."""
import hashlib
import os

import numpy as np

IMG_W, IMG_H = 1600, 900
FAKE_CLASSES = [0, 1, 2, 3, 5, 7]  # COCO: person, bicycle, car, motorcycle, bus, truck


def fake_models_enabled() -> bool:
    return os.environ.get("C4_FAKE_MODELS") == "1"


def _rng(key: str) -> np.random.Generator:
    return np.random.default_rng(int.from_bytes(hashlib.sha256(key.encode()).digest()[:8], "big"))


def fake_embed(paths, d, seed=0) -> np.ndarray:
    """Hash của đường dẫn → vector đơn vị float32 (N × d)."""
    out = np.stack([_rng(f"{seed}:{p}").standard_normal(d) for p in paths]) if len(paths) \
        else np.zeros((0, d))
    return (out / np.linalg.norm(out, axis=1, keepdims=True)).astype(np.float32) if len(paths) \
        else out.astype(np.float32)


def fake_detect(paths) -> list[list[tuple]]:
    """Mỗi ảnh 1–4 box (cls int, conf, x1, y1, x2, y2) theo pixel 1600×900."""
    result = []
    for p in paths:
        r = _rng(f"det:{p}")
        dets = []
        for _ in range(int(r.integers(1, 5))):
            x1, y1 = int(r.integers(0, IMG_W - 100)), int(r.integers(0, IMG_H - 100))
            x2, y2 = x1 + int(r.integers(20, IMG_W - x1)), y1 + int(r.integers(20, IMG_H - y1))
            dets.append((int(r.choice(FAKE_CLASSES)), round(float(r.uniform(0.05, 0.95)), 3),
                         x1, y1, x2, y2))
        result.append(dets)
    return result
