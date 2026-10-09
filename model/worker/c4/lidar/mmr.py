# c4/mining/mmr.py · MMR tham lam + trần theo scene + khoảng cách thời gian
import math

import numpy as np


def mmr_select(S, Z, scene, fidx, ok, B, B_max, lam=0.7, m=3, min_gap=4):
    """S (N,) điểm frame 0..1 · Z (N, d) float32 chuẩn hóa L2 · scene (N,) mã số scene
    fidx (N,) frame_idx · ok (N,) bool. Trả về các lần chọn theo thứ tự, tối đa B_max."""
    S = np.asarray(S, np.float32)
    Z = np.ascontiguousarray(Z, dtype=np.float32)
    blocked = ~np.asarray(ok, bool)  # đã chọn, quá gần, hoặc ảnh hỏng
    max_sim = np.zeros(len(S), dtype=np.float32)  # max sim tới tập đã chọn; rỗng thì 0
    count = np.zeros(int(scene.max()) + 1 if len(scene) else 1, dtype=np.int32)
    picks = []
    for rank in range(1, B_max + 1):
        cap = m * math.ceil(rank / B)  # m cho B đầu; 2m cho phần mở rộng của UI
        util = lam * S - (1.0 - lam) * max_sim
        util[blocked | (count[scene] >= cap)] = -np.inf
        i = int(np.argmax(util))
        if not np.isfinite(util[i]):
            break  # hết ứng viên hợp lệ
        picks.append(dict(rank=rank, i=i, S=float(S[i]), max_sim=float(max_sim[i]),
                          mmr_util=float(util[i])))
        count[scene[i]] += 1
        blocked |= (scene == scene[i]) & (np.abs(fidx - fidx[i]) < min_gap)  # gồm cả frame i
        max_sim = np.maximum(max_sim, np.clip(Z @ Z[i], 0.0, 1.0))
    return picks
