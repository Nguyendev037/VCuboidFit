"""Cổng thứ tự, băm đúng byte và marker mở trước thao tác."""
import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path

from c4.contracts import _git_sha


class BenchGateError(RuntimeError):
    def __init__(self, code: str, detail: str = ""):
        self.code = code
        super().__init__(f"{code}: {detail}")


def sha256(path: Path) -> str:
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def require(path: Path) -> Path:
    if not path.is_file():
        raise BenchGateError("MISSING_INPUT", str(path))
    return path


def check_prereg(job: Path, expected_sha: str) -> None:
    bench = Path(job) / "bench"
    actual = sha256(require(bench / "prereg.txt"))
    saved = require(bench / "prereg_sha256.txt").read_text().strip()
    if actual != expected_sha or actual != saved:
        raise BenchGateError("PREREG_MISMATCH", str(bench / "prereg.txt"))


def check_selections(job: Path) -> dict:
    bench = Path(job) / "bench"
    if not (bench / "selections.json").is_file() or not (
            bench / "selections_sha256.txt").is_file():
        raise BenchGateError("ORDER_VIOLATION", "freeze selections first")
    sels = json.loads((bench / "selections.json").read_text(encoding="utf-8"))
    if sha256(bench / "selections.json") != (bench / "selections_sha256.txt").read_text().strip():
        raise BenchGateError("ORDER_VIOLATION", "selection hash mismatch")
    check_prereg(job, sels["prereg_sha256"])
    if sha256(require(bench / "bench_split.parquet")) != sels["split_sha256"]:
        raise BenchGateError("ORDER_VIOLATION", "split hash mismatch")
    return sels


def freeze_selections(job: Path, sels: dict) -> str:
    bench = Path(job) / "bench"
    check_prereg(job, sels["prereg_sha256"])
    if sha256(require(bench / "bench_split.parquet")) != sels["split_sha256"]:
        raise BenchGateError("ORDER_VIOLATION", "split hash mismatch")
    if (bench / "pool_opened.json").exists() or list((bench / "judge").glob("judge_*_pool*")):
        raise BenchGateError("ORDER_VIOLATION", "POOL already judged")
    payload = json.dumps(sels, sort_keys=True, indent=1, ensure_ascii=False).encode("utf-8")
    try:
        with (bench / "selections.json").open("xb") as f:
            f.write(payload)
    except FileExistsError as exc:
        raise BenchGateError("ORDER_VIOLATION", "selections already frozen") from exc
    digest = hashlib.sha256(payload).hexdigest()
    (bench / "selections_sha256.txt").write_text(digest, encoding="utf-8")
    return digest


def open_once(job: Path, what: str) -> dict:
    if what not in {"pool", "eval"}:
        raise ValueError(what)
    bench = Path(job) / "bench"
    check_selections(job)
    require(bench / "judge" / "judge_calib.json")
    marker = dict(created_at=datetime.now(timezone.utc).isoformat(), repo_sha=_git_sha())
    try:
        with (bench / f"{what}_opened.json").open("x", encoding="utf-8") as f:
            json.dump(marker, f, sort_keys=True)
    except FileExistsError as exc:
        raise BenchGateError("ALREADY_OPENED", what) from exc
    return marker
