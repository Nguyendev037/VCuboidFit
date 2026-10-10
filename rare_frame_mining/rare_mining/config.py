"""Cấu hình trung tâm của pipeline (M0-M6).

Mọi tham số có mặc định hợp lý; có thể ghi đè bằng file JSON
(xem PipelineConfig.from_json). Trọng số mặc định đặt ĐỀU —
đây chính là biến thể "label-free" theo phản biện (không tune bằng GT).
Optional: tune theo rule trên tập V qua run_pipeline(tune="rule_v").
"""
from dataclasses import dataclass, field, asdict, is_dataclass
import json
from typing import Dict, List, Tuple, Optional


@dataclass
class ROIConfig:
    min_range: float = 1.0      # m — bỏ điểm quá gần
    max_range: float = 50.0     # m — ROI quan tâm (đề: vật xa >30 m vẫn nằm trong ROI)
    z_min: float = -2.0
    z_max: float = 3.5


@dataclass
class ClusterConfig:
    ground_cell: float = 1.0        # kích thước ô lưới xy để ước lượng mặt đất
    ground_h_thresh: float = 0.25   # điểm cao hơn mặt đất ô của nó quá ngưỡng → foreground
    eps: float = 0.8                # DBSCAN: bán kính láng giềng (m)
    min_samples: int = 4            # DBSCAN: số điểm tối thiểu
    min_cluster_points: int = 5     # cluster nhỏ hơn bị bỏ (cluster <10 điểm không ổn định — phản biện domain)


@dataclass
class DetectorConfig:
    backend: str = "heuristic"   # heuristic | mmdet3d | openpcdet
    config_path: str = ""        # config của model (mmdet3d/openpcdet)
    checkpoint: str = ""         # file .pth trọng số PointPillars
    score_thresh: float = 0.25
    device: str = "cuda:0"


@dataclass
class ModelConfig:
    """Cách dùng model (quyết định 10/10: "Cả hai").

    - mode="frozen" (LÕI, mặc định): checkpoint PointPillars công khai, chỉ inference.
      provenance="nuscenes_train" → V/T chỉ lấy scene model chưa thấy (val / mini_val).
    - mode="seed" (TUỲ CHỌN, bước 0): tự train PointPillars trên tập Seed có nhãn
      (scripts/train_seed.py); provenance="seed"; frame Seed bị loại khỏi V/T qua ledger.
    - retrain=True (TUỲ CHỌN, công tắc công ty): frame đã chọn + gán nhãn được thêm vào Seed
      → train lại → vòng mới. AP downstream CHỈ báo khi công tắc này bật.
    - explore_frac: phương án B — tỉ lệ frame NGẪU NHIÊN (ngoài top-B) cũng gán nhãn và thêm
      vào train, giữ phân phối chung (chỉ có ý nghĩa khi retrain=True).
    """
    mode: str = "frozen"                 # frozen | seed
    provenance: str = "nuscenes_train"   # nuscenes_train | seed | external
    seed_manifest: str = ""              # seed_manifest.json (danh sách fid/scene của Seed)
    retrain: bool = False
    explore_frac: float = 0.0


@dataclass
class TTAConfig:
    enabled: bool = True
    rots_deg: Tuple[float, ...] = (0.0, 15.0, -15.0, 0.0)  # pass đầu (0, flip=False) là canonical
    flips: Tuple[bool, ...] = (False, True)
    jitter_std: float = 0.0     # nhiễu điểm mỗi pass (m); 0 = tắt cho nhanh
    match_radius: float = 1.5   # ghép detection TTA về cluster canonical (m)


@dataclass
class ObjectScoreConfig:
    # Trọng số tổng hợp rank (đều = biến thể label-free; tune="rule_v" sẽ ghi đè)
    w_shape: float = 0.35
    w_unc: float = 0.15      # PHẢN BIỆN: rareness ≠ uncertainty → trọng số thấp
    w_slice: float = 0.30
    w_vru: float = 0.20
    hard_boost: float = 0.05  # cộng mỗi cờ cứng (far/few/confusion) sau rank-agg
    far_m: float = 30.0       # đề bài: vật xa >30 m
    few_points: int = 10      # đề bài: <10 điểm LiDAR
    # Phạm vi luật xa/ít điểm trong ĐÁP ÁN (M6): "vru" = chỉ pedestrian/bicycle/motorcycle
    # (đề là bài toán VRU cho AEB). "all" = mọi lớp — trên nuScenes mini 404/404 frame
    # thành "hiếm" (base rate 100%), đánh giá mất ý nghĩa. Đổi phải khai báo trong báo cáo.
    far_few_scope: str = "vru"
    min_pts_shape: int = 10   # dưới ngưỡng này hình học không ổn định → hạ s_vru/s_shape
    vru_h: Tuple[float, float] = (0.6, 2.0)   # nới thấp để bắt trẻ em/người ngồi (phản biện domain)
    vru_w: float = 1.2
    # Prior đóng băng a-priori (cặp nhầm đã công bố trên nuScenes) — không học từ dữ liệu
    confusing_pairs: Tuple[Tuple[str, str], ...] = (
        ("pedestrian", "bicycle"), ("bicycle", "motorcycle"),
        ("pedestrian", "motorcycle"), ("traffic_cone", "pedestrian"),
        ("bicycle", "pedestrian"), ("motorcycle", "bicycle"),
    )


@dataclass
class FrameScoreConfig:
    w_obj: float = 0.50
    w_crowd: float = 0.25
    w_weather: float = 0.25
    # Phương án chốt 10/10: OOD chỉ gắn cờ, KHÔNG cộng vào điểm chọn (ngoại lai cũng "lạ").
    # Đặt > 0 chỉ để làm ablation, phải khai báo trong báo cáo.
    w_ood: float = 0.0
    hard_boost: float = 0.06   # cộng mỗi cờ cứng (đông/đêm/mưa) sau rank-agg
    crowd_n: int = 5           # đề bài: đông người ≥5
    crowd_h: Tuple[float, float] = (1.2, 2.0)
    topk: int = 5              # mean-top-k điểm vật thể trong frame
    ood_ref: str = "comfort"   # comfort | pool — tập tham chiếu OOD (fit trên V, phản biện)


@dataclass
class GateConfig:
    """Cổng lọc NGOẠI LAI (Phương án chốt 10/10, bước 2) — xem outlier_gate.py."""
    enabled: bool = True
    # phép 1 — hợp lệ dữ liệu
    min_points_abs: int = 1000
    min_points_rel: float = 0.25        # < 25% số điểm trung vị của pool → lỗi
    max_below_ground: float = 0.05      # > 5% điểm thấp hơn mặt đường 1 m → lỗi calib/phản xạ
    max_dt_factor: float = 5.0          # Δt > 5× trung vị (hoặc ≤ 0) → timestamp lỗi
    # phép 2 — nhất quán thời gian
    temporal_radius_m: float = 1.5      # + quãng vật tự di chuyển (hoặc + độ dịch ego nếu thiếu pose)
    temporal_max_speed: float = 3.0     # m/s — xe đạp chậm; dùng khi có sensor_pose toàn cục
    cell_m: float = 0.5                 # ô lưới BEV toàn cục của điểm foreground (đối chiếu theo điểm)
    temporal_min_objs: int = 3
    temporal_min_unsupported: int = 2
    temporal_min_support: float = 0.6
    # Đo trên nuScenes mini: frame thật có nhiều cụm "giống VRU" (cây, cột) nên tỉ lệ có mặt lại
    # luôn cao; thêm điều kiện số vật KHÔNG có mặt lại vượt phân vị này của V.
    temporal_q: float = 0.99
    # phép 3 — hình học / ngữ nghĩa
    max_float_m: float = 1.0            # đáy vật giống VRU cao hơn mặt đất CỤC BỘ > 1 m → lơ lửng
    ground_radius_m: float = 3.0        # bán kính lấy mặt đất cục bộ quanh vật (p5 của z)
    vru_h_range: Tuple[float, float] = (0.4, 2.6)
    vru_max_len: float = 3.0
    geometry_min_bad: int = 2
    # Ngưỡng hiệu chỉnh trên V: chỉ trượt khi số vật sai hình học vượt phân vị này của V.
    # Đo trên nuScenes mini: tán cây/biển báo làm ~50% box "VRU" của detector giả lập lơ lửng,
    # nên ngưỡng tuyệt đối loại gần hết frame thật. Ngưỡng theo V giữ phép thử có nghĩa.
    geometry_q: float = 0.99
    # phép 4 — còn hàng xóm
    knn_k: int = 5
    knn_q_out: float = 0.999            # cô lập hơn p99.9 của V → trượt
    knn_q_near: float = 0.99            # giữa p99 và p99.9 → sát ngưỡng → Nghi ngờ
    domain_shift_frac: float = 0.3
    # nhóm Nghi ngờ: "review" = không chọn, đưa vào review_T.csv; "include" = vẫn cho chọn
    suspect_policy: str = "review"
    # kiểm chứng bằng lỗi giả trên V
    corruption_test_n: int = 20
    # OOD chỉ gắn CỜ (không cộng điểm): cờ bật khi ood_raw > phân vị này của V
    ood_flag_q: float = 0.95


@dataclass
class DedupConfig:
    window_s: float = 2.0      # cùng scene, |Δt| < 2 s
    disp_m: float = 2.0        # HOẶC ego dịch < 2 m (bền với frame rate khác nhau)
    keep_topk: int = 2         # PHẢN BIỆN: giữ top-k (không chỉ 1) mỗi nhóm


@dataclass
class DiversityConfig:
    enabled: bool = True
    quotas: Dict[str, float] = field(default_factory=lambda: {
        "rare_class": 0.30, "crowd": 0.20, "night": 0.15,
        "rain": 0.15, "far_few": 0.20, "typical": 0.10,
    })


@dataclass
class SplitConfig:
    val_frac: float = 0.2
    seed: int = 0


@dataclass
class EvalConfig:
    budgets: Tuple[int, ...] = (50, 100, 150)
    iou_thresh: float = 0.5
    n_seeds: int = 10
    bootstrap: int = 100


@dataclass
class PipelineConfig:
    roi: ROIConfig = field(default_factory=ROIConfig)
    cluster: ClusterConfig = field(default_factory=ClusterConfig)
    detector: DetectorConfig = field(default_factory=DetectorConfig)
    model: ModelConfig = field(default_factory=ModelConfig)
    tta: TTAConfig = field(default_factory=TTAConfig)
    obj: ObjectScoreConfig = field(default_factory=ObjectScoreConfig)
    frame: FrameScoreConfig = field(default_factory=FrameScoreConfig)
    gate: GateConfig = field(default_factory=GateConfig)
    dedup: DedupConfig = field(default_factory=DedupConfig)
    diversity: DiversityConfig = field(default_factory=DiversityConfig)
    split: SplitConfig = field(default_factory=SplitConfig)
    evalcfg: EvalConfig = field(default_factory=EvalConfig)
    out_dir: str = "outputs"

    def to_dict(self) -> dict:
        return asdict(self)

    def save_json(self, path: str) -> None:
        with open(path, "w", encoding="utf-8") as f:
            json.dump(self.to_dict(), f, ensure_ascii=False, indent=2)

    @staticmethod
    def from_json(path: str) -> "PipelineConfig":
        """Ghi đè tham số từ JSON phẳng lồng 1 cấp, ví dụ:
        {"roi": {"max_range": 60.0}, "frame": {"crowd_n": 4}}"""
        cfg = PipelineConfig()
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        for k, v in data.items():
            if not hasattr(cfg, k):
                continue
            cur = getattr(cfg, k)
            if is_dataclass(cur) and isinstance(v, dict):
                for kk, vv in v.items():
                    if hasattr(cur, kk):
                        setattr(cur, kk, vv)
            else:
                setattr(cfg, k, v)
        return cfg
