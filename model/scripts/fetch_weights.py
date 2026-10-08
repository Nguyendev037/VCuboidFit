"""Tải trọng số một lần vào C4_WEIGHTS_DIR (mặc định workspace/weights); job chạy không cần mạng.

    python scripts/fetch_weights.py --dir workspace/weights
"""
import argparse
import http.client
import os
import time
import urllib.error
import urllib.request
from pathlib import Path

ULTRALYTICS_URL = "https://github.com/ultralytics/assets/releases/download/v8.3.0/{name}"
YOLO_WEIGHTS = ["yolo11m.pt", "yolo11s.pt"]
DINO_MODELS = ["dinov2_vitb14", "dinov2_vits14"]
CLIP_MODEL, CLIP_PRETRAINED = "ViT-B-16", "openai"


def download(url: str, target: Path, retries: int = 6, backoff: float = 5.0) -> None:
    """Tải vào <target>.part, tiếp tục bằng Range sau khi đứt; chỉ đổi tên khi đủ byte."""
    part = target.with_name(target.name + ".part")
    last = None
    for attempt in range(1, retries + 1):
        have = part.stat().st_size if part.exists() else 0
        req = urllib.request.Request(url, headers={"Range": f"bytes={have}-"} if have else {})
        try:
            with urllib.request.urlopen(req, timeout=60) as r:
                resumed = r.status == 206
                total = int(r.headers["Content-Length"]) + (have if resumed else 0)
                with open(part, "ab" if resumed else "wb") as f:
                    while chunk := r.read(1 << 20):
                        f.write(chunk)
            if part.stat().st_size == total:
                os.replace(part, target)
                return
            last = f"got {part.stat().st_size} of {total} bytes"
        except urllib.error.HTTPError as e:
            if e.code == 416:  # .part không khớp server: bỏ làm lại
                part.unlink(missing_ok=True)
            last = str(e)
        except (OSError, urllib.error.URLError, http.client.HTTPException) as e:
            last = str(e)
        print(f"attempt {attempt}/{retries} failed for {url}: {last}")
        if attempt < retries:
            time.sleep(min(60.0, backoff * attempt))  # DNS/mạng chập chờn: nghỉ rồi thử lại
    raise RuntimeError(f"download failed after {retries} attempts: {url} ({last})")


def fetch_yolo(dest: Path) -> None:
    for name in YOLO_WEIGHTS:
        target = dest / name
        if target.exists() and target.stat().st_size > 0:
            print(f"skip {name} (exists)")
            continue
        print(f"download {name}")
        download(ULTRALYTICS_URL.format(name=name), target)


def fetch_dino(dest: Path) -> None:
    import torch

    torch.hub.set_dir(str(dest / "torch_hub"))
    for name in DINO_MODELS:
        print(f"download {name}")
        torch.hub.load("facebookresearch/dinov2", name, pretrained=True, trust_repo=True)


def fetch_clip(dest: Path) -> None:
    import open_clip

    print(f"download OpenCLIP {CLIP_MODEL}/{CLIP_PRETRAINED}")
    open_clip.create_model_and_transforms(CLIP_MODEL, pretrained=CLIP_PRETRAINED,
                                          cache_dir=str(dest / "open_clip"))


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="Fetch model weights once into the weights dir.")
    ap.add_argument("--dir", default=os.environ.get("C4_WEIGHTS_DIR", "workspace/weights"),
                    help="target directory (default: $C4_WEIGHTS_DIR or workspace/weights)")
    args = ap.parse_args(argv)
    dest = Path(args.dir)
    dest.mkdir(parents=True, exist_ok=True)
    fetch_yolo(dest)
    fetch_dino(dest)
    fetch_clip(dest)
    print(f"done -> {dest}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
