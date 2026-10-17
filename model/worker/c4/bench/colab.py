"""Helper cho notebook Colab: đo thời gian, VRAM, marker, ghi timing.jsonl.

Được gọi từ notebook vcf_judge_bench_colab.ipynb.
Logic dài > 30 dòng được chuyển vào đây để giữ notebook ngắn.
"""
from __future__ import annotations

import json
import subprocess
import sys
import time
from pathlib import Path
from typing import Optional


# ── Ghi timing ───────────────────────────────────────────────────────────────

def append_timing(
    drive_root: str,
    step: str,
    elapsed_s: float,
    vram_mb: Optional[float] = None,
    status: str = "ok",
) -> None:
    """Ghi một bản ghi vào timing.jsonl trên Drive, kể cả khi bước lỗi."""
    timing_path = Path(drive_root) / "timing.jsonl"
    record = {
        "step": step,
        "elapsed_s": round(elapsed_s, 2),
        "vram_peak_mb": vram_mb,
        "status": status,
        "ts": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
    }
    try:
        with timing_path.open("a", encoding="utf-8") as f:
            f.write(json.dumps(record, ensure_ascii=False) + "\n")
    except Exception:  # noqa: BLE001
        pass  # không dừng vì lỗi ghi log


def get_vram_mb() -> Optional[float]:
    """Trả về VRAM peak đã dùng (MB) hoặc None nếu không có GPU / torch chưa load."""
    try:
        import torch
        if torch.cuda.is_available():
            return torch.cuda.max_memory_allocated() / 1024 ** 2
    except ImportError:
        pass
    return None


# ── Chạy CLI bench_judge, raise khi exit ≠ 0 ─────────────────────────────────

def run_bench_judge(
    *args: str,
    drive_root: str,
    step: str,
    cwd: Optional[str] = None,
) -> dict:
    """Chạy `python -m c4.cli.bench_judge <args>`.

    - Ghi timing.jsonl (kể cả khi lỗi).
    - In dòng JSON tóm tắt từ stdout.
    - Khi exit ≠ 0: in mã lỗi + dòng JSON rồi raise RuntimeError.
    """
    t0 = time.perf_counter()
    cmd = [sys.executable, "-m", "c4.cli.bench_judge", *args]
    result = subprocess.run(
        cmd,
        capture_output=True,
        text=True,
        encoding="utf-8",
        cwd=cwd,
    )
    elapsed = time.perf_counter() - t0
    vram = get_vram_mb()

    # Tìm dòng JSON tóm tắt (dòng cuối có thể parse được)
    summary: dict = {}
    for line in result.stdout.strip().splitlines():
        try:
            summary = json.loads(line)
        except json.JSONDecodeError:
            pass

    print(result.stdout)
    if result.stderr:
        print(result.stderr, file=sys.stderr)
    print(json.dumps(summary, ensure_ascii=False))

    status = "ok" if result.returncode == 0 else f"exit_{result.returncode}"
    append_timing(drive_root, step, elapsed, vram, status)

    if result.returncode != 0:
        raise RuntimeError(
            f"bench_judge {' '.join(args)!r} thoát với mã {result.returncode}.\n"
            f"Tóm tắt: {json.dumps(summary, ensure_ascii=False)}"
        )
    return summary


# ── Kiểm GPU ─────────────────────────────────────────────────────────────────

def check_gpu(warn_non_a100: bool = True) -> str:
    """Kiểm GPU; cảnh báo vàng nếu không phải A100 nhưng vẫn tiếp tục.

    Trả về tên GPU (hoặc 'CPU').
    """
    try:
        import torch
        if not torch.cuda.is_available():
            print("⚠️ \033[33mKhông tìm thấy GPU — chạy trên CPU, Pha 4 sẽ rất chậm.\033[0m")
            return "CPU"
        name = torch.cuda.get_device_name(0)
        if warn_non_a100 and "A100" not in name:
            print(f"⚠️ \033[33mGPU = {name} — không phải A100. "
                  "Benchmark có thể chậm hơn ước lượng.\033[0m")
        else:
            print(f"✅ GPU: {name}")
        return name
    except ImportError:
        print("⚠️ \033[33mtorch chưa cài — kiểm GPU bỏ qua.\033[0m")
        return "unknown"


# ── Ghép gói dữ liệu từ manifest ─────────────────────────────────────────────

def assemble_pack(
    manifest_path: str,
    pack_dir: str,
    out_dir: str,
    expected_sha: Optional[str] = None,
) -> None:
    """Ghép các part theo manifest + kiểm SHA256.

    manifest_path: đường tới file manifest (JSON hoặc text 1 dòng/file).
    pack_dir: thư mục chứa các part trên Drive.
    out_dir: thư mục đích giải nén.
    expected_sha: nếu có, kiểm SHA256 của file đã ghép.
    """
    import hashlib
    import zipfile

    manifest = Path(manifest_path)
    if not manifest.is_file():
        raise FileNotFoundError(f"Manifest không tìm thấy: {manifest_path}")

    parts_def = json.loads(manifest.read_text(encoding="utf-8"))
    target = Path(out_dir)
    target.mkdir(parents=True, exist_ok=True)

    # Ghép các phần thành file zip tạm
    tmp_zip = target / "_assembled.zip"
    sha = hashlib.sha256()
    with tmp_zip.open("wb") as fout:
        for part_name in parts_def.get("parts", []):
            part_path = Path(pack_dir) / part_name
            if not part_path.is_file():
                raise FileNotFoundError(f"Part không tìm thấy: {part_path}")
            data = part_path.read_bytes()
            sha.update(data)
            fout.write(data)

    # Kiểm SHA
    actual = sha.hexdigest()
    if expected_sha and actual != expected_sha:
        tmp_zip.unlink(missing_ok=True)
        raise ValueError(
            f"SHA256 gói không khớp!\n  Kỳ vọng: {expected_sha}\n  Thực tế: {actual}"
        )
    print(f"✅ SHA256 gói: {actual}")

    # Giải nén
    with zipfile.ZipFile(tmp_zip) as zf:
        zf.extractall(target)
    tmp_zip.unlink(missing_ok=True)
    print(f"✅ Đã giải nén vào {target}")


# ── Bảng trạng thái cổng (ô 4) ───────────────────────────────────────────────

def print_gate_status(job_dir: str, expected_prereg: str) -> None:
    """In bảng trạng thái cổng xanh/đỏ cho ô 4 notebook.

    Kiểm: prereg sha, bench_split, selections, CAL, POOL, EVAL markers.
    """
    from c4.bench.gate import BenchGateError, sha256, require

    job = Path(job_dir)
    bench = job / "bench"

    def _check(label: str, ok: bool, detail: str = "") -> None:
        icon = "✅" if ok else "❌"
        msg = f"{icon} {label}"
        if detail:
            msg += f": {detail}"
        print(msg)

    # Prereg
    prereg_file = bench / "prereg.txt"
    if prereg_file.is_file():
        actual_sha = sha256(prereg_file)
        _check("Prereg SHA khớp", actual_sha == expected_prereg,
               actual_sha[:16] + "…")
    else:
        _check("Prereg SHA khớp", False, "prereg.txt không có")

    # Split
    _check("bench_split.parquet", (bench / "bench_split.parquet").is_file())

    # Selections
    _check("selections.json", (bench / "selections.json").is_file())

    # Judge CAL
    _check("judge_calib.json", (bench / "judge" / "judge_calib.json").is_file())

    # Markers
    _check("POOL đã mở", (bench / "pool_opened.json").is_file())
    _check("EVAL đã mở", (bench / "eval_opened.json").is_file())


# ── Đóng gói bundle ───────────────────────────────────────────────────────────

def pack_results_bundle(
    job_dir: str,
    drive_root: str,
    dataset: str,
) -> Path:
    """Đóng gói results_bundle.zip (bench/ trừ ảnh gốc) lên Drive.

    Trả về Path tới file zip đã ghi.
    """
    import hashlib
    import zipfile

    import pandas as pd

    job = Path(job_dir)
    bench = job / "bench"
    bundle_path = Path(drive_root) / f"results_bundle_{dataset}.zip"

    # Bảng khung POOL (sample_token → scene_token) cho notebook thẩm định tính lại bootstrap
    index = pd.read_parquet(job / "lidar" / "index.parquet", columns=["sample_token", "scene_token", "split"])
    index.loc[index.split == "T", ["sample_token", "scene_token"]].drop_duplicates().to_parquet(
        bench / "pool_frames.parquet", index=False)

    # Loại ảnh gốc (media/) và trọng số Pha 4 (*.pt) — bundle chỉ chứa bảng/số đo/crop
    include = sorted(f for f in bench.rglob("*") if f.is_file()
                     and "media" not in f.relative_to(job).parts and f.suffix != ".pt")
    sums = "".join(f"{hashlib.sha256(f.read_bytes()).hexdigest()}  {f.relative_to(job).as_posix()}\n"
                   for f in include)
    with zipfile.ZipFile(bundle_path, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        for f in include:
            zf.writestr(f.relative_to(job).as_posix(), f.read_bytes())
        zf.writestr("SHA256SUMS", sums)

    digest = hashlib.sha256(bundle_path.read_bytes()).hexdigest()
    print(json.dumps({
        "bundle": str(bundle_path),
        "sha256": digest,
        "n_files": len(include),
    }, ensure_ascii=False))
    return bundle_path
