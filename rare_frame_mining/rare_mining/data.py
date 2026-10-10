"""Khung dữ liệu chung + 3 nguồn: Synthetic (demo), BinDir (data công ty), NuScenes (adapter).

Frame là bản ghi MỎNG: điểm được load lazy qua `loader()`. GT (nếu nguồn có) được
nạp QUA `gt_fn()` — pipeline KHÔNG bao giờ gọi gt_fn; chỉ M6 (đánh giá) gọi.
Đây là cơ chế "nhãn thật giấu đi" của đề bài.
"""
import glob
import json
import os
from dataclasses import dataclass, field
from typing import Callable, List, Optional, Tuple

import numpy as np


@dataclass
class GTBox:
    center: Tuple[float, float, float]   # ego/sensor frame
    size: Tuple[float, float, float]     # (L, W, H)
    yaw: float
    class_name: str                      # pedestrian | bicycle | motorcycle | car | ...
    num_lidar_pts: int = -1              # -1 = không biết
    attributes: tuple = ()


@dataclass
class Frame:
    fid: str
    scene: str
    t: float                              # giây (hoặc đơn vị tỉ lệ được cho dedup)
    ego_xy: Tuple[float, float]           # vị trí ego (cùng hệ qua các frame) cho dedup
    desc: str = ""                        # mô tả scene tự do (thời tiết/đêm)
    loader: Optional[Callable[[], np.ndarray]] = None   # trả về (N, >=3) float32 [x y z (intensity)]
    gt_fn: Optional[Callable[[], List[GTBox]]] = None   # GT — chỉ M6 được gọi
    camera_paths: tuple = ()
    # Tư thế LiDAR trong hệ toàn cục (yaw, x, y) — để đối chiếu vật giữa 2 keyframe (cổng ngoại lai,
    # phép 2). None → cổng dùng bán kính + độ dịch ego (kém chặt hơn).
    sensor_pose: Optional[Tuple[float, float, float]] = None

    def load_points(self) -> np.ndarray:
        if self.loader is None:
            raise RuntimeError(f"Frame {self.fid} không có loader điểm")
        return self.loader()

    def load_gt(self) -> List[GTBox]:
        return self.gt_fn() if self.gt_fn else []


# ---------------------------------------------------------------------------
# Nguồn 1: thư mục .npy/.bin (data công ty hoặc dữ liệu đã chuyển đổi)
# ---------------------------------------------------------------------------

class BinDirSource:
    """Thư mục dạng:
        root/*.npy hoặc root/*.bin   — mỗi file 1 frame (N, 3|4) float32
        root/meta.json (tuỳ chọn)    — {"fid": {"scene":..., "t":..., "ego":[x,y], "desc":...}}
        root/gt.json (tuỳ chọn)      — {"fid": [{"center":[x,y,z],"size":[l,w,h],
                                                    "yaw":..,"class":"bicycle"}]}
    Scene mặc định = tên file trước '_' hoặc 'default'; t mặc định = chỉ số file.
    """

    def __init__(self, root: str):
        self.root = root
        self.files = sorted(glob.glob(os.path.join(root, "*.npy")) + glob.glob(os.path.join(root, "*.bin")))
        if not self.files:
            raise RuntimeError(f"Không tìm thấy *.npy/*.bin trong {root}")
        self.meta = {}
        mp = os.path.join(root, "meta.json")
        if os.path.exists(mp):
            with open(mp, "r", encoding="utf-8") as f:
                self.meta = json.load(f)
        self.gt = {}
        gp = os.path.join(root, "gt.json")
        if os.path.exists(gp):
            with open(gp, "r", encoding="utf-8") as f:
                self.gt = json.load(f)

    @staticmethod
    def _simple_class(cat: str) -> str:
        c = cat.split(".")[-1].lower()
        if c.startswith("ped"):
            return "pedestrian"
        return c

    def frames(self) -> List[Frame]:
        out = []
        for i, p in enumerate(self.files):
            fid = os.path.splitext(os.path.basename(p))[0]
            m = self.meta.get(fid, {})
            scene = m.get("scene", fid.split("_")[0] if "_" in fid else "default")
            t = float(m.get("t", i))
            ego = tuple(m.get("ego", (0.0, 0.0)))
            desc = m.get("desc", "")

            def loader(p=p):
                if p.endswith(".npy"):
                    return np.load(p).astype(np.float32)
                return np.fromfile(p, dtype=np.float32).reshape(-1, 4)[:, :4]

            gt_fn = None
            if fid in self.gt:
                def gtfn(fid=fid):
                    return [GTBox(center=tuple(g["center"]), size=tuple(g["size"]),
                                  yaw=float(g.get("yaw", 0.0)),
                                  class_name=self._simple_class(g.get("class", "other")),
                                  num_lidar_pts=int(g.get("num_lidar_pts", -1)))
                            for g in self.gt[fid]]
                gt_fn = gtfn
            out.append(Frame(fid=fid, scene=scene, t=t, ego_xy=ego, desc=desc,
                             loader=loader, gt_fn=gt_fn))
        return out


# ---------------------------------------------------------------------------
# Nguồn 2: nuScenes (cần nuscenes-devkit) — ADAPTER, xem ghi chú trong README
# ---------------------------------------------------------------------------

def _simple_class(cat: str) -> str:
    tail = cat.split(".")[-1].lower()
    if cat.startswith("human.pedestrian"):
        return "pedestrian"
    if cat in ("vehicle.bicycle", "bicycle"):
        return "bicycle"
    if cat in ("vehicle.motorcycle", "motorcycle"):
        return "motorcycle"
    if tail in ("car", "truck", "bus", "trailer", "construction_vehicle"):
        return "car"
    return tail if tail else "other"


# Split mặc định khi model là checkpoint CÔNG KHAI (đã train trên nuScenes train):
# chỉ scene model CHƯA thấy mới được vào V/T — nếu không s_unc/s_ood bị lệch (leak).
DEFAULT_UNSEEN_SPLIT = {"v1.0-trainval": "val", "v1.0-mini": "mini_val"}
# Split mà checkpoint công khai nuScenes đã thấy khi train.
SEEN_BY_PUBLIC_CKPT = {"train", "mini_train", "train_detect", "train_track"}


def select_scenes(all_names, version: str, split: str, splits: dict,
                  model_provenance: str = "nuscenes_train") -> List[str]:
    """Chọn scene theo split CHÍNH THỨC của nuScenes (`splits` = create_splits_scenes()).

    - split="auto": val (trainval) / mini_val (mini) — mặc định an toàn cho checkpoint công khai.
    - split="all": mọi scene của version — CHỈ hợp lệ khi model KHÔNG train trên nuScenes
      (model_provenance = "seed" | "external"); ngược lại raise để chặn leak.
    - split là tên trong `splits` (val, mini_val, train, ...): lấy đúng danh sách đó.
    """
    names = set(all_names)
    if split == "auto":
        split = DEFAULT_UNSEEN_SPLIT.get(version, "all")
    if split == "all":
        chosen = sorted(names)
        if model_provenance == "nuscenes_train":
            seen = set().union(*(set(splits.get(k, ())) for k in SEEN_BY_PUBLIC_CKPT))
            if names & seen:
                raise ValueError(
                    "split='all' gồm scene mà checkpoint công khai đã thấy khi train → leak. "
                    "Dùng --split auto (val/mini_val) hoặc khai báo --model-provenance seed|external.")
        return chosen
    if split not in splits:
        raise ValueError(f"split không hợp lệ: {split}. Có: auto, all, {', '.join(sorted(splits))}")
    if model_provenance == "nuscenes_train" and split in SEEN_BY_PUBLIC_CKPT:
        raise ValueError(f"split '{split}' là dữ liệu train của checkpoint công khai → leak.")
    chosen = sorted(names & set(splits[split]))
    if not chosen:
        raise ValueError(f"split '{split}' không có scene nào trong {version}")
    return chosen


class NuscenesSource:
    """Đọc keyframes (mặc định — phản biện kỹ thuật: KHÔNG chạy trên 380k sweeps).

    - version: 'v1.0-mini' | 'v1.0-trainval' (test không có GT → không eval được)
    - split: 'auto' (mặc định) = val chính thức (150 scene) với trainval, mini_val (2 scene)
      với mini. Lý do: checkpoint PointPillars công khai đã train trên split train.
      Khi dùng model Seed tự train (bước 0 tuỳ chọn) → `model_provenance="seed"` và
      có thể dùng split khác/"all", miễn loại frame Seed qua --exclude-fids.
    - Chỉ nạp LIDAR_TOP keyframe; desc lấy từ scene['description'] (văn bản tự do).
    - GT: sample_annotation (center = global → đổi về frame sensor của LiDAR;
      num_lidar_pts lấy thẳng từ schema — dùng cho rule '<10 điểm').
    - ƯỚC LƯỢNG yaw bằng trích quaternion 2D (yaw ≈, đủ cho BEV-IoU; ghi rõ trong README).
    """

    def __init__(self, dataroot: str, version: str = "v1.0-mini", split: str = "auto",
                 use_camera_brightness: bool = False, model_provenance: str = "nuscenes_train"):
        try:
            from nuscenes.nuscenes import NuScenes
            from nuscenes.utils.splits import create_splits_scenes
        except Exception as e:
            raise RuntimeError("Cần nuscenes-devkit: pip install nuscenes-devkit") from e
        self.nusc = NuScenes(version=version, dataroot=dataroot, verbose=False)
        self.version = version
        self.use_cam = use_camera_brightness
        all_names = [s["name"] for s in self.nusc.scene]
        names = select_scenes(all_names, version, split, create_splits_scenes(),
                              model_provenance)
        self.split = DEFAULT_UNSEEN_SPLIT.get(version, "all") if split == "auto" else split
        self.allowed_scenes = set(names)
        print(f"NuscenesSource: {version} split={self.split} → {len(names)} scene "
              f"(model_provenance={model_provenance})")

    def frames(self) -> List[Frame]:
        from pyquaternion import Quaternion
        nusc = self.nusc
        out: List[Frame] = []
        for scene in nusc.scene:
            if scene["name"] not in self.allowed_scenes:
                continue
            desc = scene.get("description", "")
            sample_token = scene["first_sample_token"]
            k = 0
            while sample_token:
                sample = nusc.get("sample", sample_token)
                sd = nusc.get("sample_data", sample["data"]["LIDAR_TOP"])
                if not sd.get("is_key_frame", True):
                    sample_token = sample["next"]
                    continue
                ep = nusc.get("ego_pose", sd["ego_pose_token"])
                cs = nusc.get("calibrated_sensor", sd["calibrated_sensor_token"])
                fid = f"{scene['name']}_f{k:04d}"
                k += 1
                t = sample["timestamp"] / 1e6
                ego_xy = (ep["translation"][0], ep["translation"][1])
                pc_path = os.path.join(nusc.dataroot, sd["filename"])

                cam_paths = ()
                if self.use_cam:
                    try:
                        csd = nusc.get("sample_data", sample["data"]["CAM_FRONT"])
                        cam_paths = (os.path.join(nusc.dataroot, csd["filename"]),)
                    except Exception:
                        pass

                R_e = Quaternion(ep["rotation"]).rotation_matrix
                R_c = Quaternion(cs["rotation"]).rotation_matrix
                t_e = np.array(ep["translation"])
                t_c = np.array(cs["translation"])

                def loader(pc_path=pc_path):
                    return np.fromfile(pc_path, dtype=np.float32).reshape(-1, 5)[:, :4]

                anns = list(sample.get("anns", []))

                def gtfn(anns=anns, R_e=R_e, t_e=t_e, R_c=R_c, t_c=t_c):
                    boxes = []
                    for tok in anns:
                        rec = nusc.get("sample_annotation", tok)
                        pg = np.array(rec["translation"])
                        p_e = R_e.T @ (pg - t_e)
                        p_s = R_c.T @ (p_e - t_c)
                        yaw_g = Quaternion(rec["rotation"]).yaw_pitch_roll[0]
                        yaw_s = yaw_g - float(np.arctan2(R_e[1, 0], R_e[0, 0])) \
                            - float(np.arctan2(R_c[1, 0], R_c[0, 0]))
                        attrs = tuple(nusc.get("attribute", a)["name"] for a in rec["attribute_tokens"])
                        boxes.append(GTBox(
                            center=(float(p_s[0]), float(p_s[1]), float(p_s[2])),
                            size=(float(rec["size"][0]), float(rec["size"][1]), float(rec["size"][2])),
                            yaw=float(yaw_s),
                            class_name=_simple_class(rec["category_name"]),
                            num_lidar_pts=int(rec["num_lidar_pts"]),
                            attributes=attrs))
                    return boxes

                t_s = R_e @ t_c + t_e
                yaw_s = float(np.arctan2(R_e[1, 0], R_e[0, 0]) + np.arctan2(R_c[1, 0], R_c[0, 0]))
                out.append(Frame(fid=fid, scene=scene["name"], t=t, ego_xy=ego_xy,
                                 desc=desc, loader=loader, gt_fn=gtfn if anns else None,
                                 camera_paths=cam_paths,
                                 sensor_pose=(yaw_s, float(t_s[0]), float(t_s[1]))))
                sample_token = sample["next"]
        return out
