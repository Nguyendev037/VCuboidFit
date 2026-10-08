"""M4 · huấn luyện PointPillars TỪ ĐẦU chỉ trên seed S (SPEC-P02 §2). Chạy TRONG image vcf-tier1.

python -m c4.lidar.tier1.train_seed --exp /exp --nusc /nusc [--version v1.0-mini] [--sweeps 10]
    [--epochs 20] [--batch 2] [--workers 4]

Mã thoát: 0 ok · 2 vi phạm bất biến (seed rỗng / info ngoài S) · 3 không GPU/OOM · 4 thiếu file.
"""
import argparse
import copy
import hashlib
import os
import pickle
import shutil
import subprocess
import sys
from pathlib import Path

import pandas as pd
import yaml

PCDET = Path(os.environ.get("PCDET_ROOT", "/opt/OpenPCDet"))
BASE_CFG = "cfgs/nuscenes_models/cbgs_pp_multihead.yaml"


def _pcdet_commit() -> str:
    """Commit OpenPCDet đã build; thiếu file (cài tay trên Kaggle/Colab) không được làm hỏng run."""
    f = PCDET / "BUILD_COMMIT"
    return f.read_text().strip() if f.is_file() else "unknown"


def detect_version(nusc: Path) -> str:
    vs = sorted(p.name for p in nusc.glob("v1.0-*") if p.is_dir())
    if len(vs) != 1:
        raise FileNotFoundError(f"{nusc}: cần đúng một thư mục v1.0-*, thấy {vs}")
    return vs[0]


def data_root(exp: Path, nusc: Path, version: str) -> Path:
    """OpenPCDet đọc `<DATA_PATH>/<version>/` ⇒ dựng thư mục ghi được, version → symlink /nusc."""
    root = exp / "t1" / "pcdet_data"
    root.mkdir(parents=True, exist_ok=True)
    link = root / version
    if not link.exists():
        link.symlink_to(nusc, target_is_directory=True)
    return root


def build_infos(exp: Path, nusc: Path, version: str, sweeps: int) -> Path:
    """Info cho MỌI keyframe (mọi scene là 'train' để có gt cho S) → lọc theo index ở bước sau."""
    out = exp / "t1" / "pcdet" / f"infos_all_{sweeps}sweeps.pkl"
    if out.is_file():
        return out
    from nuscenes.nuscenes import NuScenes
    from pcdet.datasets.nuscenes import nuscenes_utils

    nu = NuScenes(version=version, dataroot=str(nusc), verbose=False)
    scenes = {s["token"] for s in nuscenes_utils.get_available_scenes(nu)}
    infos, _ = nuscenes_utils.fill_trainval_infos(
        data_path=nusc, nusc=nu, train_scenes=scenes, val_scenes=set(), test=False,
        max_sweeps=sweeps, with_cam=False)
    out.parent.mkdir(parents=True, exist_ok=True)
    with open(out, "wb") as f:
        pickle.dump(infos, f)
    return out


def split_infos(all_path: Path, index: pd.DataFrame, sweeps: int) -> tuple[Path, Path, Path, list]:
    with open(all_path, "rb") as f:
        infos = pickle.load(f)
    by_tok = {i["token"]: i for i in infos}
    seed = set(index.loc[index["split"] == "S", "sample_token"])
    if not seed:
        raise ValueError("split S rỗng")
    seed_infos = [by_tok[t] for t in index["sample_token"] if t in seed and t in by_tok]
    if not seed_infos or not {i["token"] for i in seed_infos} <= seed:
        raise ValueError("info seed rỗng hoặc chứa token ngoài S")
    ordered = []
    for t in index["sample_token"]:
        info = copy.deepcopy(by_tok[t]) if t in by_tok else None
        if info is not None:
            ordered.append(info)
    test = set(index.loc[index["split"] == "T", "sample_token"])
    test_infos = [i for i in ordered if i["token"] in test]
    d = all_path.parent
    p_seed, p_ord = d / f"infos_seed_{sweeps}sweeps.pkl", d / f"infos_index_{sweeps}sweeps.pkl"
    p_test = d / f"infos_T_{sweeps}sweeps.pkl"
    for p, obj in ((p_seed, seed_infos), (p_ord, ordered), (p_test, test_infos)):
        with open(p, "wb") as f:
            pickle.dump(obj, f)
    return p_seed, p_ord, p_test, [i["token"] for i in seed_infos]


def to_plain(x):
    if isinstance(x, dict):  # _BASE_CONFIG_ đã được gộp; giữ lại sẽ trỏ đường dẫn tương đối
        return {k: to_plain(v) for k, v in x.items() if k != "_BASE_CONFIG_"}
    if isinstance(x, (list, tuple)):
        return [to_plain(v) for v in x]
    return x


def seed_class_counts(p_seed: Path, class_names) -> dict:
    with open(p_seed, "rb") as f:
        infos = pickle.load(f)
    counts = {c: 0 for c in class_names}
    for i in infos:
        for n in i.get("gt_names", []):
            if n in counts:
                counts[n] += 1
    return counts


def make_cfg(exp: Path, root: Path, version: str, p_seed: Path, p_test: Path, sweeps: int,
             epochs: int, name: str = "pp_seed", cbgs: bool | None = None) -> tuple[Path, dict]:
    """Config đầy đủ (đã gộp _BASE_CONFIG_) với các thay đổi bắt buộc của SPEC-P02 §2.3."""
    from easydict import EasyDict
    from pcdet.config import cfg_from_yaml_file

    cwd = os.getcwd()
    os.chdir(PCDET / "tools")
    try:
        cfg = cfg_from_yaml_file(BASE_CFG, EasyDict())
    finally:
        os.chdir(cwd)
    d = cfg.DATA_CONFIG
    d.DATA_PATH = str(root)
    d.VERSION = version
    d.MAX_SWEEPS = sweeps
    # test = T: eval sau train của OpenPCDet (nuScenes eval) đòi đúng các sample của split chấm;
    # infer_t1 tự đổi sang infos_index (mọi frame)
    d.INFO_PATH = {"train": [str(p_seed)], "test": [str(p_test)]}
    # gt_sampling dựng DB từ nhãn ngoài S ⇒ model leakage (SPEC-P02 vùng cấm)
    d.DATA_AUGMENTOR.AUG_CONFIG_LIST = [a for a in d.DATA_AUGMENTOR.AUG_CONFIG_LIST
                                        if a.NAME != "gt_sampling"]
    cfg.OPTIMIZATION.NUM_EPOCHS = epochs
    counts = seed_class_counts(p_seed, cfg.CLASS_NAMES)
    missing = [c for c, n in counts.items() if n == 0]
    # CBGS chia cho số mẫu từng lớp ⇒ seed thiếu lớp (vd mini 2 scene) phải tắt resampling.
    # cbgs != None (downstream) ⇒ ÉP cùng giá trị với model seed để mọi arm cùng config.
    if cbgs is None:
        d.BALANCED_RESAMPLING = bool(d.get("BALANCED_RESAMPLING", False)) and not missing
    else:
        if cbgs and missing:
            raise ValueError(f"ép CBGS bật nhưng tập train thiếu lớp {missing}")
        d.BALANCED_RESAMPLING = bool(cbgs)
    plain = to_plain(cfg)
    for k in ("ROOT_DIR", "LOCAL_RANK", "TAG", "EXP_GROUP_PATH"):
        plain.pop(k, None)
    out = exp / "t1" / "cfg" / f"{name}.yaml"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(yaml.safe_dump(plain, sort_keys=False), encoding="utf-8")
    return out, dict(class_counts=counts, missing_classes=missing,
                     balanced_resampling=bool(d.BALANCED_RESAMPLING))


def verify_written(p_train: Path, cfg_path: Path, allowed: set) -> None:
    """Đo lại trên file ĐÃ GHI (không tin biến trong bộ nhớ): mọi token train ∈ allowed và cfg
    không có gt_sampling. Vi phạm ⇒ ValueError (thoát 2)."""
    with open(p_train, "rb") as f:
        toks = {i["token"] for i in pickle.load(f)}
    if not toks or not toks <= allowed:
        raise ValueError(f"{p_train.name}: {len(toks - allowed)} token ngoài tập cho phép")
    cfg = yaml.safe_load(cfg_path.read_text(encoding="utf-8"))
    augs = [a["NAME"] for a in cfg["DATA_CONFIG"]["DATA_AUGMENTOR"]["AUG_CONFIG_LIST"]]
    if "gt_sampling" in augs:
        raise ValueError(f"{cfg_path.name}: còn gt_sampling")


def run_key(tokens, sweeps: int, epochs: int, cbgs: bool) -> str:
    """Khoá chạy: đổi tập train / sweeps / epochs / CBGS ⇒ thư mục output mới, không bao giờ tự
    resume checkpoint của cấu hình khác (OpenPCDet train.py tự resume ckpt mới nhất)."""
    h = hashlib.sha1("|".join(sorted(tokens)).encode())
    h.update(f"|{sweeps}|{epochs}|{int(cbgs)}".encode())
    return h.hexdigest()[:8]


def link_output(exp: Path) -> Path:
    """output của OpenPCDet nằm trong image (mất khi container --rm thoát) ⇒ trỏ ra volume /exp."""
    out_dir = exp / "t1" / "pcdet_output"
    out_dir.mkdir(parents=True, exist_ok=True)
    link = PCDET / "output"
    if link.is_symlink() or not link.exists():
        if link.is_symlink():
            link.unlink()
        link.symlink_to(out_dir, target_is_directory=True)
    return out_dir


def run_train(cfg_path: Path, tag: str, epochs: int, batch: int, workers: int,
              out_dir: Path) -> tuple[Path | None, str, Path | None]:
    """Train qua tools/train.py với extra_tag = tag (đã gồm run_key). Đã có ckpt epoch cuối của
    đúng tag ⇒ dùng lại, KHÔNG gọi train.py (tránh eval chờ vô hạn khi mọi ckpt đã eval).
    Trả (ckpt cuối | None, trạng thái eval sau train, thư mục run | None)."""
    pattern = f"{cfg_path.stem}/{tag}/ckpt/checkpoint_epoch_{epochs}.pth"
    done = sorted(out_dir.rglob(pattern))
    if done:
        return done[-1], "reused", done[-1].parent.parent
    cmd = [sys.executable, "train.py", "--cfg_file", str(cfg_path), "--batch_size", str(batch),
           "--epochs", str(epochs), "--workers", str(workers), "--extra_tag", tag,
           "--fix_random_seed", "--max_ckpt_save_num", "2", "--ckpt_save_interval", "1"]
    r = subprocess.run(cmd, cwd=PCDET / "tools")
    done = sorted(out_dir.rglob(pattern))
    if not done:
        return None, f"train.py exit {r.returncode}", None
    # train xong nhưng eval sau train (nuScenes devkit) lỗi — vd model seed yếu không ra box nào
    # trên T ("Invalid box type: None") — không chặn Tầng 1, chỉ ghi lại
    status = "ok" if r.returncode == 0 else f"failed (train.py exit {r.returncode})"
    return done[-1], status, done[-1].parent.parent


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--exp", type=Path, default=Path("/exp"))
    ap.add_argument("--nusc", type=Path, default=Path("/nusc"))
    ap.add_argument("--version", default=None)
    ap.add_argument("--sweeps", type=int, default=10)
    ap.add_argument("--epochs", type=int, default=20)
    ap.add_argument("--batch", type=int, default=2)
    ap.add_argument("--workers", type=int, default=4)
    a = ap.parse_args(argv)
    import torch

    from c4.lidar.tier1.repro import set_determinism
    determinism = set_determinism(0)

    if not torch.cuda.is_available():
        print("cần GPU (Tầng 0 vẫn chạy CPU)", file=sys.stderr)
        return 3
    try:
        version = a.version or detect_version(a.nusc)
        index = pd.read_parquet(a.exp / "index.parquet")
        root = data_root(a.exp, a.nusc, version)
        p_all = build_infos(a.exp, a.nusc, version, a.sweeps)
        p_seed, _, p_test, seed_toks = split_infos(p_all, index, a.sweeps)
        cfg_path, seed_stats = make_cfg(a.exp, root, version, p_seed, p_test, a.sweeps,
                                        a.epochs)
    except FileNotFoundError as e:
        print(f"thiếu đầu vào: {e}", file=sys.stderr)
        return 4
    except ValueError as e:
        print(f"vi phạm bất biến: {e}", file=sys.stderr)
        return 2
    try:
        verify_written(p_seed, cfg_path, set(seed_toks) & set(
            index.loc[index["split"] == "S", "sample_token"]))
    except ValueError as e:
        print(f"vi phạm bất biến: {e}", file=sys.stderr)
        return 2
    (a.exp / "t1" / "seed_tokens.txt").write_text("\n".join(seed_toks), encoding="utf-8")
    cbgs = seed_stats["balanced_resampling"]
    tag = f"seed_{run_key(seed_toks, a.sweeps, a.epochs, cbgs)}"
    print(f"seed: {len(seed_toks)} frame · sweeps {a.sweeps} · epochs {a.epochs} · "
          f"CBGS {cbgs} · thiếu lớp {seed_stats['missing_classes']} · tag {tag}", flush=True)
    ckpt, post_eval, _ = run_train(cfg_path, tag, a.epochs, a.batch, a.workers,
                                   link_output(a.exp))
    if ckpt is None:
        print(f"{post_eval} (OOM? thử --batch 1 --sweeps 1)", file=sys.stderr)
        return 3
    dst = a.exp / "t1" / "ckpt"
    dst.mkdir(parents=True, exist_ok=True)
    shutil.copy2(ckpt, dst / "seed_latest.pth")
    (a.exp / "t1" / "train_config.yaml").write_text(yaml.safe_dump(dict(
        version=version, sweeps=a.sweeps, epochs=a.epochs, batch=a.batch, n_seed=len(seed_toks),
        base_cfg=BASE_CFG, pcdet_commit=_pcdet_commit(), run_tag=tag,
        determinism=determinism,
        gt_sampling=False,  # đã đo trên cfg ghi ra bởi verify_written
        ckpt=str(dst / "seed_latest.pth"), post_train_eval=post_eval, **seed_stats)),
        encoding="utf-8")
    print(f"ckpt: {dst / 'seed_latest.pth'} ({post_eval})")
    return 0


if __name__ == "__main__":
    sys.exit(main())
