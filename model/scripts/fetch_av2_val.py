"""Tải có chọn lọc Argoverse 2 Sensor VAL (hồ sơ 21, SPEC-P01 §4) từ bucket S3 công khai.

python -I model/scripts/fetch_av2_val.py --out F:/vcf_ext/av2/src [--logs N] [--workers 32] [--dry-run]

Chỉ lấy những gì adapter cần: toàn bộ LiDAR (10 Hz: keyframe 2 Hz + sweeps), 7 camera vòng ở khung
gần nhất mỗi keyframe 2 Hz (|Δt| ≤ 50 ms, camera 20 Hz ⇒ ~1/10 số ảnh), annotations.feather,
calibration/*, city_SE3_egovehicle.feather. Bỏ stereo và map. Đo 2026-10-17: VAL đầy đủ 166 GB,
phần chọn lọc ≈ 36 GB. Tải tiếp được: file đã có đúng kích thước thì bỏ qua. Ghi manifest.tsv
(key, bytes) và done.json. License: CC BY-NC-SA 4.0 (chỉ nghiên cứu).

Mã thoát: 0 ok · 2 lỗi mạng/liệt kê sau 5 lần thử · 3 thiếu file sau khi tải (kích thước lệch).
"""
import argparse
import bisect
import concurrent.futures as cf
import json
import os
import re
import sys
import time
import urllib.parse
import urllib.request
from pathlib import Path

BUCKET = "https://argoverse.s3.amazonaws.com/"
PREFIX = "datasets/av2/sensor/val/"
RING = ["ring_front_center", "ring_front_left", "ring_front_right", "ring_side_left",
        "ring_side_right", "ring_rear_left", "ring_rear_right"]
KEEP_FILES = ("annotations.feather", "city_SE3_egovehicle.feather")
TOL_NS = 50_000_000


def _get(url, tries=5):
    for k in range(tries):
        try:
            return urllib.request.urlopen(url, timeout=120).read()
        except OSError:
            if k == tries - 1:
                raise
            time.sleep(2 ** k)


def list_keys(prefix, delimiter=None):
    """[(key, size)] hoặc [common_prefix] khi có delimiter."""
    out, token = [], None
    while True:
        q = {"list-type": "2", "prefix": prefix, "max-keys": "1000"}
        if delimiter:
            q["delimiter"] = delimiter
        if token:
            q["continuation-token"] = token
        x = _get(BUCKET + "?" + urllib.parse.urlencode(q)).decode()
        if delimiter:
            out += re.findall(r"<Prefix>([^<]+)</Prefix>", x)[1:]  # phần tử đầu là chính prefix
        else:
            out += [(k, int(s)) for k, s in re.findall(r"<Key>([^<]+)</Key>.*?<Size>(\d+)</Size>", x, re.S)]
        if "<IsTruncated>true</IsTruncated>" not in x:
            return out
        token = re.search(r"<NextContinuationToken>([^<]+)</NextContinuationToken>", x).group(1)


def plan_log(log_prefix):
    """Chọn file cần tải cho một log. Trả [(key, size)]."""
    keys = list_keys(log_prefix)
    lidar = sorted((int(Path(k).stem), k, s) for k, s in keys if "/sensors/lidar/" in k)
    key_ts = [ts for ts, _, _ in lidar[::5]]  # keyframe 2 Hz, cùng quy tắc adapter (khung 0, 5, 10…)
    want = [(k, s) for _, k, s in lidar]
    want += [(k, s) for k, s in keys if "/calibration/" in k or k.endswith(KEEP_FILES)]
    for cam in RING:
        cams = sorted((int(Path(k).stem), k, s) for k, s in keys if f"/sensors/cameras/{cam}/" in k)
        if not cams:
            continue
        ts_list = [c[0] for c in cams]
        for t in key_ts:
            i = bisect.bisect_left(ts_list, t)
            best = min((j for j in (i - 1, i) if 0 <= j < len(cams)), key=lambda j: abs(ts_list[j] - t))
            if abs(ts_list[best] - t) <= TOL_NS:
                want.append(cams[best][1:])
    return sorted(set(want))


def download(item, out):
    key, size = item
    dst = out / key[len(PREFIX):]
    if dst.is_file() and dst.stat().st_size == size:
        return 0
    dst.parent.mkdir(parents=True, exist_ok=True)
    data = _get(BUCKET + urllib.parse.quote(key))
    tmp = dst.with_name(dst.name + ".part")
    tmp.write_bytes(data)
    os.replace(tmp, dst)
    return len(data)


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--out", type=Path, required=True)
    ap.add_argument("--logs", type=int, default=None, help="chỉ N log đầu (theo thứ tự tên)")
    ap.add_argument("--workers", type=int, default=32)
    ap.add_argument("--dry-run", action="store_true")
    a = ap.parse_args(argv)
    try:
        logs = sorted(list_keys(PREFIX, delimiter="/"))[: a.logs]
        with cf.ThreadPoolExecutor(a.workers) as ex:
            plans = list(ex.map(plan_log, logs))
    except OSError as e:
        print(json.dumps({"error": "LIST_FAILED", "detail": str(e)}))
        return 2
    items = [it for p in plans for it in p]
    total = sum(s for _, s in items)
    print(json.dumps({"logs": len(logs), "files": len(items), "gb": round(total / 1e9, 2)}), flush=True)
    if a.dry_run:
        return 0
    a.out.mkdir(parents=True, exist_ok=True)
    (a.out / "manifest.tsv").write_text("".join(f"{k}\t{s}\n" for k, s in items), encoding="utf-8")
    got, t0, n = 0, time.time(), 0
    with cf.ThreadPoolExecutor(a.workers) as ex:
        for b in ex.map(lambda it: download(it, a.out), items):
            got += b
            n += 1
            if n % 2000 == 0:
                rate = got / max(time.time() - t0, 1e-6)
                print(json.dumps({"done_files": n, "of": len(items), "gb": round(got / 1e9, 2),
                                  "mb_s": round(rate / 1e6, 2)}), flush=True)
    bad = [k for k, s in items if not ((a.out / k[len(PREFIX):]).is_file()
                                       and (a.out / k[len(PREFIX):]).stat().st_size == s)]
    (a.out / "done.json").write_text(json.dumps({"logs": len(logs), "files": len(items), "bytes": total,
                                                 "missing": len(bad), "source": BUCKET + PREFIX,
                                                 "license": "CC BY-NC-SA 4.0"}), encoding="utf-8")
    print(json.dumps({"missing": len(bad), "elapsed_min": round((time.time() - t0) / 60, 1)}))
    return 3 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
