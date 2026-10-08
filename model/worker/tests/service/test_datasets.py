import hashlib
import json
import shutil
import zipfile
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from service.archives import DatasetError, extract, find_data_dirs, group_archives, merge_into
from service.datasets import check_manifest, validate_dataset
from service.main import create_app
from service.settings import Settings
from tests.fixtures.make_nuscenes import make_nuscenes

NO_7Z = "__khong_co_7z__"


def zip_dir(src: Path, out: Path, arc_prefix="", only=None):
    """Nén `src` (một thư mục data/) vào zip; `only(rel)` lọc file."""
    with zipfile.ZipFile(out, "w", zipfile.ZIP_STORED) as z:
        for p in sorted(src.rglob("*")):
            if p.is_file():
                rel = p.relative_to(src.parent).as_posix()
                if only is None or only(rel):
                    z.write(p, arc_prefix + rel)
    return out


def sha(p: Path) -> str:
    return hashlib.sha256(p.read_bytes()).hexdigest()


def write_manifest(upload: Path, parts: list[Path], version="v1.0-mini", extra_missing=()):
    entries = [dict(name=p.name, size=p.stat().st_size, sha256=sha(p)) for p in parts]
    entries += [dict(name=n, size=1, sha256="0" * 64) for n in extra_missing]
    (upload / "vcf_manifest.json").write_text(
        json.dumps(dict(version=version, parts=entries, frames=12, scenes=2)), encoding="utf-8")


@pytest.fixture
def settings(tmp_path):
    return Settings(workspace=tmp_path / "ws", sevenzip=NO_7Z)


@pytest.fixture
def client(settings):
    return TestClient(create_app(settings))


def make_upload(settings, name="u1"):
    up = settings.uploads / name
    up.mkdir(parents=True)
    return up


# ---------- extract / group / find / merge ----------

def test_group_archives_first_volume_only(tmp_path):
    names = ["a.zip", "b.part1.rar", "b.part2.rar", "c.7z.001", "c.7z.002", "d.zip.001",
             "d.zip.002", "vcf_manifest.json", "notes.txt"]
    files = [tmp_path / n for n in names]
    got = sorted(p.name for p in group_archives(files))
    assert got == ["a.zip", "b.part1.rar", "c.7z.001", "d.zip.001"]


def test_extract_zip_without_7z_and_zip_slip(tmp_path):
    bad = tmp_path / "evil.zip"
    with zipfile.ZipFile(bad, "w") as z:
        z.writestr("data/ok.txt", "x")
        z.writestr("../evil.txt", "boom")
    dest = tmp_path / "out" / "raw"
    with pytest.raises(DatasetError, match="evil.txt"):
        extract(bad, dest, NO_7Z)
    assert not (tmp_path / "out" / "evil.txt").exists()
    assert not (dest / "data" / "ok.txt").exists()  # kiểm toàn bộ trước khi ghi


def test_rar_without_7z_gives_vietnamese_error(tmp_path):
    rar = tmp_path / "x.rar"
    rar.write_bytes(b"Rar!")
    with pytest.raises(DatasetError, match="7-Zip"):
        extract(rar, tmp_path / "o", NO_7Z)


@pytest.mark.skipif(shutil.which("7z") is None, reason="cần 7-Zip")
def test_7z_archive_extracts_with_7z(tmp_path):
    import subprocess
    src = tmp_path / "src" / "data"
    (src / "samples").mkdir(parents=True)
    (src / "samples" / "a.txt").write_text("x")
    arc = tmp_path / "d.7z"
    subprocess.run([shutil.which("7z"), "a", str(arc), str(src)], check=True, capture_output=True)
    extract(arc, tmp_path / "out", "7z")
    assert (tmp_path / "out" / "data" / "samples" / "a.txt").read_text() == "x"


def test_find_data_dirs_depth_and_content(tmp_path):
    (tmp_path / "data" / "samples").mkdir(parents=True)
    (tmp_path / "Wrap" / "data" / "v1.0-mini").mkdir(parents=True)
    (tmp_path / "other" / "data").mkdir(parents=True)  # rỗng: không tính
    (tmp_path / "a" / "b" / "data" / "samples").mkdir(parents=True)  # sâu 3: không tính
    found = sorted(p.relative_to(tmp_path).as_posix() for p in find_data_dirs(tmp_path))
    assert found == ["Wrap/data", "data"]


def test_merge_into_combines_trees(tmp_path):
    a, b, target = tmp_path / "a", tmp_path / "b", tmp_path / "t"
    (a / "samples" / "CAM_FRONT").mkdir(parents=True)
    (b / "samples" / "CAM_BACK").mkdir(parents=True)
    (a / "samples" / "CAM_FRONT" / "1.jpg").write_bytes(b"1")
    (b / "samples" / "CAM_BACK" / "2.jpg").write_bytes(b"2")
    merge_into([a, b], target)
    assert (target / "samples" / "CAM_FRONT" / "1.jpg").read_bytes() == b"1"
    assert (target / "samples" / "CAM_BACK" / "2.jpg").read_bytes() == b"2"


# ---------- validate_dataset ----------

def test_validate_ok_report(tmp_path):
    root = make_nuscenes(tmp_path)
    r = validate_dataset(root, dataset_id="d1")
    assert r.ok and r.dataset_id == "d1" and r.version == "v1.0-mini"
    assert (r.scenes, r.frames) == (2, 12)
    assert r.images_by_cam["CAM_FRONT"] == 12 and sum(r.images_by_cam.values()) == 72
    assert r.has_lidar and r.has_annotations and r.errors == [] and r.warnings == []


def test_validate_warnings_not_errors_without_lidar_and_annotations(tmp_path):
    root = make_nuscenes(tmp_path, with_lidar=False, with_annotations=False)
    r = validate_dataset(root)
    assert r.ok and not r.has_lidar and not r.has_annotations
    assert len(r.warnings) == 2


def test_validate_missing_table_is_error(tmp_path):
    root = make_nuscenes(tmp_path)
    (root / "v1.0-mini" / "sample.json").unlink()
    r = validate_dataset(root)
    assert not r.ok and any("sample" in e for e in r.errors)


def test_validate_no_camera_images_is_error(tmp_path):
    root = make_nuscenes(tmp_path)
    shutil.rmtree(root / "samples" / "CAM_FRONT")
    for c in ["CAM_FRONT_LEFT", "CAM_FRONT_RIGHT", "CAM_BACK", "CAM_BACK_LEFT", "CAM_BACK_RIGHT"]:
        shutil.rmtree(root / "samples" / c)
    r = validate_dataset(root)
    assert not r.ok and any("camera" in e.lower() for e in r.errors)


# ---------- manifest ----------

def test_manifest_ok_missing_and_tampered(tmp_path):
    up = tmp_path / "up"
    up.mkdir()
    p1 = up / "vcf_part_001.zip"
    p1.write_bytes(b"AAAA")
    write_manifest(up, [p1])
    assert check_manifest(up) == []
    write_manifest(up, [p1], extra_missing=["vcf_part_002.zip"])
    errs = check_manifest(up)
    assert len(errs) == 1 and "vcf_part_002.zip" in errs[0]
    write_manifest(up, [p1])
    p1.write_bytes(b"BBBB")
    errs = check_manifest(up)
    assert len(errs) == 1 and "vcf_part_001.zip" in errs[0] and "SHA-256" in errs[0]


def test_manifest_absent_is_ok(tmp_path):
    assert check_manifest(tmp_path) == []


# ---------- POST /datasets ----------

def test_post_single_zip_ok(client, settings, tmp_path):
    data = make_nuscenes(tmp_path / "src")
    up = make_upload(settings)
    zip_dir(data, up / "all.zip")
    r = client.post("/datasets", json={"uploadId": "u1"})
    assert r.status_code == 200
    rep = r.json()
    assert rep["ok"] and rep["scenes"] == 2 and rep["frames"] == 12
    assert rep["imagesByCam"]["CAM_FRONT"] == 12 and rep["hasLidar"] and rep["hasAnnotations"]
    did = rep["datasetId"]
    assert (settings.datasets / did / "data" / "v1.0-mini" / "scene.json").is_file()
    assert not (settings.datasets / did / "raw").exists()
    assert client.get(f"/datasets/{did}").json()["frames"] == 12


def test_post_zip_with_wrapping_folder(client, settings, tmp_path):
    data = make_nuscenes(tmp_path / "src")
    up = make_upload(settings)
    zip_dir(data, up / "all.zip", arc_prefix="MyData/")
    rep = client.post("/datasets", json={"uploadId": "u1"}).json()
    assert rep["ok"] and rep["frames"] == 12


def test_post_two_parts_with_manifest_merge(client, settings, tmp_path):
    data = make_nuscenes(tmp_path / "src")
    up = make_upload(settings)
    cams_a = ("CAM_FRONT", "CAM_FRONT_LEFT", "CAM_FRONT_RIGHT")
    p1 = zip_dir(data, up / "vcf_part_001.zip",
                 only=lambda r: "/samples/" not in r or any(f"/{c}/" in r for c in cams_a)
                 or "LIDAR" in r)
    p2 = zip_dir(data, up / "vcf_part_002.zip",
                 only=lambda r: "/samples/" in r and not any(f"/{c}/" in r for c in cams_a)
                 and "LIDAR" not in r)
    write_manifest(up, [p1, p2])
    rep = client.post("/datasets", json={"uploadId": "u1"}).json()
    assert rep["ok"], rep["errors"]
    assert rep["imagesByCam"]["CAM_BACK"] == 12 and rep["imagesByCam"]["CAM_FRONT"] == 12


def test_post_manifest_missing_part_names_it(client, settings, tmp_path):
    data = make_nuscenes(tmp_path / "src")
    up = make_upload(settings)
    p1 = zip_dir(data, up / "vcf_part_001.zip")
    write_manifest(up, [p1], extra_missing=["vcf_part_002.zip"])
    rep = client.post("/datasets", json={"uploadId": "u1"}).json()
    assert not rep["ok"] and any("vcf_part_002.zip" in e for e in rep["errors"])


def test_post_tampered_part_checksum_error(client, settings, tmp_path):
    data = make_nuscenes(tmp_path / "src")
    up = make_upload(settings)
    p1 = zip_dir(data, up / "vcf_part_001.zip")
    write_manifest(up, [p1])
    with open(p1, "ab") as f:
        f.write(b"tamper")
    rep = client.post("/datasets", json={"uploadId": "u1"}).json()
    assert not rep["ok"] and any("SHA-256" in e for e in rep["errors"])


def test_post_zip_slip_not_written_and_reported(client, settings, tmp_path):
    up = make_upload(settings)
    with zipfile.ZipFile(up / "evil.zip", "w") as z:
        z.writestr("../evil.txt", "boom")
    rep = client.post("/datasets", json={"uploadId": "u1"}).json()
    assert not rep["ok"] and any("evil.txt" in e for e in rep["errors"])
    assert not (settings.datasets / "evil.txt").exists()
    assert not list(settings.workspace.rglob("evil.txt"))


def test_post_zip_without_data_dir(client, settings):
    up = make_upload(settings)
    with zipfile.ZipFile(up / "x.zip", "w") as z:
        z.writestr("readme.txt", "hi")
    rep = client.post("/datasets", json={"uploadId": "u1"}).json()
    assert not rep["ok"] and any("Không tìm thấy thư mục data/" in e for e in rep["errors"])


def test_post_unknown_upload_and_unknown_dataset(client):
    r = client.post("/datasets", json={"uploadId": "nope"})
    assert r.status_code == 404 and r.json()["error"]["code"] == "not_found"
    assert client.get("/datasets/zzz").status_code == 404


# ---------- GET /datasets/progress/{uploadId} (SPEC-P05) ----------

def test_progress_done_after_create_and_unknown_404(client, settings, tmp_path):
    data = make_nuscenes(tmp_path / "src")
    up = make_upload(settings)
    zip_dir(data, up / "all.zip")
    assert client.post("/datasets", json={"uploadId": "u1"}).json()["ok"]
    assert json.loads((up / "progress.json").read_text(encoding="utf-8"))["phase"] == "done"
    r = client.get("/datasets/progress/u1")
    assert r.status_code == 200
    assert r.json()["phase"] == "done" and r.json()["uploadId"] == "u1"
    bad = client.get("/datasets/progress/khong-co")
    assert bad.status_code == 404 and bad.json()["error"]["code"] == "not_found"
