"""Pack available official TRAIN LiDAR + 10 sweeps; exclude historical benchmark T."""

import argparse
import hashlib
import json
import sys
import zipfile
from datetime import datetime, timezone
from pathlib import Path, PurePosixPath

WORKER = Path(__file__).resolve().parents[1] / "worker"
sys.path.insert(0, str(WORKER))


class Gate(ValueError):
    """Integrity/partition violation (exit 3)."""


def digest(path):
    with Path(path).open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def read_json(path):
    return json.loads(Path(path).read_text(encoding="utf-8-sig"))


def safe_path(root, relative):
    p = PurePosixPath(relative)
    if p.is_absolute() or ".." in p.parts or "\\" in relative or ":" in relative:
        raise Gate(f"unsafe relative path: {relative}")
    f = Path(root) / relative
    if not f.resolve().is_relative_to(Path(root).resolve()) or f.is_symlink():
        raise Gate(f"unsafe source path: {relative}")
    return f


def check_scenes(train, evaluation, excluded):
    from c4.lidar.nusc_splits import TRAIN, VAL

    a, b, c = set(train), set(evaluation), set(excluded)
    if not a or not b or not a <= set(TRAIN) or not b <= set(VAL):
        raise Gate("expected nonempty official TRAIN and VAL partitions")
    if a & b or (a | b) & c:
        raise Gate("scene overlap or historical benchmark T included")


def scene_frames(root):
    meta = Path(root) / "v1.0-trainval"
    scenes = {r["token"]: r for r in read_json(meta / "scene.json")}
    logs = {r["token"]: r["logfile"] for r in read_json(meta / "log.json")}
    frames = {}
    sample_scene = {}
    for r in read_json(meta / "sample.json"):
        sc = scenes[r["scene_token"]]
        name = sc["name"]
        relative = f"samples/LIDAR_TOP/{logs[sc['log_token']]}__LIDAR_TOP__{r['timestamp']}.pcd.bin"
        frames.setdefault(name, []).append((r["token"], relative))
        sample_scene[r["token"]] = name
    return frames, sample_scene


def lidar_records(root):
    meta = Path(root) / "v1.0-trainval"
    sensors = {r["token"] for r in read_json(meta / "sensor.json") if r["channel"] == "LIDAR_TOP"}
    calibrated = {
        r["token"]
        for r in read_json(meta / "calibrated_sensor.json")
        if r["sensor_token"] in sensors
    }
    # Keep only LiDAR rows; source table is large and must not remain in memory.
    rows = read_json(meta / "sample_data.json")
    records = {r["token"]: r for r in rows if r["calibrated_sensor_token"] in calibrated}
    del rows
    return records


def coverage(root, train, evaluation, excluded):
    check_scenes(train, evaluation, excluded)
    frames, sample_scene = scene_frames(root)
    selected = set(train) | set(evaluation)
    records = lidar_records(root)
    keyframes = {
        r["sample_token"]: r
        for r in records.values()
        if r["is_key_frame"] and sample_scene.get(r["sample_token"]) in selected
    }
    files = set()
    for scene in sorted(selected):
        for token, filename in frames[scene]:
            if token not in keyframes:
                raise Gate(f"missing keyframe metadata: {token}")
            record = keyframes[token]
            if record["filename"] != filename:
                raise Gate(f"keyframe filename mismatch: {token}")
            files.add(filename)
            previous = record["prev"]
            for _ in range(9):
                if not previous:
                    break
                if previous not in records:
                    raise Gate(f"missing predecessor metadata: {previous}")
                r = records[previous]
                if sample_scene.get(r["sample_token"]) != scene:
                    raise Gate(f"predecessor crosses scene boundary: {previous}")
                files.add(r["filename"])
                previous = r["prev"]
    # Include all sweeps assigned to selected scenes, not only one keyframe's history.
    files.update(
        r["filename"] for r in records.values() if sample_scene.get(r["sample_token"]) in selected
    )
    for relative in files:
        if not safe_path(root, relative).is_file():
            raise Gate(f"missing required LiDAR/sweep: {relative}")
    return files, frames


def inventory(root, pool_index):
    import pandas as pd

    from c4.lidar.nusc_splits import TRAIN, VAL

    root = Path(root)
    frames, _ = scene_frames(root)
    full = {
        name
        for name, items in frames.items()
        if items and all(safe_path(root, p).is_file() for _, p in items)
    }
    pool = pd.read_parquet(pool_index)
    old_pool = set(pool.scene_name)
    excluded = sorted(set(pool.loc[pool.split == "T", "scene_name"]))
    train = sorted(full & set(TRAIN))
    evaluation = sorted((full & set(VAL)) - old_pool)
    print("Checking metadata predecessor closure (large sample_data.json)...", flush=True)
    files, frames = coverage(root, train, evaluation, excluded)
    for directory in (root / "v1.0-trainval", root / "maps"):
        files.update(f.relative_to(root).as_posix() for f in directory.rglob("*") if f.is_file())
    items = [{"path": p, "size_bytes": safe_path(root, p).stat().st_size} for p in sorted(files)]
    return {
        "format": "vcf-trainval-full-v1",
        "version": "v1.0-trainval",
        "sweeps": 10,
        "train_scenes": train,
        "eval_scenes": evaluation,
        "excluded_T_scenes": excluded,
        "train_frames": sum(len(frames[n]) for n in train),
        "eval_frames": sum(len(frames[n]) for n in evaluation),
        "files": items,
        "source_bytes": sum(f["size_bytes"] for f in items),
        "created_utc": datetime.now(timezone.utc).isoformat(),
    }


def code_archive(out):
    repo = WORKER.parents[1]
    candidates = [WORKER / "pyproject.toml"]
    for directory in (WORKER / "c4", WORKER / "service"):
        candidates.extend(
            p
            for p in directory.rglob("*")
            if p.is_file() and p.suffix in (".py", ".yaml", ".json", ".toml")
        )
    candidates.extend(
        [
            repo / "model/scripts/trainval_full.py",
            repo / "model/scripts/colab_setup.sh",
            repo / "model/docker/tier1/patch_pcdet.py",
            repo / "model/notebooks/TrainModel.ipynb",
        ]
    )
    source = hashlib.sha256()
    archive = Path(out) / "code_trainmodel.zip"
    with zipfile.ZipFile(archive, "w", zipfile.ZIP_DEFLATED) as z:
        for p in sorted(set(candidates)):
            relative = p.relative_to(repo).as_posix()
            source.update((relative + "\0" + digest(p) + "\n").encode())
            z.write(p, relative)
        z.comment = source.hexdigest().encode()
    return {
        "name": archive.name,
        "size_bytes": archive.stat().st_size,
        "sha256": digest(archive),
        "source_hash": source.hexdigest(),
    }


def pack(args):
    root, out = args.data_root.resolve(), args.out.resolve()
    if out.is_relative_to(root) or args.part_bytes <= 0:
        raise Gate("output cannot be inside source; part size must be positive")
    if not args.dry_run and out.exists() and any(out.iterdir()):
        raise Gate("refuse nonempty output directory")
    manifest = inventory(root, args.pool_index)
    summary = {k: v for k, v in manifest.items() if k != "files"}
    summary["file_count"] = len(manifest["files"])
    print(json.dumps(summary), flush=True)
    if args.dry_run:
        return
    out.mkdir(parents=True, exist_ok=True)
    parts, current, size = [], [], 0

    def flush():
        if not current:
            return
        name = f"trainval_part_{len(parts) + 1:03d}.zip"
        archive = out / name
        with zipfile.ZipFile(archive, "w", zipfile.ZIP_STORED, allowZip64=True) as z:
            for item in current:
                p = safe_path(root, item["path"])
                if p.stat().st_size != item["size_bytes"]:
                    raise Gate(f"source changed during pack: {p.name}")
                z.write(p, "data/" + item["path"])
        if archive.stat().st_size > args.part_bytes:
            raise Gate("ZIP overhead exceeds part size")
        with zipfile.ZipFile(archive) as z:
            bad = z.testzip()
            if bad:
                raise Gate(f"CRC failed: {bad}")
        part = {
            "name": name,
            "size_bytes": archive.stat().st_size,
            "sha256": digest(archive),
            "file_count": len(current),
        }
        parts.append(part)
        print(json.dumps(part), flush=True)

    for item in manifest["files"]:
        # Conservative per-entry overhead plus end record/Zip64 margin.
        entry = item["size_bytes"] + 2 * len(("data/" + item["path"]).encode()) + 512
        if entry + 1024 > args.part_bytes:
            raise Gate(f"single file exceeds part limit: {item['path']}")
        if current and size + entry + 1024 > args.part_bytes:
            flush()
            current, size = [], 0
        current.append(item)
        size += entry
    flush()
    manifest["parts"] = parts
    manifest["code"] = code_archive(out)
    (out / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    print(
        json.dumps(
            {
                "status": "ready",
                "parts": len(parts),
                "out": str(out),
                "train_frames": manifest["train_frames"],
                "source_bytes": manifest["source_bytes"],
            }
        ),
        flush=True,
    )


def verify(root, manifest):
    if manifest.get("format") != "vcf-trainval-full-v1" or manifest.get("sweeps") != 10:
        raise Gate("invalid manifest format/sweeps")
    check_scenes(manifest["train_scenes"], manifest["eval_scenes"], manifest["excluded_T_scenes"])
    expected = {item["path"]: item["size_bytes"] for item in manifest["files"]}
    if len(expected) != len(manifest["files"]):
        raise Gate("duplicate file path")
    for relative, size in expected.items():
        f = safe_path(root, relative)
        if not f.is_file() or f.stat().st_size != size:
            raise Gate(f"missing/wrong-size packed file: {relative}")
    required, frames = coverage(
        root, manifest["train_scenes"], manifest["eval_scenes"], manifest["excluded_T_scenes"]
    )
    if not required <= set(expected):
        raise Gate("manifest omits required LiDAR dependencies")
    if sum(len(frames[n]) for n in manifest["train_scenes"]) != manifest["train_frames"]:
        raise Gate("train frame count mismatch")
    if sum(len(frames[n]) for n in manifest["eval_scenes"]) != manifest["eval_frames"]:
        raise Gate("eval frame count mismatch")
    return frames


def make_index(args):
    import pandas as pd

    m = read_json(args.manifest)
    frames = verify(args.data_root, m)
    rows = []
    for key, split, source in (
        ("train_scenes", "S", "official_train"),
        ("eval_scenes", "T", "heldout_val"),
    ):
        for name in m[key]:
            rows.extend(
                {
                    "sample_token": t,
                    "scene_name": name,
                    "split": split,
                    "lidar_path": p,
                    "source": source,
                }
                for t, p in frames[name]
            )
    frame = pd.DataFrame(rows).sort_values("sample_token").reset_index(drop=True)
    args.exp.mkdir(parents=True, exist_ok=True)
    target = args.exp / "index.parquet"
    if target.exists() and not frame.equals(pd.read_parquet(target)):
        raise Gate("existing run index differs; use new run directory")
    frame.to_parquet(target, index=False)
    (args.exp / "dataset_manifest_sha256.txt").write_text(digest(args.manifest) + "\n")
    print(
        json.dumps(
            {
                "train_frames": int((frame.split == "S").sum()),
                "eval_frames": int((frame.split == "T").sum()),
                "index_sha256": digest(target),
            }
        )
    )


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__)
    sub = ap.add_subparsers(dest="command", required=True)
    p = sub.add_parser("pack")
    p.add_argument("--data-root", type=Path, required=True)
    p.add_argument("--pool-index", type=Path, required=True)
    p.add_argument("--out", type=Path, required=True)
    p.add_argument("--part-bytes", type=int, default=2_000_000_000)
    p.add_argument("--dry-run", action="store_true")
    for name in ("index", "verify"):
        p = sub.add_parser(name)
        p.add_argument("--data-root", type=Path, required=True)
        p.add_argument("--manifest", type=Path, required=True)
        if name == "index":
            p.add_argument("--exp", type=Path, required=True)
    args = ap.parse_args(argv)
    try:
        if args.command == "pack":
            pack(args)
        elif args.command == "index":
            make_index(args)
        else:
            m = read_json(args.manifest)
            verify(args.data_root, m)
            print(json.dumps({"status": "verified", "train_frames": m["train_frames"]}))
        return 0
    except Gate as exc:
        print(f"GATE: {exc}", file=sys.stderr)
        return 3
    except (FileNotFoundError, KeyError) as exc:
        print(f"INPUT: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
