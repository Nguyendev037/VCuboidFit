"""L2: python -m c4.cli.lidar_t1 --job-dir J --data-root D [--resume]
→ t1/signals.parquet (suy luận seed đã train qua Docker; lỗi không chặn job).

Mã thoát: 0 ok hoặc skip có lý do · 2 vi phạm contract · 4 thiếu lidar/index.parquet · 5 Docker lỗi.
"""
import json
import os
import subprocess
import sys
from pathlib import Path

from c4.cli.build_index import make_parser
from c4.contracts import ContractError, read_table

WORKER = Path(__file__).resolve().parents[2]  # .../model/worker
SEED_FILES = (("index.parquet",), ("t1", "cfg", "pp_seed.yaml"), ("t1", "ckpt", "seed_latest.pth"))


def _cfg_version(exp: Path) -> str | None:
    """VERSION nuScenes trong cấu hình pcdet của thí nghiệm (dòng `VERSION: v1.0-...`)."""
    for line in (exp / "t1" / "cfg" / "pp_seed.yaml").read_text(encoding="utf-8").splitlines():
        key, _, val = line.strip().partition(":")
        if key == "VERSION":
            return val.strip().strip("'\"")
    return None


def _data_version(data_root: Path) -> str | None:
    found = sorted(p.name for p in data_root.glob("v1.0-*") if p.is_dir())
    return found[0] if len(found) == 1 else None


def pick_experiment(spec: str, data_root: Path) -> tuple[Path | None, str]:
    """VCF_T1_EXP = một hoặc nhiều thư mục thí nghiệm (ngăn bởi os.pathsep). Chọn thí nghiệm đủ file
    seed và cùng VERSION với dataset (infer_t1 từ chối lệch phiên bản); trả (None, lý do) nếu không có."""
    exps = [Path(s) for s in spec.split(os.pathsep) if s.strip()]
    complete = [e for e in exps if all(e.joinpath(*rel).is_file() for rel in SEED_FILES)]
    if not complete:
        return None, "thiếu " + ", ".join(str(e.joinpath(*r)) for e in exps for r in SEED_FILES
                                          if not e.joinpath(*r).is_file())
    want = _data_version(data_root)
    if want is None:
        return complete[0], ""  # không đọc được phiên bản: giữ hành vi cũ, infer_t1 tự kiểm
    for e in complete:
        if _cfg_version(e) == want:
            return e, ""
    return None, f"không có model seed cho {want} (đang có: " + \
        ", ".join(f"{e.name}={_cfg_version(e)}" for e in complete) + ")"


def main(argv=None) -> int:
    for st in (sys.stdout, sys.stderr):  # Windows cp1252 làm crash khi in tiếng Việt
        st.reconfigure(encoding="utf-8", errors="replace")
    args = make_parser(__doc__.splitlines()[0]).parse_args(argv)
    job = Path(args.job_dir)
    out = job / "t1" / "signals.parquet"
    if args.resume and out.is_file():
        print("skip: đã có")
        return 0
    exp_s = os.environ.get("VCF_T1_EXP", "").strip()
    if not exp_s:
        print("skip: VCF_T1_EXP chưa đặt")
        return 0
    exp, why = pick_experiment(exp_s, Path(args.data_root))
    if exp is None:
        print(f"skip: {why}")
        return 0
    try:
        job_idx = read_table(job / "lidar" / "index.parquet", "lidar_index")
    except FileNotFoundError as e:
        print(f"thiếu đầu vào: {e}", file=sys.stderr)
        return 4
    except ContractError as e:
        print(f"vi phạm contract: {e}", file=sys.stderr)
        return 2
    # D2: suy luận trên pool của job (không cần ⊆ index thí nghiệm); novelty do infer_t1 quyết định
    (job / "t1").mkdir(parents=True, exist_ok=True)
    compose = WORKER.parent / "docker" / "tier1" / "docker-compose.yml"
    env = dict(os.environ, NUSC=str(Path(args.data_root).resolve()), EXP=str(exp.resolve()),
               JOB=str(job.resolve()))
    try:
        rc = subprocess.run(["docker", "compose", "-f", str(compose), "run", "--rm", "infer"],
                            env=env).returncode
    except OSError as e:
        print(f"docker lỗi ({e})", file=sys.stderr)
        return 5
    if rc == 2:
        print("vi phạm contract trong infer_t1 (xem log phía trên)", file=sys.stderr)
        return 2
    if rc != 0:
        print(f"docker lỗi ({rc})", file=sys.stderr)
        return 5
    try:
        sig = read_table(str(out), "t1_signals")
    except FileNotFoundError as e:
        print(f"docker lỗi: không có {e}", file=sys.stderr)
        return 5
    except ContractError as e:
        print(f"vi phạm contract: {e}", file=sys.stderr)
        return 2
    if list(sig["sample_token"]) != job_idx["sample_token"].tolist():
        print("vi phạm contract: signals không khớp pool của job", file=sys.stderr)
        return 2
    nov = "?"
    try:
        nov = json.loads((job / "t1" / "signals.parquet.manifest.json").read_text(
            encoding="utf-8")).get("nov_source", "?")
    except (OSError, ValueError):
        pass
    print(f"t1: {len(sig)} frame · nov_source={nov} → {out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
