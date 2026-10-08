"""Đặt seed/determinism cho mọi lần train/infer Tầng 1 (SPEC-P01 §3).

KHÔNG dùng torch.use_deterministic_algorithms(True): spconv có kernel không deterministic sẽ
ném lỗi và làm gãy train. Chấp nhận sai số <= 1e-4 giữa hai lần chạy.
"""
from __future__ import annotations

import os
import random


def set_determinism(seed: int = 0) -> dict:
    """Đặt các seed + cờ cudnn; trả dict giá trị đã đặt (ghi vào train_config.yaml::determinism)."""
    import numpy as np
    import torch

    os.environ["PYTHONHASHSEED"] = str(seed)
    os.environ["CUBLAS_WORKSPACE_CONFIG"] = ":4096:8"
    random.seed(seed)
    np.random.seed(seed)
    torch.manual_seed(seed)
    torch.cuda.manual_seed_all(seed)
    torch.backends.cudnn.deterministic = True
    torch.backends.cudnn.benchmark = False
    return dict(seed=seed, PYTHONHASHSEED=str(seed), CUBLAS_WORKSPACE_CONFIG=":4096:8",
                cudnn_deterministic=True, cudnn_benchmark=False)
