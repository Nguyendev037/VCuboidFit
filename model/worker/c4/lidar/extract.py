"""M3 · chạy descriptor cho cả chỉ mục (song song CPU), ghi desc_raw.npz + filter.parquet + BEV.

Không cần torch: chạy được trên bản CPU thuần (L1) lẫn trong Docker (L2/C).
"""
import json
import os
import time
from pathlib import Path

import numpy as np
import pandas as pd

from c4.contracts import read_table, validate, write_table
from c4.lidar.descriptor import BLOCKS, embed, frame_descriptor, stack

BATCH = 256


class StageProgress:
    """progress/<stage>.json = {done, total, updated_at} — cùng định dạng runner đang đọc."""

    def __init__(self, job_dir, stage: str, total: int):
        self.path = Path(job_dir) / "progress" / f"{stage}.json"
        self.total, self.done = int(total), 0

    def advance(self, n: int) -> None:
        self.done += n
        self.path.parent.mkdir(parents=True, exist_ok=True)
        tmp = self.path.with_name(self.path.name + ".tmp")
        tmp.write_text(json.dumps(dict(done=self.done, total=self.total, peak_vram_mb=0,
                                       updated_at=time.strftime("%Y-%m-%dT%H:%M:%S"))),
                       encoding="utf-8")
        for attempt in range(20):
            try:
                os.replace(tmp, self.path)
                return
            except PermissionError:  # Windows: runner đang đọc file đích
                if attempt == 19:
                    raise
                time.sleep(0.05)


def _one(path, cfg, bev_path):
    return frame_descriptor(path, cfg, bev_path)


def extract_all(index: pd.DataFrame, data_root, out_dir, cfg: dict, n_jobs: int = -1,
                progress: StageProgress | None = None, bev_dir=None):
    """Trả (raw {khối: (N, d)}, filter_df). Ghi `<out_dir>/desc_raw.npz`, `filter.parquet`."""
    from joblib import Parallel, delayed

    root, out_dir = Path(data_root), Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    tokens = index["sample_token"].tolist()
    paths = [root / p for p in index["lidar_path"]]
    bevs = [None if bev_dir is None else Path(bev_dir) / f"{t}.png" for t in tokens]
    results = []
    with Parallel(n_jobs=n_jobs, backend="loky") as par:
        for s0 in range(0, len(paths), BATCH):
            chunk = par(delayed(_one)(p, cfg, b)
                        for p, b in zip(paths[s0:s0 + BATCH], bevs[s0:s0 + BATCH]))
            results.extend(chunk)
            if progress:
                progress.advance(len(chunk))
    raw, keep = stack(results, cfg)
    filt = validate(pd.DataFrame(dict(
        sample_token=tokens, n_points=[r["n_points"] for r in results], keep=keep,
        reason=[r["reason"] for r in results])), "lidar_filter")
    tmp = out_dir / "desc_raw.tmp.npz"
    np.savez(tmp, **raw, tokens=np.asarray(tokens))
    os.replace(tmp, out_dir / "desc_raw.npz")
    write_table(filt, str(out_dir / "filter.parquet"), "lidar_filter",
                n_keep=int(keep.sum()), n_total=len(keep))
    return raw, filt


def load_raw(out_dir, index: pd.DataFrame) -> dict[str, np.ndarray]:
    """desc_raw theo đúng thứ tự `index` (lệch token ⇒ ContractError)."""
    from c4.contracts import ContractError

    d = np.load(Path(out_dir) / "desc_raw.npz")
    toks = d["tokens"].astype(str)
    pos = {t: i for i, t in enumerate(toks)}
    try:
        rows = np.array([pos[t] for t in index["sample_token"]], int)
    except KeyError as e:
        raise ContractError(f"desc_raw.npz thiếu sample_token {e}") from e
    return {k: d[k][rows] for k in BLOCKS}


def load_filter(out_dir, index: pd.DataFrame) -> np.ndarray:
    f = read_table(str(Path(out_dir) / "filter.parquet"), "lidar_filter").set_index("sample_token")
    return f.loc[index["sample_token"], "keep"].to_numpy(bool)


def embed_split(raw, keep, cfg, drop_blocks=()) -> np.ndarray:
    return embed(raw, keep, cfg["pca_dim"], drop_blocks)
