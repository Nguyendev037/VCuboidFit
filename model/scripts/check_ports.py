"""Kiểm tĩnh bất biến cổng (SPEC-P01 §2b): MỘT biến VCF_PORT, cấm số cổng cứng.

Quét model/docker/**/Dockerfile, **/docker-compose.yml, **/*.sh và web/lib/server/worker.ts.
FAIL (exit 1, in file:dòng) nếu:
  - dòng lệnh chạy (uvicorn / --port / HEALTHCHECK / healthcheck / urlopen / host:port) chứa số cổng
    cứng ngoài vị trí "mặc định của VCF_PORT";
  - mapping `ports` hai vế khác biến, không dùng VCF_PORT, hoặc thiếu vế host;
  - service `pointpillars` khai `ports`;
  - worker.ts không suy URL từ VCF_PORT.
Chỉ dùng thư viện chuẩn + pyyaml. Exit 0 khi sạch.
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

import yaml

REPO = Path(__file__).resolve().parents[2]
KEYWORDS = re.compile(r"uvicorn|--port|HEALTHCHECK|healthcheck|urlopen|curl|127\.0\.0\.1|localhost|0\.0\.0\.0", re.I)
# Chỗ được phép chứa số: mặc định của VCF_PORT / alias WORKER_PORT, ENV VCF_PORT=, EXPOSE (chỉ tài liệu)
ALLOWED = [
    re.compile(r"\$\{VCF_PORT:-\$\{WORKER_PORT:-\d+\}\}"),
    re.compile(r"\$\{(?:VCF_PORT|WORKER_PORT):-\d+\}"),
    re.compile(r"VCF_PORT\s*(?:=|\|\||\?\?)\s*[\"'`]?\d+[\"'`]?"),
    re.compile(r"^\s*EXPOSE\s+\d+\s*$"),
]
PORTLIKE = re.compile(r"(?<![\d.])\d{4,5}(?![\d.])")  # 4-5 chữ số, không phải một phần IP/phiên bản


def _files() -> list[Path]:
    d = REPO / "model" / "docker"
    out = [*d.rglob("Dockerfile"), *d.rglob("docker-compose.yml"), *d.rglob("*.sh")]
    w = REPO / "web" / "lib" / "server" / "worker.ts"
    if w.is_file():
        out.append(w)
    return sorted(set(out))


def _scan_lines(path: Path, text: str, errs: list[str]) -> None:
    for n, line in enumerate(text.splitlines(), 1):
        s = line.strip()
        if not s or s.startswith("#") or s.startswith("//") or s.startswith("*"):
            continue
        if not KEYWORDS.search(s):
            continue
        for rx in ALLOWED:
            s = rx.sub("", s)
        m = PORTLIKE.search(s)
        if m:
            errs.append(f"{path.relative_to(REPO)}:{n}: số cổng cứng '{m.group()}' — dùng VCF_PORT")


def _check_compose(path: Path, text: str, errs: list[str]) -> None:
    rel = path.relative_to(REPO)
    try:
        doc = yaml.safe_load(text) or {}
    except yaml.YAMLError as e:
        errs.append(f"{rel}:1: YAML lỗi: {e}")
        return
    for name, svc in (doc.get("services") or {}).items():
        ports = svc.get("ports") or []
        if name == "pointpillars" and ports:
            errs.append(f"{rel}: service pointpillars CẤM khai ports (chạy batch)")
        for p in ports:
            p = str(p).strip()
            line = next((i for i, ln in enumerate(text.splitlines(), 1) if p in ln), 1)
            depth, cuts = 0, []
            for i, ch in enumerate(p):  # tách ở dấu ':' NGOÀI ${...}
                depth += (ch == "{") - (ch == "}")
                if ch == ":" and depth == 0:
                    cuts.append(i)
            if len(cuts) != 1:
                errs.append(f"{rel}:{line}: ports '{p}' thiếu vế host (cổng ngẫu nhiên bị cấm)")
                continue
            host, cont = p[:cuts[0]], p[cuts[0] + 1:]
            if "VCF_PORT" not in host or host != cont:
                errs.append(f"{rel}:{line}: ports '{p}' hai vế không cùng một biến VCF_PORT")
        if ports and "VCF_PORT" not in str((svc.get("environment") or "")):
            errs.append(f"{rel}: service {name} publish cổng nhưng environment thiếu VCF_PORT")


def main() -> int:
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")
    errs: list[str] = []
    files = _files()
    for f in files:
        text = f.read_text(encoding="utf-8")
        _scan_lines(f, text, errs)
        if f.name == "docker-compose.yml":
            _check_compose(f, text, errs)
        if f.name == "worker.ts" and "VCF_PORT" not in text:
            errs.append(f"{f.relative_to(REPO)}:1: workerUrl phải suy URL từ VCF_PORT")
    for e in errs:
        print(e, file=sys.stderr)
    print(f"check_ports: {len(files)} file, {len(errs)} lỗi")
    return 1 if errs else 0


if __name__ == "__main__":
    sys.exit(main())
