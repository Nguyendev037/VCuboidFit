"""S1: DINOv2 CLS embedding (N × d float16, L2) + novelty + chất lượng ảnh.

Module cũng giữ vài hàm dùng chung cho S2/S3 (thư mục trọng số, chữ ký resume, ghi nguyên tử).
Thiếu đầu vào ném FileNotFoundError (CLI đổi thành exit 4).
"""
import hashlib
import os
import shutil
from pathlib import Path

import numpy as np
import pandas as pd
import torch

from c4.config import load_config
from c4.contracts import read_table
from c4.extract.base import Images, Progress, concat_shards, run_shards
from c4.extract.fake import fake_embed, fake_models_enabled
from c4.extract.quality import quality_metrics
from c4.mining.novelty import novelty_knn

IMAGENET_MEAN = (0.485, 0.456, 0.406)
IMAGENET_STD = (0.229, 0.224, 0.225)
_LUMA = (0.299, 0.587, 0.114)
FETCH_HINT = "python scripts/fetch_weights.py"


def weights_dir() -> Path:
    env = os.environ.get("C4_WEIGHTS_DIR")
    return Path(env) if env else Path(__file__).resolve().parents[3] / "workspace" / "weights"


def missing_weights(what: str) -> FileNotFoundError:
    w = weights_dir()
    return FileNotFoundError(f"thiếu trọng số {what} trong {w}; chạy: {FETCH_HINT} --dir {w}")


def load_frames(job_dir, limit=None) -> pd.DataFrame:
    path = Path(job_dir) / "index" / "frames.parquet"
    if not path.is_file():
        raise FileNotFoundError(f"thiếu {path} (chạy c4.cli.build_index trước)")
    frames = read_table(path, "frames")
    return frames if limit is None else frames.head(limit).reset_index(drop=True)


def signature(*parts) -> str:
    return hashlib.sha1("\n".join(str(p) for p in parts).encode("utf-8")).hexdigest()


def prepare_shard_dir(shard_dir: Path, sig: str, resume: bool) -> None:
    """Giữ shard cũ chỉ khi --resume và chữ ký (model, tham số, danh sách ảnh) khớp; ngược lại xoá.

    Không có chữ ký thì shard của lần chạy `--limit 3` sẽ bị nhận nhầm làm shard của lần chạy đủ.
    """
    sig_file = shard_dir / "_sig"
    if resume and sig_file.is_file() and sig_file.read_text(encoding="utf-8") == sig:
        return
    shutil.rmtree(shard_dir, ignore_errors=True)
    shard_dir.mkdir(parents=True)
    sig_file.write_text(sig, encoding="utf-8")


def write_npy_atomic(arr: np.ndarray, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + ".tmp")
    with open(tmp, "wb") as f:
        np.save(f, arr)
    os.replace(tmp, path)


def write_parquet_atomic(df: pd.DataFrame, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + ".tmp")
    df.to_parquet(tmp, index=False)
    os.replace(tmp, path)


def content_keys(x: torch.Tensor) -> list[str]:
    """Khoá tất định theo nội dung ảnh (model giả không biết đường dẫn, chỉ thấy tensor)."""
    return [hashlib.sha1(t.numpy().tobytes()).hexdigest() for t in x]


def _quality(x: torch.Tensor) -> np.ndarray:
    """(B, 2) = (q_bright, q_blur) của từng ảnh. Ảnh hỏng (tensor 0) cho (0, 0)."""
    luma = torch.tensor(_LUMA).view(1, 3, 1, 1)
    gray = (x * luma).sum(1).mul(255).round().clamp(0, 255).to(torch.uint8).numpy()
    return np.asarray([quality_metrics(g) for g in gray], dtype=np.float32).reshape(-1, 2)


def _fake_embedder():
    return lambda x: fake_embed(content_keys(x), 768, seed=1)


def _real_embedder(name: str, device: str):
    w = weights_dir()
    hub = w / "torch_hub"
    repo = next((p for p in (hub / "facebookresearch_dinov2_main",
                             w / "facebookresearch_dinov2_main") if p.is_dir()), None)
    if repo is None or not (hub / "checkpoints" / f"{name}_pretrain.pth").is_file():
        raise missing_weights(f"DINOv2 ({name})")
    torch.hub.set_dir(str(hub))  # checkpoint nằm sẵn trong hub/checkpoints, không tải mạng
    model = torch.hub.load(str(repo), name, source="local").eval().to(device)
    mean = torch.tensor(IMAGENET_MEAN, device=device).view(1, 3, 1, 1)
    std = torch.tensor(IMAGENET_STD, device=device).view(1, 3, 1, 1)

    def embed(x):
        x = (x.to(device) - mean) / std
        with torch.autocast("cuda", dtype=torch.float16, enabled=device.startswith("cuda")):
            z = model(x)
        return torch.nn.functional.normalize(z.float(), dim=1).cpu().numpy()

    return embed


def extract_dino(job_dir, data_root, *, profile="local-4060", resume=False, limit=None,
                 device="cuda", shard=2048, workers=None) -> pd.DataFrame:
    """Ghi cache/dino_cls.npy + cache/feat_dino.parquet; trả bảng feat_dino."""
    job = Path(job_dir)
    cfg = load_config(profile)
    frames = load_frames(job, limit)
    fake = fake_models_enabled()
    if workers is None:
        workers = 0 if fake else cfg.workers
    name, size_hw = cfg.dino["model"], tuple(cfg.dino["size_hw"])
    embed = _fake_embedder() if fake else _real_embedder(name, device)

    def fn(x):
        return np.concatenate([embed(x).astype(np.float32), _quality(x)], axis=1)

    shard_dir = job / "cache" / "dino_shards"
    prepare_shard_dir(shard_dir, signature("dino", fake, name, size_hw, *frames["img_path"]),
                      resume)
    run_shards(fn, Images(frames, data_root, size_hw), shard_dir, bs=cfg.dino["batch"],
               shard=shard, workers=workers, progress=Progress(job, "dino", len(frames)))
    arr = concat_shards(shard_dir)
    Z = arr[:, :-2].astype(np.float16)
    scene_code = pd.factorize(frames["scene_token"])[0]
    nov = novelty_knn(Z.astype(np.float32), scene_code, frames["frame_idx"].to_numpy(),
                      k=cfg.novelty["k"], min_gap=cfg.mmr["min_gap"])
    feat = pd.DataFrame(dict(
        sample_token=frames["sample_token"].astype("string"), cam=frames["cam"].astype("string"),
        emb_row=np.arange(len(frames), dtype=np.int32), nov_knn=nov.astype(np.float32),
        q_bright=arr[:, -2].astype(np.float32), q_blur=arr[:, -1].astype(np.float32)))
    write_npy_atomic(Z, job / "cache" / "dino_cls.npy")
    write_parquet_atomic(feat, job / "cache" / "feat_dino.parquet")
    return feat
