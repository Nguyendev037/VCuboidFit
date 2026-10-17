"""Đóng gói job + data-root + final_config cho notebook giám khảo (hồ sơ 21, OPERATIONS §3 bước 6).

python -I model/scripts/pack_judge_job.py --dataset nuscenes-pilot --job F:/vcf_ext/nusc_pilot/job \
    --root F:/vcf_ext/nusc_pilot/root --final-config <final_config.json> --repo-sha 94be150 \
    --out F:/vcf_pack/judge_bench/nuscenes-pilot

Một ZIP (STORED, không nén lại ảnh/LiDAR) với bố cục giải nén vào JOB_DIR trên Colab:
`<nội dung job>/`, `data_root/`, `final_config.json`. ZIP được cắt theo byte thành `pack_part_NNN.bin`
(≤ --part-gb) để upload Drive; `c4.bench.colab.assemble_pack` nối lại theo `manifest.json["parts"]`.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import zipfile
from datetime import datetime, timezone
from pathlib import Path


def _files(base: Path):
    for dirpath, _, names in os.walk(base):
        for n in sorted(names):
            yield Path(dirpath) / n


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dataset", required=True)
    ap.add_argument("--job", type=Path, required=True)
    ap.add_argument("--root", type=Path, required=True)
    ap.add_argument("--final-config", type=Path, required=True)
    ap.add_argument("--repo-sha", required=True)
    ap.add_argument("--out", type=Path, required=True)
    ap.add_argument("--part-gb", type=float, default=1.9)
    args = ap.parse_args()

    args.out.mkdir(parents=True, exist_ok=True)
    tmp = args.out / "_pack.zip"
    n_files = 0
    with zipfile.ZipFile(tmp, "w", zipfile.ZIP_STORED, allowZip64=True) as zf:
        for f in _files(args.job):
            zf.write(f, f.relative_to(args.job).as_posix())
            n_files += 1
        for f in _files(args.root):
            zf.write(f, "data_root/" + f.relative_to(args.root).as_posix())
            n_files += 1
        zf.write(args.final_config, "final_config.json")
        n_files += 1

    part_bytes = int(args.part_gb * 1e9)
    whole = hashlib.sha256()
    parts, part_sha = [], {}
    with tmp.open("rb") as fin:
        i = 0
        while chunk := fin.read(part_bytes):
            i += 1
            name = f"pack_part_{i:03d}.bin"
            (args.out / name).write_bytes(chunk)
            whole.update(chunk)
            parts.append(name)
            part_sha[name] = hashlib.sha256(chunk).hexdigest()
    total = tmp.stat().st_size
    tmp.unlink()

    bench = args.job / "bench"
    read = lambda p: p.read_text(encoding="utf-8").strip() if p.is_file() else None  # noqa: E731
    manifest = {
        "format": "vcf-judge-pack-v1", "dataset": args.dataset, "repo_sha": args.repo_sha,
        "code_zip": f"code_{args.repo_sha}.zip", "parts": parts, "part_sha256": part_sha,
        "sha256": whole.hexdigest(), "bytes": total, "files": n_files,
        "prereg_sha256": read(bench / "prereg_sha256.txt"), "split_sha256": read(bench / "split_sha256.txt"),
        "final_config_sha256": hashlib.sha256(args.final_config.read_bytes()).hexdigest(),
        "created_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
    }
    (args.out / "manifest.json").write_text(json.dumps(manifest, indent=1), encoding="utf-8")
    print(json.dumps({k: manifest[k] for k in ("dataset", "parts", "sha256", "bytes", "files")}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
