"""PointPillars seed on trainval outside the benchmark pool + V diagnostic (planning/15).

pack-seed  (local) LIDAR_TOP keyframes of official TRAIN scenes OUTSIDE the pool -> ZIP parts
           + manifest.json (sha256 per part, scene list, pool split sha, optional code zip).
seed-split (Colab) <exp>/index.parquet for c4.lidar.tier1.train_seed: S = pool S + seed-pack
           scenes, T = pool P (holdout for the OpenPCDet post-train eval only). Never a pool
           V/T token. --link symlinks pool S/P keyframes + meta + maps into the seed root.
split-manifest     checks the pool job split (counts + scene->split sha), writes
           <job>/split_manifest.csv.
diag       (Colab) V diagnostic: IY@B capture B, reach r=1 m, paired scene bootstrap. NOT the
           T benchmark; does not replace prereg pitch-v2. Labels only via c4.rare.gt_rhcio and
           only for V and P tokens.

    python model/scripts/colab_pp_night.py pack-seed --data-root E:/nuscenes_trainval
        --pool-index model/workspace/jobs/pool_v24/lidar/index.parquet
        --out F:/vcf_pack/seed_pp_v1 [--code] [--dry-run]
    python model/scripts/colab_pp_night.py seed-split --pool-root P --seed-root R --exp E
        [--manifest M] [--link] [--dry-run]
    python model/scripts/colab_pp_night.py split-manifest --job J [--dry-run]
    python model/scripts/colab_pp_night.py diag --job J --data-root D --run A=SELDIR
        --run B=SELDIR --pair B-A --out O [--dry-run]

Exit: 0 ok · 2 missing/invalid input · 3 gate/invariant violation · 1 other error.
"""

import argparse
import hashlib
import json
import os
import subprocess
import sys
import time
import zipfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
WORKER = HERE.parent / "worker"
if str(WORKER) not in sys.path:
    sys.path.insert(0, str(WORKER))

DIAG_ID = "diag-v-pp-1"
# sha256 of the diag-prereg block, planning/15 SPEC-P02 §3 (fixed before any V result)
DIAG_PREREG_SHA256 = "54725cb7de15da7d14c16d5df2f197f2dfe27089196dfbd1f427d63a33fedacb"
POOL_COUNTS = {"T": 1389, "V": 3973, "S": 279, "P": 1112}
# sha256 of sorted "split:scene" lines of the 170-scene G0c pool (measured on jobs/pool_v24,
# planning/15 evidence/PREP)
POOL_SPLIT_SHA = "e467b1cb50abffae27512b86fbadde30f41222bcc16bfeaf2c39156c1a6288fd"
VRU_GROUPS = ("pedestrian", "bicycle", "motorcycle")
PP_SOURCES = ("pointpillars", "merged")
N_BOOT, BOOT_SEED, FRAC = 1000, 20261013, 0.05


class Gate(Exception):
    """Invariant violated (exit 3)."""


# ------------------------------------------------------------------------- nuScenes meta (json)
def version_dir(root: Path) -> Path:
    vs = sorted(p for p in Path(root).glob("v1.0-*") if p.is_dir())
    if len(vs) != 1:
        raise FileNotFoundError(
            f"{root}: need exactly one v1.0-* directory, found {[p.name for p in vs]}"
        )
    return vs[0]


def load_meta(root: Path) -> dict:
    vd = version_dir(root)
    read = lambda n: json.loads((vd / f"{n}.json").read_text(encoding="utf-8"))  # noqa: E731
    return dict(version=vd.name, scene=read("scene"), sample=read("sample"), log=read("log"))


def scene_keyframes(meta: dict) -> dict[str, list[tuple[str, str]]]:
    """scene name -> [(sample_token, keyframe LIDAR_TOP path relative to root)] by timestamp.
    Keyframe files are <logfile>__LIDAR_TOP__<sample.timestamp>.pcd.bin (checked by existence)."""
    logs = {lg["token"]: lg["logfile"] for lg in meta["log"]}
    scenes = {s["token"]: (s["name"], logs[s["log_token"]]) for s in meta["scene"]}
    out: dict[str, list] = {name: [] for name, _ in scenes.values()}
    for s in sorted(meta["sample"], key=lambda r: r["timestamp"]):
        name, logfile = scenes[s["scene_token"]]
        out[name].append(
            (s["token"], f"samples/LIDAR_TOP/{logfile}__LIDAR_TOP__{s['timestamp']}.pcd.bin")
        )
    return out


def complete_scenes(root: Path, kf: dict) -> tuple[list[str], list[str]]:
    """-> (scenes with every keyframe file present, scenes with only some present)."""
    full, partial = [], []
    for name, frames in kf.items():
        n = sum((Path(root) / rel).is_file() for _, rel in frames)
        if frames and n == len(frames):
            full.append(name)
        elif n:
            partial.append(name)
    return sorted(full), sorted(partial)


def official(name: str) -> str:
    from c4.lidar import nusc_splits as ns

    return "val" if name in set(ns.VAL) else "train" if name in set(ns.TRAIN) else "other"


def split_sha(smap: dict[str, str]) -> str:
    return hashlib.sha256(
        "\n".join(sorted(f"{v}:{k}" for k, v in smap.items())).encode()
    ).hexdigest()


def names_sha(names) -> str:
    return hashlib.sha256("\n".join(sorted(names)).encode()).hexdigest()


def pool_split_map(scene_names) -> dict[str, str]:
    from c4.lidar import load_lidar_config
    from c4.lidar.splits import plan_splits

    return plan_splits(list(scene_names), load_lidar_config())


def file_sha(p: Path) -> str:
    h = hashlib.sha256()
    with open(p, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def emit(d: dict) -> None:
    print(json.dumps(d, ensure_ascii=False, default=str), flush=True)


# ------------------------------------------------------------------------------------ pack-seed
def select_seed_scenes(root: Path, meta: dict, pool_scenes: set[str]) -> dict:
    kf = scene_keyframes(meta)
    full, partial = complete_scenes(root, kf)
    seed = [n for n in full if n not in pool_scenes and official(n) == "train"]
    skipped_val = [n for n in full if n not in pool_scenes and official(n) == "val"]
    if set(seed) & pool_scenes or any(official(n) != "train" for n in seed):
        raise Gate("seed scene inside pool or not official TRAIN")
    files = [rel for n in seed for _, rel in kf[n]]
    return dict(
        seed=seed,
        files=files,
        partial=[n for n in partial if n not in pool_scenes],
        skipped_val=skipped_val,
        n_full=len(full),
        kf=kf,
    )


def git_code_zip(repo: Path, out: Path, allow_dirty: bool) -> dict:
    sha = subprocess.check_output(["git", "-C", str(repo), "rev-parse", "HEAD"], text=True).strip()
    dirty = subprocess.check_output(
        ["git", "-C", str(repo), "status", "--porcelain", "--", "model", "docs"], text=True
    ).strip()
    if dirty and not allow_dirty:
        raise Gate("uncommitted changes under model/ or docs/: commit first (code zip = HEAD)")
    z = out / f"code_{sha[:7]}.zip"
    subprocess.run(
        ["git", "-C", str(repo), "archive", "--format=zip", "-o", str(z), "HEAD"], check=True
    )
    with zipfile.ZipFile(z) as zf:
        if zf.testzip() is not None or zf.comment.decode().strip() != sha:
            raise Gate("code zip check failed")
    return dict(
        repo_sha=sha,
        code=dict(name=z.name, size_bytes=z.stat().st_size, sha256=file_sha(z)),
        dirty=bool(dirty),
    )


def write_parts(root: Path, files: list[str], out: Path, limit: int) -> list[dict]:
    parts, zf, count, raw, path = [], None, 0, 0, None

    def finish():
        nonlocal zf, count, raw
        if zf is None:
            return
        zf.close()
        with zipfile.ZipFile(path) as chk:
            if len(chk.infolist()) != count or chk.testzip() is not None:
                raise Gate(f"{path.name}: zip verification failed")
        size = path.stat().st_size
        if size > limit:
            raise Gate(f"{path.name}: {size} > {limit}")
        parts.append(
            dict(
                name=path.name,
                size_bytes=size,
                sha256=file_sha(path),
                file_count=count,
                source_bytes=raw,
            )
        )
        emit(parts[-1])
        zf, count, raw = None, 0, 0

    for rel in files:
        size = (root / rel).stat().st_size
        name = "data/" + rel
        overhead = 256 + 2 * len(name.encode())
        if zf is not None and zf.fp.tell() + size + overhead + count * 512 + 4096 > limit:
            finish()
        if zf is None:
            path = out / f"seed_part_{len(parts) + 1:03d}.zip"
            zf = zipfile.ZipFile(path, "x", compression=zipfile.ZIP_STORED, allowZip64=True)
        zf.write(root / rel, name)
        count += 1
        raw += size
    finish()
    return parts


def cmd_pack_seed(a) -> int:
    import pandas as pd

    t0 = time.perf_counter()
    root = Path(a.data_root)
    meta = load_meta(root)
    pool = set(pd.read_parquet(a.pool_index, columns=["scene_name"])["scene_name"])
    sel = select_seed_scenes(root, meta, pool)
    nbytes = sum((root / r).stat().st_size for r in sel["files"])
    summary = dict(
        version=meta["version"],
        pool_scenes=len(pool),
        pool_scenes_sha256=names_sha(pool),
        pool_split_sha256=split_sha(pool_split_map(pool)),
        scenes_with_full_lidar=sel["n_full"],
        seed_scenes=len(sel["seed"]),
        seed_scenes_sha256=names_sha(sel["seed"]),
        seed_range=[sel["seed"][0], sel["seed"][-1]] if sel["seed"] else None,
        keyframes=len(sel["files"]),
        source_bytes=nbytes,
        excluded_val_outside_pool=len(sel["skipped_val"]),
        partial_scenes=sel["partial"],
        sweeps=0,
        dry_run=a.dry_run,
    )
    emit(summary)
    if a.dry_run:
        return 0
    if not sel["files"]:
        print("no seed scene outside the pool", file=sys.stderr)
        return 2
    out = Path(a.out)
    if out.exists() and any(out.iterdir()):
        raise Gate(f"{out} not empty: use a new output directory")
    if out.resolve().is_relative_to(root.resolve()):
        raise Gate("output inside the data root")
    out.mkdir(parents=True, exist_ok=True)
    code = git_code_zip(HERE.parents[1], out, a.allow_dirty) if a.code else {}
    parts = write_parts(root, sel["files"], out, a.part_bytes)
    manifest = dict(
        format="vcf-seed-colab-v1",
        archive_mode="independent_zip_parts",
        **summary,
        scenes=sel["seed"],
        file_count=len(sel["files"]),
        parts=parts,
        **code,
        created_utc=time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
    )
    manifest.pop("dry_run")
    with (out / "manifest.json").open("x", encoding="utf-8") as f:
        json.dump(manifest, f, indent=2)
    emit(
        dict(
            out=str(out),
            parts=len(parts),
            zip_bytes=sum(p["size_bytes"] for p in parts),
            elapsed_s=round(time.perf_counter() - t0, 1),
            repo_sha=code.get("repo_sha"),
        )
    )
    return 0


# ----------------------------------------------------------------------------------- seed-split
def build_seed_index(
    pool_root: Path, seed_root: Path, manifest: dict | None, expect_sha: str | None
):
    import pandas as pd

    meta = load_meta(pool_root)
    kf = scene_keyframes(meta)
    pool_scenes, partial = complete_scenes(pool_root, kf)
    if partial:
        raise Gate(f"pool root has partial scenes {partial[:3]}")
    smap = pool_split_map(pool_scenes)
    sha = split_sha(smap)
    if expect_sha and sha != expect_sha:
        raise Gate(f"pool split sha {sha} != expected {expect_sha}")
    if Path(seed_root).resolve() == Path(pool_root).resolve():
        extra = []
    else:
        own = [q.name for q in Path(seed_root).glob("v1.0-*")]
        if own and own != [meta["version"]]:
            raise Gate(f"seed root carries {own}, pool root {meta['version']}")
        extra = [n for n in complete_scenes(seed_root, kf)[0] if n not in smap]
    if manifest is not None and sorted(extra) != sorted(manifest["scenes"]):
        raise Gate(f"seed scenes on disk ({len(extra)}) != manifest ({len(manifest['scenes'])})")
    if any(official(n) == "val" for n in extra):
        raise Gate("official VAL scene in the seed set")
    rows = []
    for name in sorted(smap):
        role = {"S": "S", "P": "T"}.get(smap[name])
        if role:
            rows += [(t, name, role, rel, "pool") for t, rel in kf[name]]
    for name in sorted(extra):
        rows += [(t, name, "S", rel, "seed_pack") for t, rel in kf[name]]
    idx = pd.DataFrame(
        rows, columns=["sample_token", "scene_name", "split", "lidar_path", "source"]
    )
    forbidden = {t for n, s in smap.items() if s in ("V", "T") for t, _ in kf[n]}
    if forbidden & set(idx["sample_token"]):
        raise Gate("exp index contains a pool V/T token")
    info = dict(
        version=meta["version"],
        pool_scenes=len(smap),
        pool_split_sha256=sha,
        pool_split_counts={k: sum(v == k for v in smap.values()) for k in "SVPT"},
        train_scenes=int(idx.loc[idx.split == "S", "scene_name"].nunique()),
        train_frames=int((idx.split == "S").sum()),
        train_from_pool_S=int(((idx.split == "S") & (idx.source == "pool")).sum()),
        train_from_seed_pack=int((idx.source == "seed_pack").sum()),
        holdout_P_scenes=int(idx.loc[idx.split == "T", "scene_name"].nunique()),
        holdout_P_frames=int((idx.split == "T").sum()),
        seed_pack_scenes_sha256=names_sha(extra),
        index_sha256=hashlib.sha256(
            "\n".join(f"{t},{s}" for t, s in zip(idx.sample_token, idx.split)).encode()
        ).hexdigest(),
    )
    return idx, info, smap


def link_pool_files(idx, pool_root: Path, seed_root: Path, version: str) -> int:
    n = 0
    for sub in (version, "maps"):
        dst, src = seed_root / sub, pool_root / sub
        if not dst.exists() and src.exists():
            dst.symlink_to(src.resolve(), target_is_directory=True)
    for rel in idx.loc[idx.source == "pool", "lidar_path"]:
        dst = seed_root / rel
        if not dst.exists():
            dst.parent.mkdir(parents=True, exist_ok=True)
            dst.symlink_to((pool_root / rel).resolve())
            n += 1
    return n


def cmd_seed_split(a) -> int:
    pool_root, seed_root, exp = Path(a.pool_root), Path(a.seed_root), Path(a.exp)
    manifest = json.loads(Path(a.manifest).read_text(encoding="utf-8")) if a.manifest else None
    expect = a.expect_split_sha or (manifest or {}).get("pool_split_sha256")
    idx, info, _ = build_seed_index(
        pool_root, seed_root, manifest, None if expect == "none" else expect
    )
    same_root = seed_root.resolve() == pool_root.resolve()
    linked = 0
    if not a.dry_run and a.link and not same_root:
        linked = link_pool_files(idx, pool_root, seed_root, info["version"])
    check_root = {"pool": pool_root, "seed_pack": seed_root}
    root_of = (lambda r: seed_root) if (a.link and not a.dry_run) else (lambda r: check_root[r])
    missing = [p for p, r in zip(idx.lidar_path, idx.source) if not (root_of(r) / p).is_file()]
    info.update(linked=linked, missing_files=len(missing), dry_run=a.dry_run)
    emit(info)
    if missing:
        print(f"missing LIDAR files: {len(missing)} (e.g. {missing[:2]})", file=sys.stderr)
        return 2
    if a.dry_run:
        return 0
    out = exp / "index.parquet"
    if out.is_file():
        old = (
            json.loads((exp / "seed_split.json").read_text(encoding="utf-8"))
            if (exp / "seed_split.json").is_file()
            else {}
        )
        if old.get("index_sha256") == info["index_sha256"]:
            print(f"skip: {out} unchanged (index_sha256 {info['index_sha256'][:12]})")
            return 0
        if not a.force:
            raise Gate(f"{out} exists with another train set: new --exp or --force")
    exp.mkdir(parents=True, exist_ok=True)
    idx.to_parquet(out, index=False)
    (exp / "seed_split.json").write_text(json.dumps(info, indent=2), encoding="utf-8")
    print(f"wrote {out}: S={info['train_frames']} T(holdout P)={info['holdout_P_frames']}")
    return 0


# ------------------------------------------------------------------------------- split-manifest
def cmd_split_manifest(a) -> int:
    from c4.contracts import read_table

    idx = read_table(Path(a.job) / "lidar" / "index.parquet", "lidar_index")
    counts = idx.groupby("split").size().to_dict()
    smap = dict(zip(idx["scene_name"], idx["split"]))
    info = dict(frames=len(idx), scenes=len(smap), counts=counts, split_sha256=split_sha(smap))
    emit(info)
    if a.expect_counts != "none":
        exp = {k: int(v) for k, v in (kv.split("=") for kv in a.expect_counts.split(","))}
        if counts != exp:
            raise Gate(f"split counts {counts} != {exp}")
    expect_sha = a.expect_split_sha
    if expect_sha and expect_sha != "none" and info["split_sha256"] != expect_sha:
        raise Gate(f"split sha {info['split_sha256']} != {expect_sha}")
    if not a.dry_run:
        idx[["sample_token", "split"]].to_csv(Path(a.job) / "split_manifest.csv", index=False)
        print(f"wrote {Path(a.job) / 'split_manifest.csv'}")
    return 0


# ----------------------------------------------------------------------------------------- diag
def read_run(sel_dir: Path, split: str) -> dict:
    import pandas as pd

    from c4.contracts import read_table

    cfg = json.loads((sel_dir / "config_used.json").read_text(encoding="utf-8"))
    if cfg.get("pool_split") != split or cfg.get("ref_split") != "V":
        raise Gate(
            f"{sel_dir}: pool_split={cfg.get('pool_split')} ref_split={cfg.get('ref_split')}"
            f" (need {split}/V)"
        )
    frames = pd.read_parquet(sel_dir / "rare_frames.parquet", columns=["sample_token", "rank"])
    ranked = frames.dropna(subset=["rank"]).sort_values("rank")
    return dict(
        cfg=cfg,
        ranking=ranked["sample_token"].tolist(),
        objects=read_table(sel_dir / "rare_objects.parquet", "rare_objects"),
    )


def legacy_on(job: Path, index, split: str, frac: float) -> list[str]:
    """M1 c4_legacy t0_rar_mmr, configs/lidar.yaml defaults, restricted to `split` BEFORE selection
    (same functions as c4.cli.bench_pitch._legacy, pool branch)."""
    import numpy as np

    from c4.lidar import load_lidar_config
    from c4.lidar.extract import load_filter
    from c4.lidar.params import LidarParams, resolve
    from c4.lidar.score import combine, rarity
    from c4.lidar.select import select_mmr
    from c4.rare.eval import budget

    cfg = load_lidar_config()
    mask = (index["split"] == split).to_numpy()
    ix = index[mask].reset_index(drop=True)
    z = np.load(job / "lidar" / "z0.npy")[mask]
    keep = load_filter(job / "lidar", index)[mask]
    p, _ = resolve(LidarParams(tier=0, budget=frac), cfg, [0])
    sc = combine(ix, keep, rarity(z, ix["scene_token"].to_numpy(), p.k, keep), None, None, 1, 0, 0)
    sel, _ = select_mmr(
        sc,
        z,
        budget(len(ix), frac),
        p.lam,
        p.m,
        method="t0_rar_mmr",
        score_norm=cfg.get("mmr_score", "rank"),
    )
    return sel.sort_values("rank")["sample_token"].tolist()


def reach_flags(objects, gt_boxes, tf_rare: dict, radius: float = 1.0) -> dict[str, bool]:
    """Per-instance version of c4.rare.eval.reachability (same rule; totals must agree)."""
    by_frame: dict[str, list] = {}
    for t, x, y in zip(objects["sample_token"], objects["cx"], objects["cy"]):
        by_frame.setdefault(t, []).append((float(x), float(y)))
    gt = {
        (i, t): (float(x), float(y))
        for i, t, x, y in zip(
            gt_boxes["instance_token"], gt_boxes["sample_token"], gt_boxes["cx"], gt_boxes["cy"]
        )
        if i in tf_rare
    }
    r2, out = radius * radius, {}
    for i, frames in tf_rare.items():
        hit = False
        for f in frames:
            c = gt.get((i, f))
            if c is not None and any(
                (x - c[0]) ** 2 + (y - c[1]) ** 2 <= r2 for x, y in by_frame.get(f, ())
            ):
                hit = True
                break
        out[i] = hit
    return out


def bootstrap_reach(
    flags: dict[str, dict[str, bool]], inst_scene: dict[str, str], n_boot=N_BOOT, seed=BOOT_SEED
):
    """Paired scene-cluster bootstrap of reach (ratio estimator), same scene draws for every run."""
    import numpy as np
    import pandas as pd

    scenes = sorted(set(inst_scene.values()))
    pos = {s: k for k, s in enumerate(scenes)}
    tgt = np.zeros(len(scenes))
    for s in inst_scene.values():
        tgt[pos[s]] += 1
    hits = {}
    for run, fl in flags.items():
        h = np.zeros(len(scenes))
        for i, ok in fl.items():
            if ok:
                h[pos[inst_scene[i]]] += 1
        hits[run] = h
    rng = np.random.default_rng(seed)
    rows = []
    for _ in range(n_boot):
        w = np.bincount(rng.integers(0, len(scenes), len(scenes)), minlength=len(scenes))
        den = float(w @ tgt)
        rows.append({run: (float(w @ h) / den if den else np.nan) for run, h in hits.items()})
    return pd.DataFrame(rows)


def det_recall(objects, boxes: dict[str, list[dict]], radii=(1.0, 2.0)) -> list[dict]:
    """Recall of GT VRU boxes (>= 1 LiDAR point) by engine candidates within r metres (ego frame),
    split by candidate source (all / PointPillars-backed) and GT points (< 8 / >= 8)."""
    import numpy as np

    by_frame = {}
    for t, x, y, src in zip(
        objects["sample_token"], objects["cx"], objects["cy"], objects["source"]
    ):
        by_frame.setdefault(t, []).append((float(x), float(y), src in PP_SOURCES))
    rows = []
    for r in radii:
        acc = {}
        for tok, bs in boxes.items():
            cand = np.array(by_frame.get(tok, []), dtype=float).reshape(-1, 3)
            for b in bs:
                if b["pts"] < 1:
                    continue
                d2 = (
                    (cand[:, 0] - b["x"]) ** 2 + (cand[:, 1] - b["y"]) ** 2
                    if len(cand)
                    else np.zeros(0)
                )
                hit_any = bool((d2 <= r * r).any())
                hit_pp = bool(((d2 <= r * r) & (cand[:, 2] > 0)).any()) if len(cand) else False
                for key in ((b["group"], "<8" if b["pts"] < 8 else ">=8"), ("all", "all")):
                    a = acc.setdefault(key, [0, 0, 0])
                    a[0] += 1
                    a[1] += hit_any
                    a[2] += hit_pp
        rows += [
            dict(
                radius_m=r,
                group=g,
                pts=p,
                n_gt=n,
                recall_any=h / n if n else None,
                recall_pp=q / n if n else None,
            )
            for (g, p), (n, h, q) in sorted(acc.items())
        ]
    return rows


def pp_raw_stats(job: Path, tokens: set[str], class_names: list[str], base: int = 1) -> dict | None:
    import pickle

    import numpy as np

    p = job / "t1" / "preds_orig.pkl"
    if not p.is_file():
        return None
    with open(p, "rb") as f:
        preds = [d for d in pickle.load(f) if d["sample_token"] in tokens]
    sc = [np.asarray(d["scores"]) for d in preds]
    lab = np.concatenate(
        [np.asarray(d["labels"])[np.asarray(d["scores"]) >= 0.3] for d in preds] or [np.zeros(0)]
    )
    hist = {
        class_names[int(k) - base]
        if 0 <= int(k) - base < len(class_names)
        else f"label{int(k)}": int(v)
        for k, v in zip(*np.unique(lab, return_counts=True))
    }
    return dict(
        frames=len(preds),
        mean_boxes_ge_0_1=float(np.mean([(s >= 0.1).sum() for s in sc])),
        mean_boxes_ge_0_3=float(np.mean([(s >= 0.3).sum() for s in sc])),
        class_hist_ge_0_3=hist,
        sha256=file_sha(p),
    )


def cmd_diag(a) -> int:
    import numpy as np
    import pandas as pd

    from c4.contracts import read_table
    from c4.rare.candidates import load_class_map
    from c4.rare.config import load_rare_def
    from c4.rare.eval import (
        bootstrap_fixed,
        budget,
        metrics,
        normalized_yield,
        paired_ci,
        random_selector,
        reachability,
        target_frames,
    )

    if a.split != "V":
        raise Gate("diag only runs on V (T is closed: prereg pitch-v2, opened once)")
    job, out = Path(a.job), Path(a.out)
    index = read_table(job / "lidar" / "index.parquet", "lidar_index")
    pool = index.loc[index["split"] == "V", "sample_token"].tolist()
    holdout = index.loc[index["split"] == "P", "sample_token"].tolist()
    if not pool:
        raise FileNotFoundError("no V frame in lidar/index.parquet")
    runs = {}
    for spec in a.run:
        name, _, d = spec.partition("=")
        if not name or not d:
            raise Gate(f"--run needs NAME=SELECTION_DIR, got {spec}")
        runs[name] = dict(read_run(Path(d), "V"), dir=str(Path(d)))
    B = budget(len(pool), FRAC)
    plan = dict(
        diag_id=DIAG_ID,
        split="V",
        n_pool=len(pool),
        n_scenes=int(index.loc[index.split == "V", "scene_token"].nunique()),
        B=B,
        runs={
            k: dict(
                modelMode=v["cfg"]["modelMode"],
                profile=v["cfg"]["profile"],
                ranked=len(v["ranking"]),
            )
            for k, v in runs.items()
        },
    )
    emit(plan)
    if a.dry_run:
        return 0
    t0 = time.perf_counter()
    from c4.data.nusc import NuscTables
    from c4.rare.gt_rhcio import (
        RareDefNotFrozen,
        base_rates,
        fit_reference,
        frame_context,
        label_gt,
        load_boxes,
    )

    allowed = set(pool) | set(holdout)

    def labels_for(tokens):  # every label read of this script goes through here (V and P only)
        if not set(tokens) <= allowed:
            raise Gate("label read outside V/P")
        return load_boxes(tables, tokens)

    tables = NuscTables.load(a.data_root)
    if a.mini_smoke and tables.version_dir.name != "v1.0-mini":
        raise Gate("--mini-smoke is only accepted on v1.0-mini")
    cfg, cfg_sha = load_rare_def()
    boxes_v = labels_for(pool)
    ref = fit_reference(boxes_v, frame_context(tables, pool), cfg)
    if ref is None:
        raise RareDefNotFrozen("no reference")
    frame, inst = label_gt(
        tables, pool, ref, cfg, split=dict(zip(index["sample_token"], index["split"]))
    )
    rate = base_rates(frame)["r2_combo"]
    warnings = []
    if rate["rate"] > cfg.base_rate_cap or rate["scenes"] < cfg.min_support_scenes:
        if not a.mini_smoke:
            raise Gate(f"BaseRateTooHigh on V: {rate}")
        warnings.append(f"BaseRateTooHigh ignored (mini smoke): {rate}")
    tf_rare = target_frames(inst, capture="rare_form", gt_frame=frame)
    tf_any = target_frames(inst)
    pool_set = set(pool)
    sels = {k: [t for t in v["ranking"] if t in pool_set][:B] for k, v in runs.items()}
    sels["M1_legacy"] = legacy_on(job, index, "V", FRAC)
    rand = {f"random{s}": random_selector(s)(pool, B) for s in range(100)}
    boot = bootstrap_fixed({**sels, **rand}, frame, tf_any, capture="rare_form")
    boot["M0_random"] = boot[list(rand)].mean(axis=1)
    rows, observed = {}, {}
    for m, sel in sels.items():
        mt, ma = metrics(sel, frame, tf_rare), metrics(sel, frame, tf_any)
        observed[m] = mt["iy"]
        lo, hi = np.percentile(boot[m], [2.5, 97.5])
        rows[m] = dict(
            iy=mt["iy"], ci95=[float(lo), float(hi)], n_instances=mt["n_instances"], iy_a=ma["iy"]
        )
    rm = [metrics(s, frame, tf_rare)["iy"] for s in rand.values()]
    observed["M0_random"] = float(np.mean(rm))
    lo, hi = np.percentile(boot["M0_random"], [2.5, 97.5])
    rows["M0_random"] = dict(iy=observed["M0_random"], ci95=[float(lo), float(hi)])
    oracle_iy = None
    try:
        from c4.rare.eval import oracle_instance

        oracle_iy = metrics(oracle_instance(pool, B, tf_rare), frame, tf_rare)["iy"]
    except Exception as e:  # noqa: BLE001 — oracle is a reference only
        print(f"oracle skipped: {type(e).__name__}: {e}", file=sys.stderr)
    for m in rows:
        if oracle_iy:
            rows[m]["ny"] = normalized_yield(rows[m]["iy"], observed["M0_random"], oracle_iy)
    gt_df = pd.DataFrame(
        [
            dict(instance_token=b["instance"], sample_token=t, cx=b["x"], cy=b["y"])
            for t, bs in boxes_v.items()
            for b in bs
        ],
        columns=["instance_token", "sample_token", "cx", "cy"],
    )
    scene_of = dict(zip(frame["sample_token"], frame["scene_token"]))
    inst_scene = {i: scene_of[next(iter(sorted(fr)))] for i, fr in tf_rare.items() if fr}
    flags = {}
    for m, r in runs.items():
        flags[m] = reach_flags(r["objects"], gt_df, tf_rare)
        ref_total = reachability(r["objects"], gt_df, tf_rare)
        if ref_total["n_reachable"] != sum(flags[m].values()):
            raise Gate(f"reach mismatch for {m}: {ref_total} vs {sum(flags[m].values())}")
        rows[m].update(
            reach=ref_total["reach"],
            n_reachable=ref_total["n_reachable"],
            modelMode=r["cfg"]["modelMode"],
            profile=r["cfg"]["profile"],
            selection_dir=r["dir"],
        )
    rboot = bootstrap_reach(
        {m: {i: f for i, f in fl.items() if i in inst_scene} for m, fl in flags.items()}, inst_scene
    )
    for m in runs:
        lo, hi = np.percentile(rboot[m].dropna(), [2.5, 97.5])
        rows[m]["reach_ci95"] = [float(lo), float(hi)]
    deltas = []
    for pair in a.pair:
        x, _, y = pair.partition("-")
        if x not in sels or y not in sels:
            continue
        ci = paired_ci(boot, x, y)
        ci["delta"] = observed[x] - observed[y]
        d = dict(a=x, b=y, iy=ci, verdict="shown" if ci["lo"] > 0 else "not shown")
        if x in rboot and y in rboot:
            dr = (rboot[x] - rboot[y]).dropna()
            lo, hi = np.percentile(dr, [2.5, 97.5])
            d["reach"] = dict(
                delta=rows[x]["reach"] - rows[y]["reach"],
                lo=float(lo),
                hi=float(hi),
                n_boot=len(dr),
            )
            d["reach_verdict"] = "shown" if lo > 0 else "not shown"
        deltas.append(d)
    det = {}
    boxes_p = labels_for(holdout) if holdout else {}
    for m, r in runs.items():
        det[m] = dict(
            V=det_recall(r["objects"], boxes_v),
            P=det_recall(r["objects"], boxes_p) if boxes_p else [],
        )
        src = r["objects"]["source"].value_counts().to_dict()
        n_pp = src.get("merged", 0) + src.get("pointpillars", 0)
        # label-free coordinate sanity: PP boxes in the wrong frame almost never merge with clusters
        det[m]["sources"] = {k: int(v) for k, v in src.items()}
        det[m]["pp_merged_rate"] = (src.get("merged", 0) / n_pp) if n_pp else None
    cmap = load_class_map()
    pp = pp_raw_stats(
        job, set(pool), cmap.get("pp_class_names", []), int(cmap.get("pp_label_base", 1))
    )
    ckpt = (
        dict(path=a.ckpt, sha256=file_sha(Path(a.ckpt)))
        if a.ckpt and Path(a.ckpt).is_file()
        else None
    )
    report = dict(
        diag_id=DIAG_ID,
        diag_prereg_sha256=DIAG_PREREG_SHA256,
        label=(
            "MINI SMOKE (in-sample, no claim)"
            if a.mini_smoke
            else "DIAGNOSTIC on V (tune split, reference fitted on V: in-sample). NOT T, "
            "does not replace prereg pitch-v2; never 'optimal'."
        ),
        warnings=warnings,
        split="V",
        pool=len(pool),
        scenes=int(frame["scene_token"].nunique()),
        B=B,
        capture_primary="rare_form",
        capture_secondary="any",
        n_target_instances=len(tf_rare),
        base_rate_V=rate,
        rare_def_sha256=cfg_sha,
        reference_sha256=ref.sha256,
        bootstrap=dict(n_boot=N_BOOT, seed=BOOT_SEED, fixed_selections=True, cluster="scene"),
        oracle_iy=oracle_iy,
        methods=rows,
        deltas=deltas,
        detector_recall=det,
        pp_raw_V=pp,
        checkpoint=ckpt,
        selections={m: s for m, s in sels.items()},
        elapsed_s=round(time.perf_counter() - t0, 1),
    )
    out.mkdir(parents=True, exist_ok=True)
    (out / "diag_report.json").write_text(
        json.dumps(report, indent=2, ensure_ascii=False, default=float), encoding="utf-8"
    )
    lines = [
        f"# {DIAG_ID} — {report['label']}",
        "",
        f"N_V={len(pool)} · scenes={report['scenes']} · B={B} · "
        f"targets (capture B)={len(tf_rare)} · oracle IY={oracle_iy}",
        "",
        "| Run | modelMode | profile | IY@B (B) | CI95 | IY (A) | reach r=1 m | reach CI95 |",
        "|---|---|---|---:|---|---:|---:|---|",
    ]
    for m, v in rows.items():
        reach = f"{v['reach']:.3f} ({v['n_reachable']}/{len(tf_rare)})" if "reach" in v else "—"
        lines.append(
            f"| {m} | {v.get('modelMode', '—')} | {v.get('profile', '—')} | {v['iy']:.4f} | "
            f"[{v['ci95'][0]:.3f}; {v['ci95'][1]:.3f}] | "
            f"{v.get('iy_a', float('nan')):.4f} | {reach} | "
            f"{v.get('reach_ci95', '—')} |"
        )
    lines += [
        "",
        "| Δ | IY Δ [CI95] | verdict | reach Δ [CI95] | verdict |",
        "|---|---|---|---|---|",
    ]
    for d in deltas:
        r = d.get("reach")
        lines.append(
            f"| {d['a']} − {d['b']} | {d['iy']['delta']:+.4f} "
            f"[{d['iy']['lo']:+.3f}; {d['iy']['hi']:+.3f}] | "
            f"{d['verdict']} | "
            + (
                f"{r['delta']:+.3f} [{r['lo']:+.3f}; {r['hi']:+.3f}] | {d['reach_verdict']} |"
                if r
                else "— | — |"
            )
        )
    lines += ["", "Detector recall of GT VRU boxes (>=1 pt), r = 1 m, all groups:", ""]
    for m, dd in det.items():
        for sp in ("V", "P"):
            for row in dd[sp]:
                if row["radius_m"] == 1.0 and row["group"] == "all":
                    lines.append(
                        f"- {m} · {sp}: n_gt={row['n_gt']} recall_any={row['recall_any']:.3f} "
                        f"recall_pp={row['recall_pp']:.3f}"
                    )
    if pp:
        lines.append(
            f"- PP raw on V: {pp['mean_boxes_ge_0_1']:.1f} box/frame >=0.1 · "
            f"{pp['mean_boxes_ge_0_3']:.1f} >=0.3"
        )
    (out / "diag_table.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    print("\n".join(lines))
    return 0


# ----------------------------------------------------------------------------------------- main
def make_parser() -> argparse.ArgumentParser:
    ap = argparse.ArgumentParser(prog="colab_pp_night", description=__doc__.splitlines()[0])
    sub = ap.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("pack-seed", help="local: pack official TRAIN scenes outside the pool")
    p.add_argument("--data-root", required=True)
    p.add_argument(
        "--pool-index",
        required=True,
        help="lidar/index.parquet of the benchmark pool job (read only)",
    )
    p.add_argument("--out", default="F:/vcf_pack/seed_pp_v1")
    p.add_argument("--part-bytes", type=int, default=2_000_000_000)
    p.add_argument(
        "--code", action="store_true", help="also write code_<sha7>.zip = git archive HEAD"
    )
    p.add_argument("--allow-dirty", action="store_true")
    p.add_argument("--dry-run", action="store_true")
    s = sub.add_parser(
        "seed-split", help="Colab: <exp>/index.parquet for c4.lidar.tier1.train_seed"
    )
    s.add_argument("--pool-root", required=True)
    s.add_argument("--seed-root", required=True)
    s.add_argument("--exp", required=True)
    s.add_argument(
        "--manifest", default=None, help="seed pack manifest.json (scene list + pool split sha)"
    )
    s.add_argument("--expect-split-sha", default=None, help="'none' disables the pool split check")
    s.add_argument(
        "--link",
        action="store_true",
        help="symlink pool S/P keyframes + meta + maps into the seed root",
    )
    s.add_argument("--force", action="store_true")
    s.add_argument("--dry-run", action="store_true")
    m = sub.add_parser(
        "split-manifest", help="check pool job split, write <job>/split_manifest.csv"
    )
    m.add_argument("--job", required=True)
    m.add_argument("--expect-counts", default="T=1389,V=3973,S=279,P=1112", help="'none' disables")
    m.add_argument("--expect-split-sha", default=POOL_SPLIT_SHA, help="'none' disables")
    m.add_argument("--dry-run", action="store_true")
    d = sub.add_parser("diag", help="Colab: V diagnostic of rare_v24 runs (not T)")
    d.add_argument("--job", required=True)
    d.add_argument("--data-root", required=True)
    d.add_argument(
        "--run", action="append", required=True, help="NAME=<job>/engines/rare_v24/<sid>"
    )
    d.add_argument(
        "--pair",
        action="append",
        default=[],
        help="A-B paired delta, e.g. B_pp_lidar-A_cluster_lidar",
    )
    d.add_argument("--split", default="V", choices=["V", "T"], help="only V is accepted; T exits 3")
    d.add_argument("--ckpt", default=None, help="checkpoint to record (sha256)")
    d.add_argument("--out", required=True)
    d.add_argument("--dry-run", action="store_true")
    d.add_argument(
        "--mini-smoke", action="store_true", help="v1.0-mini only: base-rate gate becomes a warning"
    )
    return ap


def main(argv=None) -> int:
    for st in (sys.stdout, sys.stderr):
        try:
            st.reconfigure(encoding="utf-8", errors="replace")
        except AttributeError:
            pass
    a = make_parser().parse_args(argv)
    fn = {
        "pack-seed": cmd_pack_seed,
        "seed-split": cmd_seed_split,
        "split-manifest": cmd_split_manifest,
        "diag": cmd_diag,
    }[a.cmd]
    try:
        return fn(a)
    except Gate as e:
        print(f"GATE: {e}", file=sys.stderr)
        return 3
    except FileNotFoundError as e:
        print(f"missing/invalid input: {type(e).__name__}: {e}", file=sys.stderr)
        return 2
    except Exception as e:  # noqa: BLE001
        from c4.contracts import ContractError

        if isinstance(e, ContractError):
            print(f"missing/invalid input: {e}", file=sys.stderr)
            return 2
        raise


if __name__ == "__main__":
    os.environ.setdefault("PYTHONIOENCODING", "utf-8")
    sys.exit(main())
