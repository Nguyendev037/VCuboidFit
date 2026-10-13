"""D2 - Xuất số benchmark cho web: `report_pitch.json` -> `bench_pitch.json` (SPEC-P01 §2, contract C1).

    python model/worker/scripts/export_demo_bench.py --report <report_pitch.json> --out <dir>

Sinh `<out>/bench_pitch.json` theo schema `vcf-demo-bench-v1` (01-CONTRACTS §C1) và chép các hình
nằm cạnh report vào `<out>/`. Web CHỈ đọc file này, KHÔNG tính lại (00-ARCHITECTURE §3).

Bất biến (C1):
  - `label`, `conclusion`, `pool`, `scenes`, `capture_primary` và mọi con số của từng phương pháp
    là NGUYÊN VĂN của report; KHÔNG làm tròn, KHÔNG ẩn CI95, KHÔNG đổi tên baseline,
    KHÔNG chọn lọc phương pháp đẹp.
  - `conclusion` chỉ nhận {"shown", "not shown / underpowered"}; giá trị lạ ⇒ exit 2 và KHÔNG ghi
    file nào (fail closed), tuyệt đối không tự sửa kết luận.
  - `source.report_sha256` = sha256 tệp report gốc (truy vết nguồn).
  - `source.repo_sha` / `source.code_sha` lấy từ short HEAD của repo sản phẩm tại thời điểm xuất,
    ghi đè được bằng cờ khi xuất số T (REPO_SHA của gói code Colab + commit code thật).

Chỉ dùng thư viện chuẩn: chạy được bằng python hệ thống, KHÔNG cần venv có `c4`/torch.
Mã thoát: 0 ok · 2 thiếu đầu vào / vi phạm contract.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
import shutil
import subprocess
import sys
from pathlib import Path

SCHEMA = "vcf-demo-bench-v1"
FIGURES = ("fig_iy_budget.png", "fig_context.png", "fig_examples.png")
METHOD_ORDER = ("M0", "M1", "M2", "M3")
METHOD_NAMES = {"M0": "Random", "M1": "Legacy", "M2": "lidar_only", "M3": "multisensor"}
# Cặp chính của report: `c4/cli/bench_pitch.py` tính `paired_ci(boot, "M2", "M1")` cho primary_delta.
PRIMARY_PAIR = "M2-M1"
ALLOWED_CONCLUSIONS = ("shown", "not shown / underpowered")
REQUIRED_KEYS = ("label", "pool", "scenes", "capture_primary", "B", "methods",
                 "primary_delta", "conclusion", "reachability")


class InputError(Exception):
    """Thiếu đầu vào hoặc report vi phạm contract C1."""


def _utf8() -> None:
    for stream in (sys.stdout, sys.stderr):  # Windows cp1252 làm crash khi in tiếng Việt
        stream.reconfigure(encoding="utf-8", errors="replace")


def _default_repo() -> Path:
    # <repo>/model/worker/scripts/export_demo_bench.py -> <repo>
    return Path(__file__).resolve().parents[3]


def _git_sha(root: Path) -> str:
    """Short HEAD của `root`; "" khi không phải repo git (KHÔNG bịa sha)."""
    env = {k: v for k, v in os.environ.items() if not k.startswith("GIT_CONFIG_")}
    try:
        done = subprocess.run(["git", "-C", str(root), "rev-parse", "--short", "HEAD"],
                              capture_output=True, text=True, encoding="utf-8",
                              env=env, timeout=15)
    except (OSError, subprocess.SubprocessError):
        return ""
    return done.stdout.strip() if done.returncode == 0 else ""


def _num(value):
    """float hữu hạn, None khi thiếu/không phải số/NaN (JSON không cho NaN)."""
    if value is None or isinstance(value, bool):
        return None
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if math.isfinite(number) else None


def _int(value):
    number = _num(value)
    return None if number is None else int(number)


def _sanitize(obj):
    """Thay NaN/Infinity bằng None để `json.dumps(allow_nan=False)` không nổ giữa đường."""
    if isinstance(obj, dict):
        return {str(k): _sanitize(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple)):
        return [_sanitize(v) for v in obj]
    if isinstance(obj, float) and not math.isfinite(obj):
        return None
    return obj


def _methods(raw: dict) -> dict:
    """M0..M3 nguyên văn số; phương pháp chưa đo giữ đúng trạng thái "chưa đo"."""
    raw_methods = raw["methods"]
    if not isinstance(raw_methods, dict):
        raise InputError("`methods` phải là object")
    out: dict[str, dict] = {}
    order = list(METHOD_ORDER) + [m for m in raw_methods if m not in METHOD_ORDER]
    for key in order:
        row = raw_methods.get(key)
        if not isinstance(row, dict) or "iy" not in row:
            out[key] = {"name": METHOD_NAMES.get(key, str(key)), "iy": None,
                        "ci_lo": None, "ci_hi": None, "status": "chưa đo"}
            continue
        ci = row.get("ci95") or [None, None]
        item = {"name": METHOD_NAMES.get(key, str(key)), "iy": _num(row["iy"]),
                "ci_lo": _num(ci[0]) if len(ci) else None,
                "ci_hi": _num(ci[1]) if len(ci) > 1 else None, "status": "ok"}
        if "ny" in row:
            item["ny"] = _num(row["ny"])
        out[key] = item
    return out


def build(report_path, out_dir, *, run_id: str | None = None, repo_sha: str | None = None,
          code_sha: str | None = None, repo=None) -> dict:
    """Đọc report, ghi `<out>/bench_pitch.json` + chép hình, trả payload."""
    report_path = Path(report_path)
    if not report_path.is_file():
        raise InputError(f"không thấy report: {report_path}")
    raw_bytes = report_path.read_bytes()
    try:
        raw = json.loads(raw_bytes.decode("utf-8"))
    except (UnicodeDecodeError, ValueError) as exc:
        raise InputError(f"report không phải JSON UTF-8 đọc được: {exc}") from exc
    if not isinstance(raw, dict):
        raise InputError("report phải là object JSON")
    missing = [k for k in REQUIRED_KEYS if k not in raw]
    if missing:
        raise InputError("report thiếu khoá bắt buộc: " + ", ".join(missing))

    conclusion = raw["conclusion"]
    if conclusion not in ALLOWED_CONCLUSIONS:
        raise InputError(f"conclusion ngoài contract C1: {conclusion!r} "
                         f"(chỉ nhận {ALLOWED_CONCLUSIONS})")

    primary_raw = raw["primary_delta"]
    if not isinstance(primary_raw, dict):
        raise InputError("`primary_delta` phải là object")
    reach_raw = raw["reachability"]
    if not isinstance(reach_raw, dict):
        raise InputError("`reachability` phải là object")

    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    figures = []
    for name in FIGURES:
        src = report_path.parent / name
        if src.is_file():
            shutil.copy2(src, out / name)
            figures.append(name)

    head = _git_sha(Path(repo) if repo else _default_repo())
    payload = {
        "schema": SCHEMA,
        "source": {
            "run_id": run_id or report_path.parent.name,
            "repo_sha": repo_sha if repo_sha is not None else head,
            "code_sha": code_sha if code_sha is not None else head,
            "prereg_sha256": str(raw.get("prereg_sha256", "")),
            # chỉ report mode=pool của T mới có (bench_pitch.py); mini để "" thay vì bịa
            "final_config_sha256": str(raw.get("final_config_sha256", "")),
            "report_sha256": hashlib.sha256(raw_bytes).hexdigest(),
        },
        "label": str(raw["label"]),
        "pool": _int(raw["pool"]),
        "scenes": _int(raw["scenes"]),
        "capture_primary": str(raw["capture_primary"]),
        "budget_B": _int(raw["B"]),
        "methods": _methods(raw),
        "primary": {
            "pair": PRIMARY_PAIR,
            "delta": _num(primary_raw.get("delta")),
            "ci_lo": _num(primary_raw.get("lo")),
            "ci_hi": _num(primary_raw.get("hi")),
            "conclusion": conclusion,
        },
        "reachability": {
            "radius_m": _num(reach_raw.get("radius_m")),
            "n_targets": _int(reach_raw.get("n_targets")),
            "methods": _sanitize(reach_raw.get("methods") or {}),
        },
        "figures": figures,
    }
    text = json.dumps(payload, ensure_ascii=False, indent=2, allow_nan=False) + "\n"
    (out / "bench_pitch.json").write_text(text, encoding="utf-8")
    return payload


def make_parser() -> argparse.ArgumentParser:
    ap = argparse.ArgumentParser(prog="export_demo_bench", description=__doc__.splitlines()[0])
    ap.add_argument("--report", required=True, type=Path, help="report_pitch.json của bench_pitch")
    ap.add_argument("--out", required=True, type=Path, help="thư mục đích (web/public/demo)")
    ap.add_argument("--run-id", default=None, help="mặc định: tên thư mục chứa report")
    ap.add_argument("--repo-sha", default=None, help="REPO_SHA của gói code (mặc định: HEAD)")
    ap.add_argument("--code-sha", default=None, help="commit code sinh số (mặc định: HEAD)")
    ap.add_argument("--repo", default=None, help="gốc repo để đọc git (mặc định: repo sản phẩm)")
    return ap


def main(argv=None) -> int:
    _utf8()
    args = make_parser().parse_args(argv)
    try:
        payload = build(args.report, args.out, run_id=args.run_id, repo_sha=args.repo_sha,
                        code_sha=args.code_sha, repo=args.repo)
    except InputError as exc:
        print(f"export_demo_bench: {exc}", file=sys.stderr)
        return 2
    ok = sum(1 for m in payload["methods"].values() if m["status"] == "ok")
    src = payload["source"]
    print(f"export_demo_bench: {payload['label']} · B={payload['budget_B']} · "
          f"{ok}/{len(payload['methods'])} phương pháp đo được · "
          f"conclusion={payload['primary']['conclusion']!r} · "
          f"figures={len(payload['figures'])} · sha={src['report_sha256'][:12]} -> "
          f"{Path(args.out) / 'bench_pitch.json'}")
    if not src["repo_sha"] or not src["code_sha"]:
        print("export_demo_bench: cảnh báo — không đọc được git sha, source.repo_sha/code_sha = ''",
              file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
