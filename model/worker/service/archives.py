"""Giải nén và gộp thư mục data/ từ các archive người dùng tải lên."""
import re
import shutil
import subprocess
import zipfile
from pathlib import Path

MANIFEST = "vcf_manifest.json"


class DatasetError(Exception):
    """Lỗi dữ liệu người dùng; message là tiếng Việt, hiển thị nguyên văn."""


def group_archives(files: list[Path]) -> list[Path]:
    """Chỉ volume đầu của archive nhiều phần; bỏ manifest và file không phải archive."""
    out = []
    for f in files:
        name = f.name.lower()
        if name == MANIFEST:
            continue
        part = re.search(r"\.part(\d+)\.rar$", name)
        vol = re.search(r"\.(?:7z|zip)\.(\d+)$", name)
        if part or vol:
            if int((part or vol).group(1)) == 1:
                out.append(f)
        elif name.endswith((".zip", ".rar", ".7z")):
            out.append(f)
    return out


def _safe_zip_extract(archive: Path, dest: Path) -> None:
    root = dest.resolve()
    with zipfile.ZipFile(archive) as z:
        for info in z.infolist():
            target = (dest / info.filename).resolve()
            if target != root and root not in target.parents:
                raise DatasetError(
                    f"Archive {archive.name} chứa đường dẫn không hợp lệ: {info.filename}")
        dest.mkdir(parents=True, exist_ok=True)
        z.extractall(dest)


def extract(archive: Path, dest: Path, sevenzip: str) -> None:
    """7z x -y -o<dest>; .zip dùng zipfile khi không có 7-Zip."""
    archive, dest = Path(archive), Path(dest)
    exe = shutil.which(sevenzip)
    if exe:
        dest.mkdir(parents=True, exist_ok=True)
        r = subprocess.run([exe, "x", "-y", f"-o{dest}", str(archive)],
                           capture_output=True, text=True, check=False)
        if r.returncode != 0:
            raise DatasetError(f"Không giải nén được {archive.name} (7-Zip mã {r.returncode})")
        return
    if archive.suffix.lower() == ".zip":
        try:
            _safe_zip_extract(archive, dest)
        except zipfile.BadZipFile as e:
            raise DatasetError(f"File {archive.name} không phải zip hợp lệ") from e
        return
    raise DatasetError("Cần cài 7-Zip để giải nén file .rar/.7z")


def find_data_dirs(root: Path) -> list[Path]:
    """Thư mục `data` sâu ≤ 2 chứa v1.0-* hoặc samples."""
    root = Path(root)
    cands = [root / "data", *sorted(p / "data" for p in root.iterdir() if p.is_dir())] \
        if root.is_dir() else []
    return sorted(d for d in cands
                  if d.is_dir() and ((d / "samples").is_dir() or any(d.glob("v1.0-*"))))


def merge_into(srcs: list[Path], target_data: Path) -> None:
    """Gộp các cây data/ vào target_data (di chuyển từng file; trùng tên thì ghi đè)."""
    target_data = Path(target_data)
    target_data.mkdir(parents=True, exist_ok=True)
    for src in srcs:
        for f in sorted(Path(src).rglob("*")):
            if f.is_file():
                dst = target_data / f.relative_to(src)
                dst.parent.mkdir(parents=True, exist_ok=True)
                shutil.move(str(f), str(dst))
