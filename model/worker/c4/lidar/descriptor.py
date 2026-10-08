"""M3 · descriptor hình học Tầng 0 (PDF §4.1): khối A–E → z-score → chia √d khối → PCA.

Không model, không nhãn, chạy CPU. Một frame = một dict {khối: vector}; ghép và PCA ở `embed`
trên đúng tập đang chọn (PCA không dùng nhãn nên fit trên chính tập đó là hợp lệ).
"""
from pathlib import Path

import numpy as np

from c4.lidar.pcd import load_pcd, preprocess, remove_close

BLOCKS = ["A", "B", "C", "D", "E"]


def _hist(x: np.ndarray, edges) -> np.ndarray:
    h, _ = np.histogram(np.clip(x, edges[0], edges[-1] - 1e-6), bins=edges)
    return (h / max(h.sum(), 1)).astype(np.float32)


def block_range(p, cfg) -> np.ndarray:
    r = np.hypot(p[:, 0], p[:, 1])
    return np.append(_hist(r, cfg["blocks"]["range_bins_m"]), np.log1p(len(p))).astype(np.float32)


def block_height(p, cfg) -> np.ndarray:
    lo, hi = cfg["blocks"]["z_range_m"]
    step = cfg["blocks"]["z_step_m"]
    return _hist(p[:, 2], np.arange(lo, hi + step / 2, step))


def bev_counts(p, cell: float, half: float) -> np.ndarray:
    n = int(round(2 * half / cell))
    ix = np.clip(((p[:, 0] + half) / cell).astype(np.int64), 0, n - 1)
    iy = np.clip(((p[:, 1] + half) / cell).astype(np.int64), 0, n - 1)
    grid = np.zeros((n, n), np.float32)
    np.add.at(grid, (iy, ix), 1.0)
    return grid


def block_bev(p, cfg) -> np.ndarray:
    return np.log1p(bev_counts(p, cfg["blocks"]["bev_cell_m"], cfg["pcd"]["crop_m"])).ravel()


def ground_plane(v: np.ndarray, cfg) -> np.ndarray | None:
    """RANSAC mặt phẳng trên điểm thấp gần xe; trả (a, b, c, d) với ax+by+cz+d=0, c>0, ‖n‖=1."""
    rc = cfg["blocks"]["ransac"]
    near = v[np.hypot(v[:, 0], v[:, 1]) < rc["radius_m"]]
    if len(near) < 3:
        return None
    cand = near[near[:, 2] <= np.percentile(near[:, 2], 30)]
    if len(cand) < 3:
        return None
    rng = np.random.default_rng(rc["seed"])
    best, best_n = None, -1
    for _ in range(rc["iters"]):
        a, b, c = cand[rng.choice(len(cand), 3, replace=False), :3]
        n = np.cross(b - a, c - a)
        norm = np.linalg.norm(n)
        if norm < 1e-6 or abs(n[2]) / norm < 0.8:  # bỏ mặt phẳng dốc hơn ~37°
            continue
        n = n / norm
        if n[2] < 0:
            n = -n
        d = -float(n @ a)
        cnt = int((np.abs(near[:, :3] @ n + d) < rc["thr_m"]).sum())
        if cnt > best_n:
            best, best_n = np.append(n, d), cnt
    return best


def block_clusters(v, plane, cfg) -> tuple[np.ndarray, np.ndarray]:
    """Khối D + mặt nạ điểm không phải mặt đất (trên tập voxel)."""
    from sklearn.cluster import DBSCAN

    b = cfg["blocks"]
    nb = len(b["cluster_size_bins"]) + len(b["cluster_bev_bins_m2"]) + 2
    if plane is None:
        return np.zeros(nb, np.float32), np.ones(len(v), bool)
    height = v[:, :3] @ plane[:3] + plane[3]
    nonground = height > b["ransac"]["thr_m"]
    pts = v[nonground]
    if len(pts) < b["dbscan"]["min_samples"]:
        return np.zeros(nb, np.float32), nonground
    lab = DBSCAN(eps=b["dbscan"]["eps_m"], min_samples=b["dbscan"]["min_samples"],
                 algorithm="kd_tree").fit_predict(pts[:, :3])
    ids = lab[lab >= 0]
    if ids.size == 0:
        return np.zeros(nb, np.float32), nonground
    sizes = np.bincount(ids)
    order = np.argsort(lab, kind="stable")
    lab_s, pts_s = lab[order], pts[order]
    start = np.searchsorted(lab_s, np.arange(len(sizes)))
    stop = np.searchsorted(lab_s, np.arange(len(sizes)), side="right")
    area, dist = np.zeros(len(sizes)), np.zeros(len(sizes))
    for i, (s0, s1) in enumerate(zip(start, stop)):
        q = pts_s[s0:s1]
        ext = q[:, :2].max(0) - q[:, :2].min(0)
        area[i] = ext[0] * ext[1]
        dist[i] = np.hypot(*q[:, :2].mean(0))
    def counts(x, uppers):
        idx = np.searchsorted(np.asarray(uppers, float), x, side="left")
        return np.log1p(np.bincount(np.minimum(idx, len(uppers) - 1), minlength=len(uppers)))
    sf = b["small_far"]
    small_far = int(((sizes <= sf["max_pts"]) & (dist > sf["min_r_m"])).sum())
    vec = np.concatenate([[np.log1p(len(sizes))], counts(sizes, b["cluster_size_bins"]),
                          counts(area, b["cluster_bev_bins_m2"]), [np.log1p(small_far)]])
    return vec.astype(np.float32), nonground


def block_sensor(p, v, nonground, cfg) -> np.ndarray:
    r = np.hypot(v[:, 0], v[:, 1])
    near_ng = float((nonground & (r < cfg["blocks"]["sensor_radius_m"])).sum()) / max(len(v), 1)
    inten = p[:, 3] if len(p) else np.zeros(1, np.float32)
    return np.array([near_ng, inten.mean() / 255.0, inten.std() / 255.0], np.float32)


def bev_png(p, path: Path, cfg) -> None:
    from PIL import Image

    px = cfg["bev_png_px"]
    half = cfg["pcd"]["crop_m"]
    g = np.log1p(bev_counts(p, 2 * half / px, half))
    g = (255 * g / max(g.max(), 1e-6)).astype(np.uint8)
    img = np.ascontiguousarray(g.T[::-1, ::-1])  # hàng = −x (xe hướng lên), cột = −y (trái = +y)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".tmp.png")
    Image.fromarray(img).save(tmp)
    tmp.replace(path)


def frame_descriptor(path, cfg, bev_path: Path | None = None) -> dict:
    """Trả {"blocks": {A..E: vec} | None, "n_points": int, "reason": str}."""
    try:
        raw = load_pcd(path)
    except (OSError, ValueError):
        return dict(blocks=None, n_points=0, reason="read_error")
    n = len(remove_close(raw, cfg["pcd"]["remove_close_m"]))
    if n < cfg["filter"]["min_points"]:
        return dict(blocks=None, n_points=n, reason="few_points")
    p, v = preprocess(raw, cfg)
    plane = ground_plane(v, cfg)
    d, nonground = block_clusters(v, plane, cfg)
    blocks = dict(A=block_range(p, cfg), B=block_height(p, cfg), C=block_bev(p, cfg), D=d,
                  E=block_sensor(p, v, nonground, cfg))
    if bev_path is not None and not bev_path.exists():
        bev_png(p, bev_path, cfg)
    return dict(blocks=blocks, n_points=n, reason="")


def block_dims(cfg) -> dict[str, int]:
    b = cfg["blocks"]
    lo, hi = b["z_range_m"]
    n_bev = int(round(2 * cfg["pcd"]["crop_m"] / b["bev_cell_m"]))
    return dict(A=len(b["range_bins_m"]), B=len(np.arange(lo, hi + b["z_step_m"] / 2,
                                                          b["z_step_m"])) - 1,
                C=n_bev * n_bev,
                D=len(b["cluster_size_bins"]) + len(b["cluster_bev_bins_m2"]) + 2, E=3)


def stack(results: list[dict], cfg) -> tuple[dict[str, np.ndarray], np.ndarray]:
    """Ghép kết quả từng frame thành {khối: (N, d)} + mặt nạ keep. Frame hỏng = dòng 0."""
    dims = block_dims(cfg)
    keep = np.array([r["blocks"] is not None for r in results], bool)
    raw = {k: np.zeros((len(results), d), np.float32) for k, d in dims.items()}
    for i, r in enumerate(results):
        if r["blocks"] is not None:
            for k in BLOCKS:
                raw[k][i] = r["blocks"][k]
    return raw, keep


def embed(raw: dict[str, np.ndarray], fit_mask: np.ndarray, dim: int,
          drop_blocks: tuple[str, ...] = ()) -> np.ndarray:
    """z-score (theo fit_mask) → chia √d khối → ghép → PCA fit trên fit_mask, chiếu mọi dòng."""
    fit_mask = np.asarray(fit_mask, bool)
    if fit_mask.sum() < 2:
        raise ValueError("Không có frame LiDAR hợp lệ")
    parts = []
    for k in BLOCKS:
        if k in drop_blocks:
            continue
        x = raw[k].astype(np.float64)
        mu, sd = x[fit_mask].mean(0), x[fit_mask].std(0)
        z = np.where(sd > 1e-9, (x - mu) / np.where(sd > 1e-9, sd, 1.0), 0.0)
        parts.append(z / np.sqrt(x.shape[1]))
    X = np.concatenate(parts, axis=1)
    Xf = X[fit_mask]
    mean = Xf.mean(0)
    _, _, vt = np.linalg.svd(Xf - mean, full_matrices=False)
    d = int(min(dim, Xf.shape[0] - 1, Xf.shape[1]))
    comp = vt[:d]
    flip = np.sign(comp[np.arange(d), np.abs(comp).argmax(1)])  # dấu tất định
    comp = comp * flip[:, None]
    return ((X - mean) @ comp.T).astype(np.float32)
