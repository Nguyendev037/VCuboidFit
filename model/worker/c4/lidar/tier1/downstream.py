"""M9 · downstream (PDF §5.4, stretch): huấn luyện PointPillars trên S ∪ A và chấm trên T, với CÙNG
config/epoch/sweeps như model seed. Chạy TRONG image vcuboidfit_pointpillars sau train_seed.

python -m c4.lidar.tier1.downstream --exp /exp --nusc /nusc
    --selected /exp/V/hybrid_mmr/selected_5pct.csv --tag hybrid [--epochs 20] [--batch 2]
Gọi lần lượt cho tập method và random (vd random_0) rồi so `t1/downstream/*/eval.json`.
Mã thoát: 0 ok · 2 bất biến (A chạm T, hoặc A rỗng) · 3 GPU/train lỗi · 4 thiếu file.
"""
import argparse
import json
import pickle
import sys
from pathlib import Path

import pandas as pd
import yaml

from c4.lidar.tier1.train_seed import (
    build_infos,
    data_root,
    link_output,
    make_cfg,
    run_key,
    run_train,
    verify_written,
)


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--exp", type=Path, default=Path("/exp"))
    ap.add_argument("--nusc", type=Path, default=Path("/nusc"))
    ap.add_argument("--selected", type=Path, required=True)
    ap.add_argument("--tag", required=True)
    ap.add_argument("--epochs", type=int, default=None, help="mặc định = epoch của model seed")
    ap.add_argument("--batch", type=int, default=2)
    ap.add_argument("--workers", type=int, default=4)
    a = ap.parse_args(argv)
    seed_cfg = a.exp / "t1" / "train_config.yaml"
    if not seed_cfg.is_file() or not a.selected.is_file():
        print(f"thiếu {seed_cfg} hoặc {a.selected}", file=sys.stderr)
        return 4
    sc = yaml.safe_load(seed_cfg.read_text(encoding="utf-8"))
    sweeps, epochs = sc["sweeps"], a.epochs or sc["epochs"]
    index = pd.read_parquet(a.exp / "index.parquet")
    sel = pd.read_csv(a.selected)
    B = int(sel["budget_B"].iloc[0])
    A = set(sel.loc[sel["rank"] <= B, "sample_token"])
    S = set(index.loc[index["split"] == "S", "sample_token"])
    T = set(index.loc[index["split"] == "T", "sample_token"])
    if not A or A & T:
        print("tập chọn rỗng hoặc chạm split T (chấm downstream sẽ rò)", file=sys.stderr)
        return 2
    version = sc["version"]
    root = data_root(a.exp, a.nusc, version)
    p_all = build_infos(a.exp, a.nusc, version, sweeps)
    with open(p_all, "rb") as f:
        infos = pickle.load(f)
    by_tok = {i["token"]: i for i in infos}
    order = index["sample_token"].tolist()
    train = [by_tok[t] for t in order if t in (S | A) and t in by_tok]
    test = [by_tok[t] for t in order if t in T and t in by_tok]
    d = a.exp / "t1" / "pcdet"
    p_train = d / f"infos_train_{a.tag}_{sweeps}sweeps.pkl"
    p_test = d / f"infos_T_{sweeps}sweeps.pkl"
    with open(p_train, "wb") as f:
        pickle.dump(train, f)
    if not p_test.is_file():
        with open(p_test, "wb") as f:
            pickle.dump(test, f)
    cbgs = bool(sc.get("balanced_resampling", False))  # ÉP như model seed: mọi arm cùng config
    try:
        cfg_path, stats = make_cfg(a.exp, root, version, p_train, p_test, sweeps, epochs,
                                   name=f"pp_ds_{a.tag}", cbgs=cbgs)
        verify_written(p_train, cfg_path, S | A)
    except ValueError as e:
        print(f"vi phạm bất biến: {e}", file=sys.stderr)
        return 2
    run_tag = f"{a.tag}_{run_key([i['token'] for i in train], sweeps, epochs, cbgs)}"
    print(f"downstream {a.tag}: |S|={len(S)} |A|={len(A)} train={len(train)} test={len(test)} "
          f"sweeps={sweeps} epochs={epochs} CBGS={cbgs} tag={run_tag}", flush=True)
    _, post_eval, run_dir = run_train(cfg_path, run_tag, epochs, a.batch, a.workers,
                                      link_output(a.exp))
    summaries = (sorted(run_dir.rglob("eval/**/metrics_summary.json"),
                        key=lambda p: p.stat().st_mtime) if run_dir else [])
    res = dict(tag=a.tag, run_tag=run_tag, post_train_eval=post_eval, n_S=len(S), n_A=len(A),
               sweeps=sweeps, epochs=epochs, selected=str(a.selected), **stats)
    if summaries:
        m = json.loads(summaries[-1].read_text())
        res.update(mAP=m.get("mean_ap"), NDS=m.get("nd_score"),
                   AP_per_class=m.get("mean_dist_aps"))
    else:
        res.update(mAP=None, NDS=None, error="không có metrics_summary.json (eval lỗi?)")
    dst = a.exp / "t1" / "downstream" / a.tag
    dst.mkdir(parents=True, exist_ok=True)
    (dst / "eval.json").write_text(json.dumps(res, indent=1, ensure_ascii=False), encoding="utf-8")
    print(json.dumps({k: res[k] for k in ("tag", "run_tag", "mAP", "NDS", "post_train_eval")}))
    return 0 if summaries else 3


if __name__ == "__main__":
    sys.exit(main())
