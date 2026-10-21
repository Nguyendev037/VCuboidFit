"""Stage camera tuỳ chọn: OpenCV + OpenCLIP, ngưỡng in-sample và crops cho rare_v24."""
import argparse
import subprocess
import sys
from pathlib import Path

from c4.jobs.runner import _atomic_json


def gpu_available() -> bool:
    try:
        import torch

        return torch.cuda.is_available()
    except (ImportError, OSError):
        return False


def _cli(module: str, job: Path, root: Path, *flags: str) -> None:
    command, flags = ([flags[0]], flags[1:]) if module == "context" else ([], flags)
    subprocess.run([sys.executable, "-m", f"c4.cli.{module}", *command, "--job-dir", str(job),
                    "--data-root", str(root), *flags], check=True)


def _build_crops(job: Path, root: Path, device: str) -> None:
    from c4.rare.pipeline import run_rare_v24
    from c4.rare.semantic import build_crops

    result = run_rare_v24(job, root, profile="lidar_only", pool_split="all", ref_split="all")
    build_crops(job, root, device=device, sid=result["selectionId"])


def _split_manifest(job: Path) -> None:
    from c4.contracts import read_table

    path = job / "split_manifest.csv"
    if not path.is_file():
        frames = read_table(job / "index/frames.parquet", "frames")
        # One row per keyframe, including tokens shared by multiple cameras.
        tokens = frames[["sample_token"]].drop_duplicates().assign(split="V")
        tmp = path.with_name(path.name + ".tmp")
        tokens.to_csv(tmp, index=False)
        tmp.replace(path)


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--job-dir", required=True)
    ap.add_argument("--data-root", required=True)
    ap.add_argument("--profile", default=None)  # accepted for runner.stage_command
    ap.add_argument("--resume", action="store_true")
    ap.add_argument("--device", default="cuda")
    args = ap.parse_args(argv)
    if not gpu_available():
        print("camera: bỏ qua — máy không có GPU/torch", file=sys.stderr)
        return 0
    job, root = Path(args.job_dir), Path(args.data_root)

    def progress(done: int) -> None:
        _atomic_json(dict(done=done, total=7, etaSec=None), job / "progress/camera.json")

    step = 1
    try:
        progress(step)
        step = 2
        if not all((job / p).is_file() for p in ("index/frames.parquet", "index/cam_poses.parquet")):
            _cli("build_index", job, root, "--device", args.device)
        progress(step)
        step = 3
        if not (job / "cache/clip_img.npy").is_file():
            _cli("extract_clip", job, root, "--device", args.device)
        progress(step)
        step = 4
        if not (job / "cache/quality_cv.parquet").is_file():
            _cli("context", job, root, "cv")
        progress(step)
        step = 5
        _split_manifest(job)
        if not (job / "cache/context_thresholds_v1.json").is_file():
            _cli("context", job, root, "fit", "--split", "V")
        progress(step)
        step = 6
        if not (job / "cache/context_frame.parquet").is_file():
            _cli("context", job, root, "run", "--profile", "multisensor")
        progress(step)
        step = 7
        if not (job / "cache/rare_crops.npy").is_file():
            _build_crops(job, root, args.device)
        progress(step)
    except subprocess.CalledProcessError as e:
        hint = " — chạy fetch_weights.py để tải trọng số OpenCLIP" if step == 3 and e.returncode == 4 else ""
        print(f"camera: lỗi bước {step} (mã {e.returncode}){hint}", file=sys.stderr)
        return e.returncode if e.returncode > 0 else 1
    except Exception as e:  # noqa: BLE001 — stage tuỳ chọn, runner giữ job hoàn tất
        print(f"camera: lỗi bước {step}: {type(e).__name__}: {e}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
