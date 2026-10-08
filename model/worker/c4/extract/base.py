"""Khung extract: dataset ảnh, chạy theo shard có resume, lùi batch khi OOM, tiến độ."""
import json
import logging
import os
import sys
import time
from datetime import datetime
from pathlib import Path

import numpy as np
import torch
from PIL import Image
from torch.utils.data import DataLoader, Dataset, Subset

log = logging.getLogger("c4.extract")
PROGRESS_EVERY_S = 2.0
REPLACE_RETRIES = 20


class Images(Dataset):
    """Item = (tensor float32 3×H×W trong [0,1], ok). Ảnh hỏng/thiếu → tensor 0, ok=False."""

    def __init__(self, frames, data_root, size_hw):
        self.tokens = frames["sample_token"].tolist()
        self.paths = frames["img_path"].tolist()
        self.root = Path(data_root)
        self.size_hw = tuple(size_hw)

    def __len__(self):
        return len(self.paths)

    def __getitem__(self, i):
        h, w = self.size_hw
        try:
            with Image.open(self.root / self.paths[i]) as im:
                arr = np.asarray(im.convert("RGB").resize((w, h), Image.BILINEAR), dtype=np.uint8)
            return torch.from_numpy(arr.copy()).permute(2, 0, 1).float() / 255.0, True
        except Exception as e:  # noqa: BLE001 — một ảnh hỏng không được làm sập cả stage
            log.warning("unreadable image sample_token=%s path=%s (%s)",
                        self.tokens[i], self.paths[i], e)
            return torch.zeros(3, h, w, dtype=torch.float32), False


class Progress:
    """progress/<stage>.json = {done, total, peak_vram_mb, updated_at}, ghi tối đa mỗi 2 s."""

    def __init__(self, job_dir, stage, total):
        self.path = Path(job_dir) / "progress" / f"{stage}.json"
        self.total = int(total)
        self.done = 0
        self._last = None

    def advance(self, n):
        self.done += int(n)  # n âm = lùi khi chạy lại shard sau OOM
        now = time.monotonic()
        if self._last is None or now - self._last >= PROGRESS_EVERY_S:
            self.flush()

    def flush(self):
        self._last = time.monotonic()
        peak = int(torch.cuda.max_memory_allocated() / 2**20) if torch.cuda.is_available() else 0
        info = dict(done=self.done, total=self.total, peak_vram_mb=peak,
                    updated_at=datetime.now().astimezone().isoformat(timespec="seconds"))
        self.path.parent.mkdir(parents=True, exist_ok=True)
        tmp = self.path.with_name(self.path.name + ".tmp")
        tmp.write_text(json.dumps(info), encoding="utf-8")
        for _ in range(REPLACE_RETRIES):
            try:
                os.replace(tmp, self.path)
                return
            except PermissionError:  # Windows: runner đang mở file đích để đọc
                time.sleep(0.05)
        # tiến độ chỉ là thông tin phụ: lần ghi sau sẽ bù, tuyệt đối không làm sập stage
        log.warning("progress file locked, skipped one write: %s", self.path)


def _shard_path(out: Path, k: int) -> Path:
    return out / f"shard_{k:05d}.npy"


def run_shards(fn, ds, out_dir, bs, shard=2048, workers=4, progress=None) -> Path:
    """Chạy fn(batch_tensor) -> ndarray trên từng shard, ghi shard_XXXXX.npy nguyên tử.

    Resume: bắt đầu từ shard đầu tiên chưa có file. OOM: chia đôi bs và chạy lại đúng shard;
    bs = 1 vẫn OOM → sys.exit(3).
    """
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    n = len(ds)
    n_shards = -(-n // shard)
    k = 0
    while k < n_shards and _shard_path(out, k).is_file():
        k += 1
    progress.advance(min(n, k * shard))
    while k < n_shards:
        lo, hi = k * shard, min(n, (k + 1) * shard)
        loader = DataLoader(Subset(ds, range(lo, hi)), batch_size=bs, shuffle=False,
                            num_workers=workers)
        parts, done = [], 0
        try:
            with torch.inference_mode():
                for x, _ok in loader:
                    parts.append(np.asarray(fn(x)))
                    done += len(x)
                    progress.advance(len(x))
        except torch.cuda.OutOfMemoryError:
            progress.advance(-done)
            if bs == 1:
                sys.exit(3)
            bs = max(1, bs // 2)
            log.warning("OOM at shard %d → batch %d", k, bs)
            if torch.cuda.is_available():
                torch.cuda.empty_cache()
            continue
        tmp = out / f"shard_{k:05d}.npy.tmp"
        with open(tmp, "wb") as f:
            np.save(f, np.concatenate(parts))
        os.replace(tmp, _shard_path(out, k))
        k += 1
    progress.flush()
    return out


def concat_shards(out_dir) -> np.ndarray:
    files = sorted(Path(out_dir).glob("shard_*.npy"))
    if not files:
        raise FileNotFoundError(f"{out_dir}: không có shard nào")
    return np.concatenate([np.load(f) for f in files])
