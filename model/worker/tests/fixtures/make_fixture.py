"""Dữ liệu giả đúng contract: scene là cụm embedding, frame hiếm là điểm lệch hướng riêng."""
from dataclasses import dataclass
from pathlib import Path

import numpy as np
import pandas as pd

from c4.contracts import CAMS, validate, write_table


@dataclass
class Fixture:
    feat: pd.DataFrame
    Z_img: np.ndarray
    C_img: np.ndarray
    gt: pd.DataFrame | None
    rare_tokens: set


def _unit(x):
    return x / np.linalg.norm(x, axis=-1, keepdims=True)


def make_fixture(n_scenes=4, frames_per_scene=10, d=32, seed=0, missing_cams=True,
                 with_gt=True, rare_frac=0.1) -> Fixture:
    rng = np.random.default_rng(seed)
    n_frames = n_scenes * frames_per_scene
    scene_of = np.repeat(np.arange(n_scenes), frames_per_scene)
    fidx = np.tile(np.arange(frames_per_scene), n_scenes)
    tokens = np.array([f"s{s}_f{i}" for s, i in zip(scene_of, fidx)])
    rare = np.zeros(n_frames, bool)
    rare[rng.choice(n_frames, max(1, int(rare_frac * n_frames)), replace=False)] = True

    cam_mask = np.ones((n_frames, 6), bool)
    if missing_cams:
        for f in np.flatnonzero(rng.random(n_frames) < 0.3):
            cam_mask[f, rng.choice(6, rng.integers(1, 4), replace=False)] = False
    fi, ci = np.nonzero(cam_mask)  # một dòng một ảnh, đã sắp theo frame rồi camera
    n = len(fi)
    r_img = rare[fi]
    u = rng.random(n).astype(np.float32)

    centroids = _unit(rng.normal(size=(n_scenes, d)))
    rare_dirs = _unit(rng.normal(size=(n_frames, d)))
    base = np.where(r_img[:, None], rare_dirs[fi], centroids[scene_of[fi]])
    Z = _unit(base + 0.05 * rng.normal(size=(n, d))).astype(np.float16)
    C = rng.normal(size=(n, 16))
    C[r_img, 0] += 4.0
    C = _unit(C).astype(np.float16)

    unc = np.where(r_img, 0.5 + 0.3 * u, 0.2 * u).astype(np.float32)
    q_bright = np.full(n, 120.0, np.float32)
    q_bright[-1] = 3.0  # một ảnh gần như đen
    feat = pd.DataFrame(dict(
        sample_token=tokens[fi], cam=np.array(CAMS)[ci],
        scene_token=[f"scene{s}" for s in scene_of[fi]],
        split="pool", frame_idx=fidx[fi],
        img_path=[f"samples/{CAMS[c]}/{tokens[f]}.jpg" for f, c in zip(fi, ci)],
        emb_row=np.arange(n), nov_knn=np.where(r_img, 0.6 + 0.1 * u, 0.2 + 0.05 * u),
        det_n=3, det_n_conf=2, det_ent=unc, det_tmp=unc, unc=unc,
        qry_max=np.where(r_img, 0.30 + 0.02 * u, 0.15 + 0.05 * u),
        qry_best=np.where(r_img, "night_rain", "bicycle"),
        q_bright=q_bright, q_blur=80.0, q_ok=q_bright >= 8))
    gt = None
    if with_gt:
        gt = pd.DataFrame(dict(
            sample_token=tokens, is_rare=rare, A_night=rare & (fidx % 2 == 0), A_rain=False,
            B_rare_class=rare & (fidx % 2 == 1), C_crowd=False, C_low_vis=False, C_far=False))
        gt = validate(gt, "gt_rare")
    return Fixture(validate(feat, "features_cache"), Z, C, gt, set(tokens[rare]))


def write_job_dir(fx: Fixture, root: Path) -> Path:
    """Bố cục thư mục job mà Plan 2 phải sinh ra."""
    root = Path(root)
    (root / "cache").mkdir(parents=True, exist_ok=True)
    write_table(fx.feat, str(root / "cache/features_cache.parquet"), "features_cache")
    np.save(root / "cache/dino_cls.npy", fx.Z_img)
    np.save(root / "cache/clip_img.npy", fx.C_img)
    if fx.gt is not None:
        (root / "gt").mkdir(exist_ok=True)
        write_table(fx.gt, str(root / "gt/gt_rare.parquet"), "gt_rare")
    return root
