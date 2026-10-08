import hashlib
import json
import subprocess
import sys
import zipfile
from pathlib import Path

import pytest

from vcf_pack.cli import main, parse_size, plan_parts, write_parts

PART = "200KB"
PART_BYTES = 200 * 1024


def _run(root, out, *extra):
    assert main([str(root), "--out", str(out), "--part-size", PART, *extra]) == 0
    manifest = json.loads((Path(out) / "vcf_manifest.json").read_text(encoding="utf-8"))
    return manifest, [Path(out) / p["name"] for p in manifest["parts"]]


def _names(zips):
    return [n for z in zips for n in zipfile.ZipFile(z).namelist()]


def test_parse_size():
    assert parse_size("50MB") == 50 * 1024 * 1024
    assert parse_size("200KB") == 200 * 1024
    assert parse_size("1gb") == 1024**3
    with pytest.raises(ValueError):
        parse_size("abc")


def test_every_part_within_limit_and_several_parts(nus_root, tmp_path):
    manifest, zips = _run(nus_root, tmp_path / "out")
    assert len(zips) >= 3
    for z in zips:
        assert z.stat().st_size <= PART_BYTES, z.name
    assert [p["name"] for p in manifest["parts"]] == [
        f"vcf_part_{i:03d}.zip" for i in range(1, len(zips) + 1)]


def test_part1_has_all_metadata_and_arcnames_start_with_data(nus_root, tmp_path):
    _, zips = _run(nus_root, tmp_path / "out")
    names = _names(zips)
    assert all(n.startswith("data/") for n in names)
    meta_src = sorted(p.name for p in (nus_root / "v1.0-mini").glob("*.json"))
    first = set(zipfile.ZipFile(zips[0]).namelist())
    assert {f"data/v1.0-mini/{n}" for n in meta_src} <= first
    later = {n for z in zips[1:] for n in zipfile.ZipFile(z).namelist()}
    assert not any(n.startswith("data/v1.0-") for n in later)


def test_unzip_reproduces_every_file_byte_for_byte(nus_root, tmp_path):
    _, zips = _run(nus_root, tmp_path / "out")
    dest = tmp_path / "unz"
    for z in zips:
        zipfile.ZipFile(z).extractall(dest)
    src_files = [p for p in nus_root.rglob("*")
                 if p.is_file() and p.relative_to(nus_root).parts[0] != "sweeps"]
    assert src_files
    for p in src_files:
        rel = p.relative_to(nus_root)
        assert (dest / "data" / rel).read_bytes() == p.read_bytes(), rel
    got = [p for p in (dest / "data").rglob("*") if p.is_file()]
    assert len(got) == len(src_files)


def test_sweeps_excluded_by_default_and_included_on_flag(nus_root, tmp_path):
    assert any(p.is_file() for p in (nus_root / "sweeps").rglob("*"))
    _, zips = _run(nus_root, tmp_path / "a")
    assert not any(n.startswith("data/sweeps/") for n in _names(zips))
    _, zips2 = _run(nus_root, tmp_path / "b", "--include-sweeps")
    assert any(n.startswith("data/sweeps/") for n in _names(zips2))


def test_maps_only_with_flag(nus_root, tmp_path):
    (nus_root / "maps").mkdir()
    (nus_root / "maps" / "m.png").write_bytes(b"png-bytes")
    _, zips = _run(nus_root, tmp_path / "a")
    assert not any(n.startswith("data/maps/") for n in _names(zips))
    _, zips2 = _run(nus_root, tmp_path / "b", "--include-maps")
    assert "data/maps/m.png" in _names(zips2)


def test_manifest_matches_parts(nus_root, tmp_path):
    manifest, zips = _run(nus_root, tmp_path / "out")
    assert manifest["tool"] == "vcf-pack 0.1"
    assert manifest["version"] == "v1.0-mini"
    assert manifest["scenes"] == 2 and manifest["frames"] == 12
    assert manifest["createdAt"]
    for entry, z in zip(manifest["parts"], zips):
        assert entry["size"] == z.stat().st_size
        assert entry["sha256"] == hashlib.sha256(z.read_bytes()).hexdigest()


def test_scenes_1_keeps_only_scene0_and_filters_tables(nus_root, tmp_path):
    manifest, zips = _run(nus_root, tmp_path / "out", "--scenes", "1")
    assert manifest["scenes"] == 1 and manifest["frames"] == 6
    names = _names(zips)
    media = [n for n in names if n.startswith("data/samples/")]
    assert media and all("/scene0_" in n for n in media)
    z0 = zipfile.ZipFile(zips[0])

    def table(n):
        return json.loads(z0.read(f"data/v1.0-mini/{n}.json"))

    assert [s["name"] for s in table("scene")] == ["scene0"]
    samples = table("sample")
    assert len(samples) == 6 and {s["scene_token"] for s in samples} == {"sc0"}
    tokens = {s["token"] for s in samples}
    sds = table("sample_data")
    assert sds and {r["sample_token"] for r in sds} <= tokens
    assert {e["token"] for e in table("ego_pose")} == {f"ego_{t}" for t in tokens}
    anns = table("sample_annotation")
    assert anns and {a["sample_token"] for a in anns} <= tokens
    assert {i["token"] for i in table("instance")} == {a["instance_token"] for a in anns}
    assert len(table("sensor")) == 7  # bảng không phụ thuộc scene giữ nguyên


def test_plan_parts_rules():
    files = [("v1.0-mini/a.json", 10), ("v1.0-mini/b.json", 10),
             ("samples/x1.jpg", 40), ("samples/x2.jpg", 40),
             ("samples/y1.jpg", 40), ("samples/y2.jpg", 40),
             ("samples/big.jpg", 500)]
    groups = {"samples/x1.jpg": "x", "samples/x2.jpg": "x",
              "samples/y1.jpg": "y", "samples/y2.jpg": "y", "samples/big.jpg": "big"}

    def group_of(p):
        return groups.get(p, "__meta__")

    parts = plan_parts(files, 200, group_of=group_of)
    # metadata (20) + x (80) + y (80) = 180 <= 200: cùng part 1; file quá lớn nằm riêng
    assert parts[0] == ["v1.0-mini/a.json", "v1.0-mini/b.json", "samples/x1.jpg",
                        "samples/x2.jpg", "samples/y1.jpg", "samples/y2.jpg"]
    assert parts[1] == ["samples/big.jpg"] and len(parts) == 2
    # nhóm không vừa phần còn lại thì mở part mới, không tách nhóm
    parts = plan_parts(files[:6], 150, group_of=group_of)
    assert parts == [["v1.0-mini/a.json", "v1.0-mini/b.json", "samples/x1.jpg", "samples/x2.jpg"],
                     ["samples/y1.jpg", "samples/y2.jpg"]]


def test_write_parts_compression_and_overrides(nus_root, tmp_path):
    rels = ["v1.0-mini/scene.json", "samples/CAM_FRONT/scene0_f0__CAM_FRONT.jpg"]
    out = write_parts(nus_root, [rels], tmp_path / "o",
                      overrides={"v1.0-mini/scene.json": b"[]"})
    zf = zipfile.ZipFile(out[0])
    kinds = {i.filename: i.compress_type for i in zf.infolist()}
    assert kinds["data/v1.0-mini/scene.json"] == zipfile.ZIP_DEFLATED
    assert kinds["data/samples/CAM_FRONT/scene0_f0__CAM_FRONT.jpg"] == zipfile.ZIP_STORED
    assert zf.read("data/v1.0-mini/scene.json") == b"[]"


def test_missing_root_fails_cleanly(tmp_path):
    assert main([str(tmp_path / "nope"), "--out", str(tmp_path / "o")]) == 4


def test_help_survives_legacy_console_encoding(tmp_path):
    # Windows console cp1252: help/lỗi tiếng Việt không được làm crash (bắt được khi smoke .exe)
    env = {**__import__("os").environ, "PYTHONIOENCODING": "cp1252", "PYTHONUTF8": "0"}
    r = subprocess.run([sys.executable, "-m", "vcf_pack", "--help"],
                       capture_output=True, env=env)
    assert r.returncode == 0, r.stderr.decode("cp1252", "replace")
    r = subprocess.run([sys.executable, "-m", "vcf_pack", str(tmp_path / "nope"), "--out",
                        str(tmp_path / "o")], capture_output=True, env=env)
    assert r.returncode == 4, r.stderr.decode("cp1252", "replace")


def test_module_entry_point_runs(nus_root, tmp_path):
    r = subprocess.run([sys.executable, "-m", "vcf_pack", str(nus_root), "--out",
                        str(tmp_path / "o"), "--part-size", PART],
                       capture_output=True, text=True)
    assert r.returncode == 0, r.stderr
