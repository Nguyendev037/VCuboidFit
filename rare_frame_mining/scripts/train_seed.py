#!/usr/bin/env python3
"""BƯỚC 0 (TUỲ CHỌN) — chuẩn bị và train model Seed. Lõi pipeline KHÔNG cần bước này.

Quyết định 10/10 ("Cả hai"): lõi dùng checkpoint PointPillars công khai đóng băng; bước 0
và vòng retrain là công tắc tuỳ chọn. Script này làm 3 việc:

  1. `manifest`  — chọn tập Seed (frame ĐÃ có nhãn) và ghi seed_manifest.json
                   {"scenes": [...], "fids": [...], "round": k}. Manifest được truyền vào
                   run_pipeline --seed-manifest → frame Seed bị ép split=PILOT, không lọt V/T.
  2. `add`       — vòng lặp retrain: gộp frame vừa gán nhãn (ledger: lô selected=1 và,
                   nếu bật phương án B, lô explore=1) vào manifest → round k+1.
  3. `infos`     — (nuScenes + OpenPCDet) lọc file infos .pkl của split train xuống đúng các
                   scene Seed, rồi in lệnh train. Chạy train thật cần GPU + OpenPCDet; script
                   KHÔNG tự train (môi trường sandbox không có GPU) — nó in lệnh để chạy.

Ví dụ (nuScenes, Seed = 100 scene đầu tiên của split train, V/T vẫn là 150 scene val):
  python scripts/train_seed.py manifest --source nuscenes --dataroot /data/nuScenes \
      --version v1.0-trainval --seed-split train --n-scenes 100 --out seed_manifest.json
  python scripts/train_seed.py infos --dataroot /data/nuScenes --version v1.0-trainval \
      --manifest seed_manifest.json --infos /data/nuScenes/nuscenes_infos_10sweeps_train.pkl
  # → in lệnh OpenPCDet; train xong:
  python scripts/run_pipeline.py --source nuscenes --dataroot /data/nuScenes \
      --version v1.0-trainval --model-mode seed --seed-manifest seed_manifest.json \
      --detector openpcdet --checkpoint seed_r0.pth --model-config pointpillar_seed.yaml ...

Data công ty (BinDir): `manifest --source bindir --labeled-fids labeled.json`.
"""
import argparse
import json
import os
import pickle
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def _load_list(path):
    with open(path, "r", encoding="utf-8") as f:
        data = json.load(f)
    if isinstance(data, dict) and "pilot_fids" in data:
        return list(data["pilot_fids"])
    if isinstance(data, dict) and "fids" in data:
        return list(data["fids"])
    if isinstance(data, dict):
        return [k for k, v in data.items() if v]
    return list(data)


def cmd_manifest(args):
    if args.source == "nuscenes":
        from rare_mining import NuscenesSource
        # Seed lấy từ split train; provenance="seed" vì model Seed sẽ chỉ thấy các scene này.
        src = NuscenesSource(args.dataroot, args.version, args.seed_split, model_provenance="seed")
        frames = src.frames()
        scenes = sorted({f.scene for f in frames})
        if args.n_scenes > 0:
            import random
            rnd = random.Random(args.seed)
            scenes = sorted(rnd.sample(scenes, min(args.n_scenes, len(scenes))))
        fids = [f.fid for f in frames if f.scene in set(scenes)]
    else:
        if not args.labeled_fids:
            raise SystemExit("bindir: cần --labeled-fids (danh sách frame đã có nhãn)")
        fids = _load_list(args.labeled_fids)
        scenes = sorted({fid.rsplit("_f", 1)[0] for fid in fids})
    man = {"round": 0, "scenes": scenes, "fids": fids,
           "source": args.source, "version": getattr(args, "version", "")}
    with open(args.out, "w", encoding="utf-8") as f:
        json.dump(man, f, ensure_ascii=False, indent=2)
    print(f"Seed round 0: {len(scenes)} scene, {len(fids)} frame → {args.out}")


def cmd_add(args):
    with open(args.manifest, "r", encoding="utf-8") as f:
        man = json.load(f)
    new = []
    for p in args.labeled:
        new += _load_list(p)
    before = set(man["fids"])
    man["fids"] = sorted(before | set(new))
    man["scenes"] = sorted(set(man["scenes"]) | {fid.rsplit("_f", 1)[0] for fid in new})
    man["round"] = int(man.get("round", 0)) + 1
    out = args.out or args.manifest
    with open(out, "w", encoding="utf-8") as f:
        json.dump(man, f, ensure_ascii=False, indent=2)
    print(f"Seed round {man['round']}: +{len(set(new) - before)} frame mới, tổng {len(man['fids'])} → {out}")
    print("Bước tiếp: train lại (lệnh `infos`), chạy run_pilot.py sanity với checkpoint mới, "
          "rồi run_pipeline --seed-manifest với manifest này (vòng mới).")


def cmd_infos(args):
    try:
        from nuscenes.nuscenes import NuScenes
    except Exception as e:
        raise SystemExit("Cần nuscenes-devkit") from e
    with open(args.manifest, "r", encoding="utf-8") as f:
        man = json.load(f)
    keep_scenes = set(man["scenes"])
    keep_fids = set(man["fids"])
    nusc = NuScenes(version=args.version, dataroot=args.dataroot, verbose=False)
    tok2fid = {}
    for sc in nusc.scene:
        tok, k = sc["first_sample_token"], 0
        while tok:
            tok2fid[tok] = (sc["name"], f"{sc['name']}_f{k:04d}")
            k += 1
            tok = nusc.get("sample", tok)["next"]
    with open(args.infos, "rb") as f:
        infos = pickle.load(f)
    kept = []
    for info in infos:
        scene, fid = tok2fid.get(info.get("token"), (None, None))
        if scene in keep_scenes and (fid in keep_fids or args.whole_scenes):
            kept.append(info)
    out = args.out or args.infos.replace(".pkl", f"_seed_r{man.get('round', 0)}.pkl")
    with open(out, "wb") as f:
        pickle.dump(kept, f)
    print(f"Infos Seed: {len(kept)}/{len(infos)} sample → {out}")
    print("\nLệnh train (OpenPCDet, chạy trên máy có GPU):")
    print(f"  # sửa INFO_PATH.train trong cfg nuscenes_dataset.yaml thành [{os.path.basename(out)}]")
    print("  cd OpenPCDet/tools && python train.py "
          "--cfg_file cfgs/nuscenes_models/cbgs_pp_multihead.yaml "
          f"--extra_tag seed_r{man.get('round', 0)}")
    print("Train xong: chạy run_pilot.py sanity với checkpoint mới TRƯỚC khi chạy full pool; "
          "ghi mAP của Seed trên tập val (biết model đủ tốt cho uncertainty hay không).")


def main():
    ap = argparse.ArgumentParser(description="Bước 0 tuỳ chọn: tập Seed + train/retrain")
    sub = ap.add_subparsers(dest="cmd", required=True)
    a = sub.add_parser("manifest")
    a.add_argument("--source", required=True, choices=["nuscenes", "bindir"])
    a.add_argument("--dataroot", default="")
    a.add_argument("--version", default="v1.0-trainval")
    a.add_argument("--seed-split", default="train")
    a.add_argument("--n-scenes", type=int, default=0, help="0 = lấy hết scene của seed-split")
    a.add_argument("--labeled-fids", default="")
    a.add_argument("--seed", type=int, default=0)
    a.add_argument("--out", default="seed_manifest.json")
    b = sub.add_parser("add")
    b.add_argument("--manifest", required=True)
    b.add_argument("--labeled", nargs="+", required=True,
                   help="file JSON list fid đã gán nhãn (lô selected=1, lô explore=1)")
    b.add_argument("--out", default="")
    c = sub.add_parser("infos")
    c.add_argument("--dataroot", required=True)
    c.add_argument("--version", default="v1.0-trainval")
    c.add_argument("--manifest", required=True)
    c.add_argument("--infos", required=True, help="nuscenes_infos_*_train.pkl của OpenPCDet")
    c.add_argument("--whole-scenes", action="store_true")
    c.add_argument("--out", default="")
    args = ap.parse_args()
    {"manifest": cmd_manifest, "add": cmd_add, "infos": cmd_infos}[args.cmd](args)


if __name__ == "__main__":
    main()
