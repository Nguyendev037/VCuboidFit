"""M3a · crop vật -> OpenCLIP, r_sem, điểm khái niệm zero-shot (planning/11 SPEC-P06 §4). Không VLM/LLM.
`build_crops` là bước DUY NHẤT cần torch/GPU (import lười); `semantic_scores` chạy CPU không torch.
Phía chọn không đọc nhãn: ngưỡng khái niệm = phân vị 99,5 trên crop của frame `ref_split`."""
import hashlib
import json
import time
from pathlib import Path

import numpy as np
import pandas as pd
import yaml

from c4.config import CONFIG_DIR, load_config
from c4.contracts import read_table, write_table
from c4.lidar.score import pct_rank
from c4.mining.novelty import novelty_knn
from c4.mining.query import query_scores
from c4.rare.project import project_objects

CLIP_DIM = 512
CONCEPT_PCT = 99.5
CROP_FILES = ("rare_crops.npy", "rare_crops.parquet", "concepts_text.npy", "concepts_text.json")


class CropsStale(ValueError):
    """rare_crops không khớp tập ứng viên hiện tại (CLI exit 2 CROPS_STALE)."""


class ConceptRefEmpty(ValueError):
    """0 crop trên ref_split (CLI exit 3 CONCEPT_REF_EMPTY)."""


def load_concepts(path: Path | None = None) -> tuple[list[dict], str]:
    p = Path(path) if path else CONFIG_DIR / "concepts_v1.yaml"
    raw = p.read_bytes()
    return yaml.safe_load(raw.decode("utf-8"))["concepts"], hashlib.sha256(raw).hexdigest()


def objects_signature(objs: pd.DataFrame) -> str:
    """Chữ ký tập ứng viên (khoá + hình học làm tròn 1 mm) để phát hiện rare_crops cũ."""
    d = objs.sort_values(["sample_token", "object_id"], kind="mergesort")
    cols = [d[c].to_numpy(np.float32) for c in ("cx", "cy", "l", "w")]
    lines = [f"{t},{o},{a:.3f},{b:.3f},{c:.3f},{e:.3f}"
             for t, o, a, b, c, e in zip(d["sample_token"], d["object_id"], *cols)]
    return hashlib.sha256("\n".join(lines).encode()).hexdigest()


def latest_selection(job: Path, sid: str | None = None) -> Path:
    """Thư mục engines/rare_v24/<sid> (sid cho trước, hoặc bản rare_objects mới nhất theo mtime)."""
    base = job / "engines" / "rare_v24"
    files = [base / sid / "rare_objects.parquet"] if sid else         sorted(base.glob("*/rare_objects.parquet"), key=lambda p: p.stat().st_mtime)
    if not files or not files[-1].is_file():
        raise FileNotFoundError(f"engines/rare_v24/{sid or '*'}/rare_objects.parquet (chạy `rare run` trước)")
    return files[-1].parent


def _crop_batches(items, data_root: Path, margin: float, batch: int, skipped: list):
    """Sinh (rows, uint8 (b,224,224,3)). Ảnh thiếu/hỏng: bỏ các crop của ảnh đó, đếm vào `skipped`."""
    from PIL import Image

    buf, rows = [], []
    for (path, group) in items:
        try:
            with Image.open(data_root / path) as im:
                im = im.convert("RGB")
                W, H = im.size
                for r in group:
                    bw, bh = r.x2 - r.x1, r.y2 - r.y1
                    box = (max(r.x1 - margin * bw, 0), max(r.y1 - margin * bh, 0),
                           min(r.x2 + margin * bw, W), min(r.y2 + margin * bh, H))
                    if box[2] - box[0] < 2 or box[3] - box[1] < 2:
                        skipped.append(r)
                        continue
                    buf.append(np.asarray(im.crop(tuple(int(round(v)) for v in box)).resize((224, 224), Image.BILINEAR),
                                          dtype=np.uint8).copy())
                    rows.append(r)
                    if len(buf) == batch:
                        yield rows, np.stack(buf)
                        buf, rows = [], []
        except Exception:  # noqa: BLE001 — một ảnh hỏng không được làm sập cả bước
            skipped.extend(group)
    if buf:
        yield rows, np.stack(buf)


def build_crops(job_dir, data_root, *, device: str = "cuda", margin: float = 0.2, batch: int = 64,
                sid: str | None = None, profile: str = "local-4060") -> dict:
    """Ghi cache/rare_crops.{npy,parquet} + cache/concepts_text.{npy,json}; trả số liệu.

    rare_objects = bản mới nhất của job (hoặc `sid`). Crop nới `margin` mỗi cạnh, co thẳng 224×224 (không center-crop)."""
    from c4.extract.fake import fake_embed, fake_models_enabled

    t0 = time.time()
    job, root = Path(job_dir), Path(data_root)
    sel = latest_selection(job, sid)
    objs = read_table(sel / "rare_objects.parquet", "rare_objects")
    for rel in ("index/cam_poses.parquet", "index/frames.parquet"):
        if not (job / rel).is_file():
            raise FileNotFoundError(rel)
    poses = read_table(job / "index" / "cam_poses.parquet", "cam_poses")
    frames = pd.read_parquet(job / "index" / "frames.parquet", columns=["sample_token", "cam", "img_path"])
    proj = project_objects(objs, poses)
    proj = proj.merge(frames, on=["sample_token", "cam"], how="left")
    proj["img_path"] = proj["img_path"].fillna("")
    cfg = load_config(profile)
    name, pretrained = cfg.clip["model"], cfg.clip["pretrained"]
    fake = fake_models_enabled()
    if fake:  # không torch: embedding giả tất định theo khoá vật
        embed_text = lambda ps: fake_embed(list(ps), CLIP_DIM, seed=7)  # noqa: E731
        embed = None
    else:
        import torch

        from c4.extract.clip import OpenClipTextEncoder, _real_embedder
        embed_text = OpenClipTextEncoder(name, pretrained).encode
        real = _real_embedder(name, pretrained, device)

        def embed(u8):
            with torch.inference_mode():
                return real(torch.from_numpy(u8).permute(0, 3, 1, 2).float() / 255.0)

    groups = [(p, list(g.itertuples(index=False))) for p, g in proj.groupby("img_path", sort=True)]
    skipped, done_rows, feats = [], [], []
    for rows, x in _crop_batches(groups, root, margin, batch, skipped):
        z = fake_embed([f"{r.sample_token}|{r.object_id}" for r in rows], CLIP_DIM, seed=2) if fake else embed(x)
        feats.append(z.astype(np.float16))
        done_rows += rows
    C = np.concatenate(feats) if feats else np.zeros((0, CLIP_DIM), np.float16)
    keep = pd.DataFrame(done_rows, columns=proj.columns).drop(columns="img_path") if done_rows \
        else proj.iloc[:0].drop(columns="img_path")
    concepts, csha = load_concepts()
    prompts = [p for c in concepts for p in c["prompts"]]
    T = np.asarray(embed_text(prompts), np.float32)

    cache = job / "cache"
    cache.mkdir(parents=True, exist_ok=True)
    np.save(cache / "rare_crops.npy", C)
    write_table(keep, cache / "rare_crops.parquet", "rare_obj_cam", sid=sel.name,
                objects_sha=objects_signature(objs), concepts_sha=csha, clip=f"{name}/{pretrained}", fake=fake)
    np.save(cache / "concepts_text.npy", T)
    (cache / "concepts_text.json").write_text(json.dumps(
        {"concepts_sha256": csha, "ids": [c["id"] for c in concepts], "groups": [c["group"] for c in concepts],
         "prompts": prompts, "prompts_per_concept": [len(c["prompts"]) for c in concepts]},
        ensure_ascii=False, indent=2), encoding="utf-8")
    return {"sid": sel.name, "n_objects": len(objs), "n_projected": len(proj), "n_crops": len(keep),
            "crops_skipped": len(skipped), "elapsed_s": round(time.time() - t0, 1), "dir": cache}


def check_crops(job_dir, candidates: pd.DataFrame) -> Path:
    """Kiểm cache M3 đủ và khớp tập ứng viên. Thiếu => FileNotFoundError (tên file); lệch => CropsStale."""
    cache = Path(job_dir) / "cache"
    miss = [f"cache/{n}" for n in CROP_FILES if not (cache / n).is_file()]
    if miss:
        raise FileNotFoundError(", ".join(miss))
    meta = json.loads((cache / "rare_crops.parquet.manifest.json").read_text(encoding="utf-8"))
    if meta.get("objects_sha") != objects_signature(candidates):
        raise CropsStale("CROPS_STALE: rare_crops khác tập ứng viên hiện tại; chạy lại `rare crops`")
    return cache


def semantic_scores(job_dir, index: pd.DataFrame, ref_split: str = "V") -> pd.DataFrame:
    """CPU, không torch. -> sample_token, object_id, r_sem, concept_top, concept_score, concept_group (mỗi crop một hàng).

    r_sem = pct_rank(novelty_knn(crops, scene, frame_idx, k=10, min_gap=4)) trên mọi crop. Điểm khái niệm = max cosine
    các prompt; ngưỡng mỗi khái niệm = phân vị 99,5 trên crop thuộc frame `ref_split` ("all" = mọi frame)."""
    cache = Path(job_dir) / "cache"
    C = np.load(cache / "rare_crops.npy").astype(np.float32)
    keys = read_table(cache / "rare_crops.parquet", "rare_obj_cam")
    T = np.load(cache / "concepts_text.npy")
    meta = json.loads((cache / "concepts_text.json").read_text(encoding="utf-8"))
    ids, groups, per = meta["ids"], meta["groups"], meta["prompts_per_concept"]
    if len(keys) != len(C):
        raise CropsStale("CROPS_STALE: số hàng rare_crops.npy khác rare_crops.parquet")
    info = index.set_index("sample_token")
    tok = keys["sample_token"].to_numpy()
    scene = info["scene_token"].reindex(tok).astype("category").cat.codes.to_numpy()
    fidx = info["frame_idx"].reindex(tok).to_numpy()
    split = info["split"].reindex(tok).to_numpy()
    allm = np.ones(len(keys), bool)
    nov = novelty_knn(C, scene, fidx, k=10, min_gap=4) if len(C) else np.zeros(0, np.float32)
    r_sem = pct_rank(nov, allm) if len(C) else np.zeros(0, np.float32)
    ref = allm if ref_split == "all" else (split == ref_split)
    if not ref.any():
        raise ConceptRefEmpty(f"CONCEPT_REF_EMPTY: 0 crop trên ref_split={ref_split}")
    S, thr, pr, off = [], [], [], 0
    for cid, k in zip(ids, per):
        s, _ = query_scores(C, T[off:off + k], [cid] * k)
        off += k
        S.append(s)
        thr.append(float(np.percentile(s[ref], CONCEPT_PCT)))
        pr.append(pct_rank(s, allm))
    S, thr, pr = np.stack(S, 1), np.array(thr), np.stack(pr, 1)
    margin = np.where(S > thr, S - thr, -np.inf)
    best = margin.argmax(1)
    hit = np.isfinite(margin.max(1))
    out = keys[["sample_token", "object_id"]].copy()
    out["r_sem"] = r_sem.astype(np.float32)
    out["concept_top"] = np.where(hit, np.array(ids, object)[best], "")
    out["concept_score"] = np.where(hit, pr[np.arange(len(C)), best], np.nan).astype(np.float32)
    out["concept_group"] = np.where(hit, np.array(groups, object)[best], "")
    return out
