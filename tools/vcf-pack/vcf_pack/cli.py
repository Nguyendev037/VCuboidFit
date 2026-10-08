"""vcf-pack: chia một thư mục nuScenes thành các part zip <= part-size (mặc định 50 MB).

Mỗi arcname bắt đầu bằng ``data/`` để web upload ghép lại thành ``data/v1.0-*/`` và
``data/samples/CAM_*/`` đúng cấu trúc worker đọc. Part 1 luôn chứa metadata.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
import zipfile
from collections.abc import Callable, Iterable
from datetime import datetime, timezone
from pathlib import Path

TOOL = "vcf-pack 0.1"
META_GROUP = "__meta__"
# Ước lượng chi phí header zip cho mỗi entry (local header + central directory + slack).
ZIP_ENTRY_OVERHEAD = 200
_UNITS = {"B": 1, "KB": 1024, "MB": 1024**2, "GB": 1024**3}
_TABLES_BY_SAMPLE = ("sample_data", "sample_annotation")


def parse_size(text: str) -> int:
    m = re.fullmatch(r"\s*(\d+)\s*(B|KB|MB|GB)?\s*", text, re.I)
    if not m:
        raise ValueError(f"Kích thước không hợp lệ: {text!r} (ví dụ 50MB, 200KB)")
    return int(m.group(1)) * _UNITS[(m.group(2) or "B").upper()]


def _default_group(rel: str) -> str:
    return META_GROUP if rel.split("/", 1)[0].startswith("v1.0-") else rel


def plan_parts(files: list[tuple[str, int]], part_size: int,
               group_of: Callable[[str], str] | None = None) -> list[list[str]]:
    """Xếp file (đã theo thứ tự mong muốn, metadata trước) vào các part.

    File liên tiếp cùng ``group_of`` là một nhóm (một sample token) và không bị tách giữa
    hai part; nhóm không vừa phần còn lại thì mở part mới. Nhóm lớn hơn ``part_size`` được
    xé theo từng file, file lớn hơn ``part_size`` chiếm một part riêng.
    """
    group_of = group_of or _default_group
    groups: list[tuple[list[str], int]] = []
    last_key = None
    for rel, size in files:
        key = group_of(rel)
        if groups and key == last_key:
            groups[-1][0].append(rel)
            groups[-1] = (groups[-1][0], groups[-1][1] + size)
        else:
            groups.append(([rel], size))
            last_key = key
    flat: list[tuple[list[str], int]] = []
    for names, total in groups:
        if total > part_size and len(names) > 1:
            sizes = dict(files)
            flat.extend(([n], sizes[n]) for n in names)
        else:
            flat.append((names, total))

    parts: list[list[str]] = []
    cur: list[str] = []
    used = 0
    for names, total in flat:
        if total > part_size:  # một file duy nhất quá lớn: part riêng
            if cur:
                parts.append(cur)
                cur, used = [], 0
            parts.append(list(names))
            continue
        if cur and used + total > part_size:
            parts.append(cur)
            cur, used = [], 0
        cur.extend(names)
        used += total
    if cur:
        parts.append(cur)
    return parts


def write_parts(root: Path, parts: list[list[str]], out: Path,
                overrides: dict[str, bytes] | None = None) -> list[Path]:
    """Ghi ``vcf_part_NNN.zip``; ``overrides`` thay nội dung file theo relpath (metadata đã lọc)."""
    root, out = Path(root), Path(out)
    overrides = overrides or {}
    out.mkdir(parents=True, exist_ok=True)
    written: list[Path] = []
    for i, rels in enumerate(parts, start=1):
        path = out / f"vcf_part_{i:03d}.zip"
        with zipfile.ZipFile(path, "w") as zf:
            for rel in rels:
                method = zipfile.ZIP_DEFLATED if rel.lower().endswith(".json") else zipfile.ZIP_STORED
                arc = f"data/{rel}"
                if rel in overrides:
                    zf.writestr(arc, overrides[rel], compress_type=method)
                else:
                    zf.write(root / rel, arc, compress_type=method)
        written.append(path)
    return written


def _sha256(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for block in iter(lambda: f.read(1 << 20), b""):
            h.update(block)
    return h.hexdigest()


def _walk(root: Path, sub: str) -> list[str]:
    base = root / sub
    if not base.is_dir():
        return []
    return sorted(p.relative_to(root).as_posix() for p in base.rglob("*") if p.is_file())


def _load(tdir: Path, name: str) -> list:
    return json.loads((tdir / f"{name}.json").read_text(encoding="utf-8"))


def _dump(rows: list) -> bytes:
    return json.dumps(rows, ensure_ascii=False, separators=(",", ":")).encode("utf-8")


def _filter_tables(tdir: Path, scenes: list, samples: list) -> tuple[dict[str, bytes], set[str]]:
    """Lọc bảng theo scene giữ lại. Trả về (overrides theo relpath, tập sample_token giữ)."""
    version = tdir.name
    scene_tokens = {s["token"] for s in scenes}
    kept_samples = [s for s in samples if s["scene_token"] in scene_tokens]
    tokens = {s["token"] for s in kept_samples}
    sds = [r for r in _load(tdir, "sample_data") if r["sample_token"] in tokens]
    out = {
        f"{version}/scene.json": _dump(scenes),
        f"{version}/sample.json": _dump(kept_samples),
        f"{version}/sample_data.json": _dump(sds),
    }
    egos = {r["ego_pose_token"] for r in sds}
    out[f"{version}/ego_pose.json"] = _dump([e for e in _load(tdir, "ego_pose") if e["token"] in egos])
    if (tdir / "sample_annotation.json").exists():
        anns = [a for a in _load(tdir, "sample_annotation") if a["sample_token"] in tokens]
        out[f"{version}/sample_annotation.json"] = _dump(anns)
        if (tdir / "instance.json").exists():
            inst = {a["instance_token"] for a in anns}
            out[f"{version}/instance.json"] = _dump(
                [i for i in _load(tdir, "instance") if i["token"] in inst])
    return out, tokens


def _build_plan(root: Path, version: str, n_scenes: int | None, sweeps: bool, maps: bool):
    tdir = root / version
    scenes = _load(tdir, "scene")
    samples = _load(tdir, "sample")
    overrides: dict[str, bytes] = {}
    if n_scenes is not None and n_scenes < len(scenes):
        scenes = scenes[:n_scenes]
        overrides, tokens = _filter_tables(tdir, scenes, samples)
        samples = [s for s in samples if s["token"] in tokens]
    scene_order = {s["token"]: i for i, s in enumerate(scenes)}
    samples = sorted((s for s in samples if s["scene_token"] in scene_order),
                     key=lambda s: (scene_order[s["scene_token"]], s["timestamp"], s["token"]))
    filtered = bool(overrides)

    meta = sorted(p.relative_to(root).as_posix() for p in tdir.glob("*.json"))
    media = _walk(root, "samples") + (_walk(root, "sweeps") if sweeps else [])
    media_set = set(media)
    rows = overrides.get(f"{version}/sample_data.json")
    sds = json.loads(rows) if rows is not None else _load(tdir, "sample_data")
    by_sample: dict[str, list[str]] = {}
    for r in sds:
        if r["filename"] in media_set:
            by_sample.setdefault(r["sample_token"], []).append(r["filename"])

    ordered: list[tuple[str, str]] = [(rel, META_GROUP) for rel in meta]
    seen = set()
    for s in samples:
        for rel in sorted(by_sample.get(s["token"], [])):
            ordered.append((rel, s["token"]))
            seen.add(rel)
    extras = [] if filtered else [rel for rel in media if rel not in seen]
    extras += _walk(root, "maps") if maps else []
    ordered += [(rel, rel) for rel in sorted(set(extras))]
    return ordered, overrides, len(scenes), len(samples)


def main(argv: Iterable[str] | None = None) -> int:
    for stream in (sys.stdout, sys.stderr):  # console Windows cp1252 không in được tiếng Việt
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(errors="replace")
    ap = argparse.ArgumentParser(prog="vcf-pack", description=__doc__.splitlines()[0])
    ap.add_argument("nuscenes_root", help="thư mục chứa v1.0-*/ và samples/")
    ap.add_argument("--out", required=True, help="thư mục ghi vcf_part_*.zip + vcf_manifest.json")
    ap.add_argument("--part-size", default="50MB")
    ap.add_argument("--version", default="v1.0-mini")
    ap.add_argument("--scenes", type=int, default=None, help="chỉ giữ N scene đầu")
    ap.add_argument("--include-sweeps", action="store_true")
    ap.add_argument("--include-maps", action="store_true")
    args = ap.parse_args(None if argv is None else list(argv))

    root, out = Path(args.nuscenes_root), Path(args.out)
    part_size = parse_size(args.part_size)
    required = [root / args.version / n for n in ("scene.json", "sample.json", "sample_data.json")]
    missing = [str(p) for p in required if not p.is_file()]
    if missing or not (root / "samples").is_dir():
        print("Thiếu file đầu vào: " + (", ".join(missing) or str(root / "samples")), file=sys.stderr)
        return 4

    ordered, overrides, n_scenes, n_frames = _build_plan(
        root, args.version, args.scenes, args.include_sweeps, args.include_maps)
    group = dict(ordered)
    sized = []
    for rel, _ in ordered:
        size = len(overrides[rel]) if rel in overrides else (root / rel).stat().st_size
        sized.append((rel, size + ZIP_ENTRY_OVERHEAD + 2 * len(rel)))
    parts = plan_parts(sized, part_size, group_of=lambda rel: group[rel])

    out.mkdir(parents=True, exist_ok=True)
    for old in out.glob("vcf_part_*.zip"):  # phần cũ của lần chạy trước làm người dùng chọn nhầm
        old.unlink()
    zips = write_parts(root, parts, out, overrides=overrides)
    manifest = {
        "version": args.version,
        "parts": [{"name": z.name, "size": z.stat().st_size, "sha256": _sha256(z)} for z in zips],
        "frames": n_frames,
        "scenes": n_scenes,
        "createdAt": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "tool": TOOL,
    }
    (out / "vcf_manifest.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    total = sum(p["size"] for p in manifest["parts"])
    print(f"{len(zips)} part, {n_scenes} scene, {n_frames} frame, {total / 1024**2:.1f} MB -> {out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
