"""S3: OpenCLIP ViT-B/16 image embedding (N × 512 float16, L2) + điểm 6 query mặc định,
và OpenClipTextEncoder (CPU, nạp lười) cho query tuỳ chỉnh.

Ảnh được co thẳng về 224×224 (không cắt giữa) để giữ nguyên toàn cảnh; rìa khung hình là nơi
vật thể hiếm hay xuất hiện.
"""
import os
from pathlib import Path

import numpy as np
import pandas as pd
import torch

from c4.config import load_config, load_queries
from c4.extract.base import Images, Progress, concat_shards, run_shards
from c4.extract.dino import (
    content_keys,
    load_frames,
    missing_weights,
    prepare_shard_dir,
    signature,
    weights_dir,
    write_npy_atomic,
    write_parquet_atomic,
)
from c4.extract.fake import fake_embed, fake_models_enabled
from c4.mining.query import query_scores

CLIP_SIZE = 224
CLIP_DIM = 512
CLIP_MEAN = (0.48145466, 0.4578275, 0.40821073)
CLIP_STD = (0.26862954, 0.26130258, 0.27577711)


class FakeTextEncoder:
    """Hash text → vector đơn vị (chạy CPU, không cần trọng số)."""

    def encode(self, texts: list[str]) -> np.ndarray:
        return fake_embed(list(texts), CLIP_DIM, seed=7)


def _load_open_clip(name: str, pretrained: str, device: str):
    d = weights_dir() / "open_clip"
    if not d.is_dir() or not any(d.iterdir()):
        raise missing_weights(f"OpenCLIP ({name}/{pretrained})")
    os.environ.setdefault("HF_HUB_OFFLINE", "1")  # job không dùng mạng
    import open_clip

    try:
        model, _, _ = open_clip.create_model_and_transforms(
            name, pretrained=pretrained, cache_dir=str(d), device=device)
    except (OSError, RuntimeError, ValueError) as e:
        raise FileNotFoundError(f"{missing_weights(f'OpenCLIP {name}')} [{e}]") from e
    return model.eval()


class OpenClipTextEncoder:
    """Cài đặt Plan 1 `TextEncoder`: encode(texts) → (len, 512) float32 L2. Nạp lười, một lần."""

    def __init__(self, model: str = "ViT-B-16", pretrained: str = "openai"):
        self._name, self._pretrained = model, pretrained
        self._model = self._tokenize = None
        self._fake = FakeTextEncoder()

    def encode(self, texts: list[str]) -> np.ndarray:
        if fake_models_enabled():
            return self._fake.encode(texts)
        if self._model is None:
            self._model = _load_open_clip(self._name, self._pretrained, "cpu")
            import open_clip

            self._tokenize = open_clip.get_tokenizer(self._name)
        with torch.inference_mode():
            z = self._model.encode_text(self._tokenize(list(texts)))
            z = torch.nn.functional.normalize(z.float(), dim=-1)
        return z.numpy().astype(np.float32)


def _fake_embedder():
    return lambda x: fake_embed(content_keys(x), CLIP_DIM, seed=2)


def _real_embedder(name: str, pretrained: str, device: str):
    model = _load_open_clip(name, pretrained, device)
    mean = torch.tensor(CLIP_MEAN, device=device).view(1, 3, 1, 1)
    std = torch.tensor(CLIP_STD, device=device).view(1, 3, 1, 1)

    def embed(x):
        x = (x.to(device) - mean) / std
        with torch.autocast("cuda", dtype=torch.float16, enabled=device.startswith("cuda")):
            z = model.encode_image(x)
        return torch.nn.functional.normalize(z.float(), dim=-1).cpu().numpy()

    return embed


def extract_clip(job_dir, data_root, *, profile="local-4060", resume=False, limit=None,
                 device="cuda", shard=2048, workers=None) -> pd.DataFrame:
    """Ghi cache/clip_img.npy + cache/feat_clip.parquet; trả bảng feat_clip."""
    job = Path(job_dir)
    cfg = load_config(profile)
    frames = load_frames(job, limit)
    fake = fake_models_enabled()
    if workers is None:
        workers = 0 if fake else cfg.workers
    name, pretrained = cfg.clip["model"], cfg.clip["pretrained"]
    embed = _fake_embedder() if fake else _real_embedder(name, pretrained, device)
    queries = load_queries()
    T = OpenClipTextEncoder(name, pretrained).encode([q["text"] for q in queries])

    shard_dir = job / "cache" / "clip_shards"
    prepare_shard_dir(shard_dir, signature("clip", fake, name, pretrained, *frames["img_path"]),
                      resume)
    run_shards(lambda x: embed(x).astype(np.float32),
               Images(frames, data_root, (CLIP_SIZE, CLIP_SIZE)), shard_dir,
               bs=cfg.clip["batch"], shard=shard, workers=workers,
               progress=Progress(job, "clip", len(frames)))
    C = concat_shards(shard_dir).astype(np.float16)
    mx, best = query_scores(C.astype(np.float32), T, [q["id"] for q in queries])
    feat = pd.DataFrame(dict(
        sample_token=frames["sample_token"].astype("string"), cam=frames["cam"].astype("string"),
        qry_max=mx.astype(np.float32), qry_best=pd.array(best, dtype="string")))
    write_npy_atomic(C, job / "cache" / "clip_img.npy")
    write_parquet_atomic(feat, job / "cache" / "feat_clip.parquet")
    return feat
