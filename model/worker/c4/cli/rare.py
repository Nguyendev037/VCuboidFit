"""Engine rare_v24: python -m c4.cli.rare run --job-dir J --data-root D [--budget-frac 0.05] [--pool-split T|V|all]
[--ref-split V|all] [--profile lidar_only|multisensor] [--scoring-config S.json]
-> J/engines/rare_v24/<selectionId>/{rare_objects.parquet, rare_frames.parquet, config_used.json}.
python -m c4.cli.rare crops --job-dir J --data-root D [--device cuda] [--sid S]  (venv có torch)
-> J/cache/{rare_crops.npy, rare_crops.parquet, concepts_text.npy, concepts_text.json}.

Mã thoát (SPEC-P05 §8, SPEC-P06 §6): 0 ok · 2 thiếu đầu vào / vi phạm contract / CROPS_STALE / thiếu trọng số ·
3 config sai (gồm PRED_REF_TOO_SMALL, CONCEPT_REF_EMPTY) · 1 lỗi khác.
"""
import argparse
import json
import sys

from c4.contracts import ContractError


def make_parser() -> argparse.ArgumentParser:
    ap = argparse.ArgumentParser(prog="c4.cli.rare", description=__doc__.splitlines()[0])
    sub = ap.add_subparsers(dest="cmd", required=True)
    run = sub.add_parser("run", help="M2: candidates -> gate -> score -> select")
    run.add_argument("--job-dir", required=True)
    run.add_argument("--data-root", required=True, help="thư mục chứa v1.0-*/")
    run.add_argument("--budget-frac", type=float, default=0.05)
    run.add_argument("--profile", default="lidar_only", choices=["lidar_only", "multisensor"])
    run.add_argument("--scoring-config", default=None, help="JSON ghi đè trọng số mặc định")
    run.add_argument("--pool-split", default="T", choices=["T", "V", "all"])
    run.add_argument("--ref-split", default="V", choices=["V", "all"])
    cr = sub.add_parser("crops", help="M3: chiếu box -> crop ảnh -> OpenCLIP (cần torch)")
    cr.add_argument("--job-dir", required=True)
    cr.add_argument("--data-root", required=True)
    cr.add_argument("--device", default="cuda")
    cr.add_argument("--sid", default=None, help="selectionId rare_objects dùng làm nguồn (mặc định: mới nhất)")
    return ap


def _cmd_crops(args) -> int:
    from c4.rare.semantic import build_crops

    r = build_crops(args.job_dir, args.data_root, device=args.device, sid=args.sid)
    print(f"crops: {r['n_crops']} crops · crops_skipped={r['crops_skipped']} · objects={r['n_objects']} "
          f"projected={r['n_projected']} · sid={r['sid']} · elapsed={r['elapsed_s']}s -> {r['dir']}")
    return 0


def _cmd_run(args) -> int:
    from c4.rare.pipeline import run_rare_v24

    scoring = None
    if args.scoring_config:
        with open(args.scoring_config, encoding="utf-8") as f:
            scoring = json.load(f)
    r = run_rare_v24(args.job_dir, args.data_root, profile=args.profile, budget_frac=args.budget_frac,
                     pool_split=args.pool_split, ref_split=args.ref_split, scoring=scoring)
    g = r["gate_counts"]
    print(f"rare_v24: {r['n_objects']} objects · {r['n_frames']} frames · B={r['B']} · selected={len(r['selected'])} · "
          f"gate: {g.get('valid', 0)} valid / {g.get('suspect', 0)} suspect / {g.get('outlier', 0)} outlier · "
          f"mode={r['modelMode']}")
    print(f"ranking={len(r['ranking'])} eligible={r['eligible_n']} warnings={r['warnings']} "
          f"elapsed={r['elapsed_s']}s -> {r['selection_dir']}")
    return 0


def main(argv=None) -> int:
    for st in (sys.stdout, sys.stderr):  # Windows cp1252 làm crash khi in tiếng Việt
        st.reconfigure(encoding="utf-8", errors="replace")
    args = make_parser().parse_args(argv)
    from c4.rare.candidates import ClassMapError
    from c4.rare.pipeline import PredRefTooSmall
    from c4.rare.semantic import ConceptRefEmpty, CropsStale
    try:
        return {"run": _cmd_run, "crops": _cmd_crops}[args.cmd](args)
    except (ClassMapError, PredRefTooSmall, ConceptRefEmpty, json.JSONDecodeError) as e:
        print(f"config sai: {type(e).__name__}: {e}", file=sys.stderr)
        return 3
    except (FileNotFoundError, CropsStale) as e:
        print(f"thiếu đầu vào: {e}", file=sys.stderr)
        return 2
    except ContractError as e:
        print(f"vi phạm contract: {e}", file=sys.stderr)
        return 2
    except Exception as e:  # noqa: BLE001 — mã 1 = lỗi khác
        print(f"lỗi: {type(e).__name__}: {e}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
