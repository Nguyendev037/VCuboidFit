"""CLI benchmark giám khảo, mỗi lệnh xuất đúng một dòng JSON."""
import argparse
from contextlib import redirect_stdout
from datetime import datetime, timezone
import importlib
import io
import json
import math
import os
from pathlib import Path
import re
import sys
import time

import numpy as np
import pandas as pd

from c4.bench.gate import (
    BenchGateError, check_prereg, check_selections, freeze_selections, open_once, require, sha256,
)
from c4.bench.registry import assert_independent
from c4.bench.split import plan_bench_split
from c4.contracts import ContractError, _git_sha, read_table, write_table
from c4.rare.eval import budget, random_selector


def _repo_sha():
    # Colab chạy từ git archive (không có .git) ⇒ notebook đặt VCF_REPO_SHA.
    return os.environ.get("VCF_REPO_SHA") or _git_sha()


def _late(name):
    try:
        return importlib.import_module(f"c4.bench.{name}")
    except ImportError as exc:
        raise BenchGateError("MISSING_INPUT", f"c4.bench.{name}: {exc}") from exc


PREREG_TARGET_RECALL_EASY = 0.90  # SPEC-P03 §4, băm trong prereg


def _json(path, payload):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, sort_keys=True, indent=1,
                               allow_nan=False), encoding="utf-8")


def _frames(job, split):
    index = read_table(require(job / "lidar/index.parquet"), "lidar_index")
    splits = read_table(require(job / "bench/bench_split.parquet"), "bench_split")
    return index.loc[index.scene_token.isin(splits.loc[
        splits.bench_split == split.upper(), "scene_token"])].copy()


def _split(args):
    job, bench = args.job_dir, args.job_dir / "bench"
    if (bench / "bench_split.parquet").exists():
        raise BenchGateError("ORDER_VIOLATION", "split already exists")
    index = read_table(require(job / "lidar/index.parquet"), "lidar_index")
    scenes = index[["scene_token", "scene_name"]].drop_duplicates()
    if scenes.scene_token.duplicated().any() or scenes.scene_name.duplicated().any():
        raise ContractError("scene names/tokens must map one-to-one")
    mapping = plan_bench_split(scenes.scene_name.tolist(), args.seed)
    scenes["bench_split"] = scenes.scene_name.map(mapping)
    scenes["engine_split"] = scenes.bench_split.map({"CAL": "V", "POOL": "T", "EVAL": "P"})
    scenes["n_frames"] = scenes.scene_token.map(index.groupby("scene_token").size())
    write_table(scenes, bench / "bench_split.parquet", "bench_split")
    digest = sha256(bench / "bench_split.parquet")
    (bench / "split_sha256.txt").write_text(digest, encoding="utf-8")
    # Bảng override không có schema riêng trong contracts.
    scenes[["scene_name", "engine_split"]].to_parquet(
        bench / "engine_split_override.parquet", index=False)
    return dict(split_sha256=digest, n_scenes=len(scenes))


def _prereg(args):
    bench = args.job_dir / "bench"
    require(bench / "bench_split.parquet")
    if (bench / "prereg.txt").exists():
        raise BenchGateError("ORDER_VIOLATION", "prereg already exists")
    if args.file is None:
        raise BenchGateError("MISSING_INPUT", "--file required")
    source = require(args.file).read_text(encoding="utf-8")
    blocks = re.findall(r"^```prereg\r?\n(.*?)^```\s*$", source, re.M | re.S)
    if len(blocks) != 1:
        raise BenchGateError("MISSING_INPUT", "exactly one prereg fenced block required")
    (bench / "prereg.txt").write_bytes(blocks[0].replace("\r\n", "\n").encode("utf-8"))
    digest = sha256(bench / "prereg.txt")
    (bench / "prereg_sha256.txt").write_text(digest, encoding="utf-8")
    return dict(prereg_sha256=digest)


def _third_party(method, module, job, pool, bmax, external=None):
    if external is not None:
        selector = module.external_selector(require(Path(external)))
    elif method == "X1":
        feat = pd.read_parquet(require(job / "cache/feat_dino.parquet"))
        emb = np.load(require(job / "cache/dino_cls.npy"))
        vectors, tokens = [], []
        for token, rows in feat.loc[feat.sample_token.isin(pool)].groupby("sample_token", sort=True):
            cams = emb[rows.emb_row.to_numpy(int)]
            cams = cams / np.maximum(np.linalg.norm(cams, axis=1, keepdims=True), 1e-12)
            vector = cams.mean(axis=0)
            vectors.append(vector / max(float(np.linalg.norm(vector)), 1e-12))
            tokens.append(token)
        if set(tokens) != set(pool):
            raise BenchGateError("MISSING_INPUT", "DINO embeddings for all POOL frames")
        selector = module.kcenter_selector(np.asarray(vectors), tokens)
    elif method in {"N1", "N2"}:
        feat = pd.read_parquet(require(job / "cache/feat_dino.parquet"))
        grouped = feat.loc[feat.sample_token.isin(pool)].groupby("sample_token")
        values = grouped.q_blur.min() if method == "N1" else grouped.q_bright.mean()
        selector = module.blur_selector(values) if method == "N1" else module.dark_selector(values)
    elif method in {"X2", "X3"}:
        feat = pd.read_parquet(require(job / "cache/feat_det.parquet"))
        if method == "X2":
            from c4.mining.uncertainty import uncertainty

            det = pd.read_parquet(require(job / "cache/detections.parquet"))
            frames = read_table(require(job / "index/frames.parquet"), "frames")
            frames = frames.loc[frames.sample_token.isin(pool)]
            values = uncertainty(det, frames).groupby("sample_token").unc.max()
            selector = module.entropy_selector(values)
        else:
            det = pd.read_parquet(require(job / "cache/detections.parquet"))
            if not {"sample_token", "conf", "cls"} <= set(det.columns):
                raise BenchGateError("MISSING_INPUT", "YOLO sample_token/conf/cls columns")
            values = det.loc[(det.conf >= 0.5) & det.cls.isin([0, 1, 3])].groupby(
                "sample_token").size().reindex(pool, fill_value=0)
            selector = module.crowd_selector(values)
    else:
        raise BenchGateError("MISSING_INPUT", f"selector {method}")
    try:
        tokens = selector(pool, bmax)
    except ValueError as exc:
        if "ORDER_VIOLATION" in str(exc):
            raise BenchGateError("ORDER_VIOLATION", str(exc)) from exc
        raise
    if not set(tokens) <= set(pool) or len(tokens) != len(set(tokens)):
        raise BenchGateError("ORDER_VIOLATION", method)
    return dict(tokens=tokens, short=len(tokens) < bmax, source=external or method)


def _run_methods(args, job, pool, engine_split="T"):
    """Mọi bên chọn trên cùng `pool`; engine_split = split engine của pool (T, hoặc V khi chọn CAL)."""
    entries = args.methods.split(",")
    ids = [entry.split("=", 1)[0] for entry in entries]
    required = {"OURS", "M1", "M2", "X0", "X1", "X2", "X3", "N1", "N2"}
    if not required <= set(ids) or len(ids) != len(set(ids)):
        raise BenchGateError("ORDER_VIOLATION", "run all mandatory methods once")
    thirdparty = _late("thirdparty")
    from c4.bench.ours import select_ours

    methods, bmax = {}, budget(len(pool), 0.10)
    for entry, method in zip(entries, ids):
        start = time.monotonic()
        if method in {"OURS", "M1", "M2"}:
            if args.data_root is None or args.final_config is None:
                raise BenchGateError("MISSING_INPUT", "--data-root and --final-config")
            methods[method] = select_ours(method, job, args.data_root, args.final_config, pool,
                                          pool_split=engine_split, ref_split="V")
        elif method == "X0":
            methods[method] = {"seeds": {str(s): random_selector(s)(pool, bmax) for s in range(100)}}
        else:
            external = entry.split("=", 1)[1] if "=" in entry else None
            methods[method] = _third_party(method, thirdparty, job, pool, bmax, external)
        methods[method]["elapsed_s"] = time.monotonic() - start
    return methods


def _power(job, sels, st, cal, n_boot, seed):
    """SPEC-P04 §4: MDE = 2.8 · SE(D_JA) trên CAL · sqrt(n_scenes_CAL / n_scenes_POOL). Chỉ quyết định câu chữ."""
    from c4.bench.metrics import struggle_frames, sy
    from c4.rare.eval import bootstrap_fixed

    tf = struggle_frames(st)
    b = budget(len(cal), 0.05)
    fixed = {}
    for name, entry in sels["methods"].items():
        if name == "X0":
            fixed.update({f"X0_s{k}": list(v[:b]) for k, v in entry["seeds"].items()})
        else:
            fixed[name] = list(entry["tokens"][:b])
    frame = cal[["sample_token", "scene_token"]].drop_duplicates()
    boot = bootstrap_fixed(fixed, frame, tf, n_boot=n_boot, seed=seed, capture="any")
    rivals = [m for m in ("X1", "X2", "X3", "Xext") if m in fixed]
    d = boot["OURS"] - boot[rivals].max(axis=1)
    se = float(d.std(ddof=1)) if len(d) > 1 else 0.0
    n_cal, n_pool = int(frame.scene_token.nunique()), int(_frames(job, "POOL").scene_token.nunique())
    x0 = float(np.mean([sy(v, tf) for m, v in fixed.items() if m.startswith("X0_s")]))
    mde = 2.8 * se * math.sqrt(n_cal / n_pool)
    return dict(schema="bench-power/1", judge="JA", label="exploratory", ours_in_sample=True,
                se_D_JA=se, mde=mde, n_scenes_cal=n_cal, n_scenes_pool=n_pool, B_cal=b,
                n_boot=n_boot, seed=seed, sy_x0_mean_cal=x0,
                D_JA_cal=sy(fixed["OURS"], tf) - max(sy(fixed[m], tf) for m in rivals),
                sy_cal={m: sy(v, tf) for m, v in fixed.items() if not m.startswith("X0_s")},
                underpowered=bool(mde > 0.5 * x0), repo_sha=_repo_sha(),
                created_at=datetime.now(timezone.utc).isoformat())


def _select_cal(args):
    """select --split cal --exploratory: chọn trên CAL (OURS in-sample, ref = CAL) ⇒ power.json trước POOL."""
    job, bench = args.job_dir, args.job_dir / "bench"
    digest = require(bench / "prereg_sha256.txt").read_text().strip()
    check_prereg(job, args.expected_sha or digest)
    if (bench / "pool_opened.json").exists() or list((bench / "judge").glob("judge_*_pool*")):
        raise BenchGateError("ORDER_VIOLATION", "power must be written before POOL opens")
    cal = _frames(job, "CAL")
    if cal.empty:
        raise BenchGateError("MISSING_INPUT", "empty CAL")
    sels = dict(schema="bench-selections-cal/1", dataset=args.dataset, prereg_sha256=digest,
                label="exploratory", repo_sha=_repo_sha(), n_cal=len(cal), B=budget(len(cal), 0.05),
                methods=_run_methods(args, job, cal.sample_token.tolist(), "V"),
                created_at=datetime.now(timezone.utc).isoformat())
    _json(bench / "cal/selections_cal.json", sels)
    result = dict(n_cal=len(cal), B_cal=sels["B"], power=None)
    st = bench / "judge/judge_struggle_JA_cal.parquet"
    if st.is_file():
        power = _power(job, sels, read_table(st, "judge_struggle"), cal, args.n_boot, args.seed)
        _json(bench / "power.json", power)
        result["power"] = {k: power[k] for k in ("se_D_JA", "mde", "sy_x0_mean_cal", "underpowered")}
    return result


def _select(args):
    if args.split == "cal" and args.exploratory:
        return _select_cal(args)
    job, bench = args.job_dir, args.job_dir / "bench"
    digest = require(bench / "prereg_sha256.txt").read_text().strip()
    check_prereg(job, args.expected_sha or digest)
    if (bench / "selections.json").exists() or (bench / "pool_opened.json").exists() or list(
            (bench / "judge").glob("judge_*_pool*")):
        raise BenchGateError("ORDER_VIOLATION", "selection must precede judging")
    split_hash = sha256(require(bench / "bench_split.parquet"))
    if split_hash != require(bench / "split_sha256.txt").read_text().strip():
        raise BenchGateError("ORDER_VIOLATION", "split hash mismatch")
    pool = _frames(job, "POOL").sample_token.tolist()
    if not pool:
        raise BenchGateError("MISSING_INPUT", "empty POOL")
    methods = _run_methods(args, job, pool)
    sels = dict(schema="bench-selections/1", dataset=args.dataset, prereg_sha256=digest,
                split_sha256=sha256(require(bench / "bench_split.parquet")), repo_sha=_repo_sha(),
                B=budget(len(pool), 0.05), n_pool=len(pool), methods=methods,
                created_at=datetime.now(timezone.utc).isoformat())
    return dict(selections_sha256=freeze_selections(job, sels), B=sels["B"], n_pool=len(pool))


def _objects(args):
    from c4.bench.aeb import aeb_objects

    job = args.job_dir
    if args.data_root is None:
        raise BenchGateError("MISSING_INPUT", "--data-root required for annotation metadata")
    tables = sorted(args.data_root.glob("v*/sample_annotation.json"))
    if not tables:
        raise BenchGateError("MISSING_INPUT", "sample_annotation.json")
    meta = pd.DataFrame(json.loads(tables[0].read_text(encoding="utf-8")))
    index = read_table(require(job / "lidar/index.parquet"), "lidar_index")
    meta["scene_token"] = meta.sample_token.map(index.set_index("sample_token").scene_token)
    return aeb_objects(read_table(require(job / "gt/gt_boxes_2d.parquet"), "gt_boxes_2d"),
                       read_table(require(job / "gt/boxes_3d.parquet"), "boxes_3d"), meta)


def _open(args, what):
    try:
        return open_once(args.job_dir, what)
    except BenchGateError as exc:
        if exc.code != "ALREADY_OPENED" or not args.exploratory:
            raise
        # Giữ marker lần đầu; đánh dấu mọi report từ lần chạy này là exploratory.
        _json(args.job_dir / "bench" / f"{what}_exploratory.json",
              dict(created_at=datetime.now(timezone.utc).isoformat(), repo_sha=_repo_sha()))


def _judge(args):
    job, bench = args.job_dir, args.job_dir / "bench"
    check_selections(job)
    calib_path = bench / "judge/judge_calib.json"
    if args.split == "pool" and not calib_path.is_file():
        # CAL phải xong trước POOL (01-CONTRACTS §6), nên đây là lỗi THỨ TỰ, không phải thiếu file.
        raise BenchGateError("ORDER_VIOLATION", "judge_calib.json required before POOL")
    module = _late("judge")
    frames = read_table(require(job / "index/frames.parquet"), "frames")
    tokens = _frames(job, args.split).sample_token.tolist()
    frames = frames.loc[frames.sample_token.isin(tokens)].copy()
    data_root = getattr(args, "data_root", None)
    if data_root is not None:
        frames["img_path"] = frames["img_path"].map(lambda p: str(Path(data_root) / str(p)))
    objects = _objects(args)
    objects = objects.loc[objects.sample_token.isin(tokens)]
    if args.split == "pool":
        _open(args, "pool")
        calib = json.loads(calib_path.read_text(encoding="utf-8"))
    else:
        if calib_path.exists():
            raise BenchGateError("ORDER_VIOLATION", "calibration already frozen")
        calib = {}
    out = bench / "judge"
    out.mkdir(exist_ok=True)
    target = float(getattr(args, "target_recall_easy", PREREG_TARGET_RECALL_EASY))
    if args.split == "cal" and target != PREREG_TARGET_RECALL_EASY:
        # Lệch prereg phải để lại dấu: report đọc file này và tự hạ nhãn xuống exploratory.
        _json(bench / "prereg_deviation.json",
              dict(field="judge.target_recall_easy", prereg=PREREG_TARGET_RECALL_EASY, used=target,
                   created_at=datetime.now(timezone.utc).isoformat(), repo_sha=_repo_sha()))
    invalid, tables = [], {}
    for judge in args.judges.split(","):
        det = module.run_judge(judge, frames, device=args.device, batch=args.batch)
        if args.split == "cal":
            calibration = module.calibrate_tau(det, objects, target_recall_easy=target)
            struggle = module.struggle_table(det, objects, calibration["tau"],
                                             calibration.get("iou_thr", 0.5), judge=judge)
            calibration["validity"] = module.validity(struggle, objs=objects,
                                                      calibration=calibration)
            calibration["valid"] = bool(calibration["validity"]["ok"])
            calibration["versions"] = det.attrs.get("versions", {})
            calib[judge] = calibration
            tables[judge] = struggle
            if not calibration["valid"]:
                invalid.append(judge)
        else:
            struggle = module.struggle_table(det, objects, calib[judge]["tau"],
                                             calib[judge].get("iou_thr", 0.5), judge=judge)
        write_table(det, out / f"judge_det_{judge}_{args.split}.parquet", "judge_det")
        write_table(struggle, out / f"judge_struggle_{judge}_{args.split}.parquet", "judge_struggle")
    if args.split == "cal":
        if {"JA", "JB"} <= tables.keys():
            from c4.bench.metrics import cohen_kappa

            kappa = cohen_kappa(tables["JA"], tables["JB"])
            for judge in tables:
                calib[judge]["validity"]["kappa_JA_JB"] = kappa
                calib[judge]["validity"]["v3_ok"] = bool(kappa >= 0.20)
        _json(out / "judge_calib.json", calib)
    if invalid:
        raise BenchGateError("JUDGE_INVALID", str(invalid))
    return dict(split=args.split, judges=list(calib))


def _report(args):
    from c4.bench.metrics import bench_report

    job, bench = args.job_dir, args.job_dir / "bench"
    sels = check_selections(job)
    judges = args.judges.split(",")
    assert_independent(list(sels["methods"]), judges)
    sels["judges"] = json.loads(require(bench / "judge/judge_calib.json").read_text(encoding="utf-8"))
    sels["selections_sha256"] = sha256(bench / "selections.json")
    sels["exploratory"] = (bench / "pool_exploratory.json").exists()
    deviation = bench / "prereg_deviation.json"
    if deviation.is_file():
        sels["exploratory"] = True
        sels["prereg_deviation"] = json.loads(deviation.read_text(encoding="utf-8"))
    power = bench / "power.json"
    if power.is_file():
        sels["power"] = json.loads(power.read_text(encoding="utf-8"))
    tables = {j: read_table(require(bench / f"judge/judge_struggle_{j}_pool.parquet"),
                            "judge_struggle") for j in judges}
    pool_frames = _frames(job, "POOL")
    # Nhãn nội bộ chỉ được nạp ở phía report, reference chỉ fit trên CAL.
    from c4.data.nusc import NuscTables
    from c4.rare.config import load_rare_def
    from c4.rare.gt_rhcio import fit_reference, frame_context, label_gt, load_boxes

    if args.data_root is None:
        raise BenchGateError("MISSING_INPUT", "--data-root")
    data = NuscTables.load(args.data_root)
    cal_tokens = _frames(job, "CAL").sample_token.tolist()
    cfg, _ = load_rare_def()
    ref = fit_reference(load_boxes(data, cal_tokens), frame_context(data, cal_tokens), cfg)
    pool_frames.attrs["internal_gt"] = label_gt(data, pool_frames.sample_token, ref, cfg)
    report = bench_report(sels, tables, _objects(args), pool_frames,
                          n_boot=args.n_boot, seed=args.seed)
    _json(bench / "report/report_judge.json", report)
    dashboard = _late("dashboard")
    render = getattr(dashboard, "render", None)
    if render is None:
        raise BenchGateError("MISSING_INPUT", "dashboard.render")
    render(report, None, job, bench / "report")
    return dict(report=str(bench / "report/report_judge.json"), verdict=report["verdict"])


def _train_eval(args):
    check_selections(args.job_dir)
    module = _late("train_sel")
    run = getattr(module, "run_train_eval", None)
    if run is None:
        raise BenchGateError("MISSING_INPUT", "train_sel.run_train_eval")
    try:
        seeds = [int(seed) for seed in args.seeds.split(",")]
    except ValueError as exc:
        raise BenchGateError("ORDER_VIOLATION", "--seeds must be 0,1,2") from exc
    # SPEC-P05 §3: marker có nhưng chưa có report_train ⇒ resume cùng lần mở (Colab ngắt), được phép.
    # Đã có report_train ⇒ EVAL đã dùng xong; chạy lại chỉ với --exploratory.
    bench = args.job_dir / "bench"
    if ((bench / "eval_opened.json").exists() and (bench / "report/report_train.json").exists()
            and not args.exploratory):
        raise BenchGateError("ALREADY_OPENED", "eval đã hoàn tất; chạy lại chỉ với --exploratory")
    return run(args.job_dir, args.methods.split(","), seeds, data_root=args.data_root,
               open_eval=lambda: _open(args, "eval"), exploratory=args.exploratory)


class _Parser(argparse.ArgumentParser):
    def error(self, message):
        raise BenchGateError("MISSING_INPUT", message)


def main(argv=None):
    parser = _Parser()
    parser.add_argument("command", choices=["split", "prereg", "select", "judge", "report", "train-eval"])
    parser.add_argument("--job-dir", type=Path, required=True)
    parser.add_argument("--seed", type=int, default=20261017)
    parser.add_argument("--file", type=Path)
    parser.add_argument("--expected-sha")
    parser.add_argument("--data-root", type=Path)
    parser.add_argument("--final-config", type=Path)
    parser.add_argument("--dataset", default="nuscenes-pilot")
    parser.add_argument("--methods", default="OURS,M1,M2,X0,X1,X2,X3,N1,N2")
    parser.add_argument("--judges", default="JA,JB")
    parser.add_argument("--split", choices=["cal", "pool"], default="cal")
    parser.add_argument("--device", default="cuda")
    parser.add_argument("--batch", type=int, default=16)
    parser.add_argument("--n-boot", type=int, default=2000)
    parser.add_argument("--exploratory", action="store_true")
    parser.add_argument("--target-recall-easy", type=float, default=PREREG_TARGET_RECALL_EASY)
    parser.add_argument("--seeds", default="0,1,2")
    args, result, code = None, None, 0
    try:
        args = parser.parse_args(argv)
        (args.job_dir / "bench").mkdir(parents=True, exist_ok=True)
        with redirect_stdout(io.StringIO()):
            result = {"split": _split, "prereg": _prereg, "select": _select, "judge": _judge,
                      "report": _report, "train-eval": _train_eval}[args.command](args)
        result = dict(ok=True, command=args.command, **result)
    except (BenchGateError, FileNotFoundError, ContractError) as exc:
        error = getattr(exc, "code", "MISSING_INPUT" if isinstance(exc, FileNotFoundError)
                        else "ORDER_VIOLATION")
        code = {"MISSING_INPUT": 2, "JUDGE_INVALID": 4, "GPU_OOM": 5}.get(error, 3)
        result = dict(ok=False, error=error, detail=str(exc))
    except (KeyError, ValueError, TypeError, OSError, RuntimeError) as exc:
        error = "GPU_OOM" if "out of memory" in str(exc).lower() else "MISSING_INPUT"
        code = 5 if error == "GPU_OOM" else 2
        result = dict(ok=False, error=error, detail=str(exc))
    line = json.dumps(result, ensure_ascii=False, allow_nan=False)
    if args is not None:
        with (args.job_dir / "bench/log.jsonl").open("a", encoding="utf-8") as f:
            f.write(line + "\n")
    print(line)
    return code


if __name__ == "__main__":
    sys.exit(main())
