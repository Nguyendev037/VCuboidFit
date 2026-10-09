"""Hợp đồng API (spec tổng §4.2). JSON camelCase, Python snake_case."""
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field
from pydantic.alias_generators import to_camel

from c4.lidar.params import LidarParams
from c4.params import SelectParams

Cam = Literal["CAM_FRONT", "CAM_FRONT_LEFT", "CAM_FRONT_RIGHT",
              "CAM_BACK", "CAM_BACK_LEFT", "CAM_BACK_RIGHT"]
Pipeline = Literal["lidar", "camera"]
Stage = Literal["index", "dino", "det", "clip", "merge", "lidar_index", "t0", "t1"]
Preset = Literal["balanced", "rare_first", "hard_for_model", "safety_scenarios"]
Diversity = Literal["low", "medium", "high"]


class ApiModel(BaseModel):
    model_config = ConfigDict(alias_generator=to_camel, populate_by_name=True)


class ErrorDetail(ApiModel):
    code: str
    message: str


class ErrorBody(ApiModel):
    error: ErrorDetail


class DatasetReport(ApiModel):
    dataset_id: str
    ok: bool
    scenes: int = 0
    frames: int = 0
    images_by_cam: dict[str, int] = Field(default_factory=dict)
    has_lidar: bool = False
    has_annotations: bool = False
    version: str = ""
    errors: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)


class StageStatus(ApiModel):
    name: str
    state: str
    duration_sec: float | None = None
    peak_vram_mb: int | None = None
    reason: str | None = None  # lý do tiếng Việt khi stage `skipped`/`failed` (plan 09 D3)


class Tier1Info(ApiModel):
    """Trạng thái Tầng 1 của MỘT job (plan 09 §3): máy sẵn sàng hay chưa nằm ở params-schema."""
    state: Literal["ready", "queued", "running", "done", "skipped", "failed"]
    reason: str | None = None
    can_run: bool = False
    nov_source: Literal["seed", "none"] | None = None


class Tier0Info(ApiModel):
    """Tóm tắt Tầng 0 (hình học) của MỘT job lidar: số frame đủ điểm LiDAR, thời gian chạy."""
    state: str
    n_total: int | None = None
    n_keep: int | None = None
    duration_sec: float | None = None


class JobError(ApiModel):
    code: int | str
    message: str


class JobStatus(ApiModel):
    job_id: str
    state: Literal["queued", "running", "done", "failed", "cancelled"]
    stage: Stage | None = None
    pipeline: Pipeline | None = None
    done: int = 0
    total: int = 0
    eta_sec: float | None = None
    stages: list[StageStatus] = Field(default_factory=list)
    error: JobError | None = None
    tier0: Tier0Info | None = None  # chỉ job lidar
    tier1: Tier1Info | None = None  # chỉ job lidar


class JobSummary(ApiModel):
    job_id: str
    dataset_id: str
    pipeline: Pipeline = "camera"
    state: Literal["queued", "running", "done", "failed", "cancelled"]
    created_at: str = ""
    finished_at: str | None = None
    scenes: int = 0
    frames: int = 0
    version: str = ""
    last_selection_id: str | None = None


class JobList(ApiModel):
    items: list[JobSummary]


class SelectionInfo(ApiModel):
    selection_id: str
    params: dict = Field(default_factory=dict)
    created_at: str


class SelectionList(ApiModel):
    items: list[SelectionInfo]


class SelectParamsIn(ApiModel):
    budget: float = Field(0.05, ge=0.01, le=0.10)
    preset: Preset = "balanced"
    diversity: Diversity = "medium"
    queries: list[Annotated[str, Field(min_length=1, max_length=200)]] | None = Field(
        None, min_length=1, max_length=12)
    alpha: float | None = Field(None, ge=0, le=1)
    beta: float | None = Field(None, ge=0, le=1)
    gamma: float | None = Field(None, ge=0, le=1)
    max_per_scene: int | None = Field(None, ge=1, le=50)
    min_gap: int | None = Field(None, ge=1, le=20)
    cameras: list[Cam] | None = Field(None, min_length=1)
    min_luma: float | None = Field(None, ge=0, le=255)
    min_blur_var: float | None = Field(None, ge=0, le=1000)
    tier: Literal[0, 1] | None = None
    k: int | None = Field(None, ge=3, le=50)
    lam: float | None = Field(None, ge=0, le=1)
    quota_off: bool = False

    def to_select_params(self) -> SelectParams:
        return SelectParams(**{k: getattr(self, k) for k in SelectParams.__dataclass_fields__})

    def to_lidar_params(self) -> LidarParams:
        """01-CONTRACTS §3: preset/diversity là ánh xạ ngược khi web không gửi tham số nâng cao."""
        return LidarParams(
            budget=self.budget, preset=self.preset, diversity=self.diversity, tier=self.tier,
            k=self.k, lam=self.lam, max_per_scene=self.max_per_scene, quota_off=self.quota_off,
            alpha=self.alpha, beta=self.beta, gamma=self.gamma)


class Metrics(ApiModel):
    recall: float
    uplift: float
    precision: float
    coverage: float
    coverage_gain: float
    redundancy: float
    by_group: dict[str, float] = Field(default_factory=dict)
    n_recall: float = 0.0
    scene_recall: float = 0.0
    n_boxes: float = 0.0


class RandomMetrics(ApiModel):
    mean: Metrics
    std: Metrics


class Ci95(ApiModel):
    low: float
    high: float


class MetricsBlock(ApiModel):
    hybrid: Metrics
    random: RandomMetrics | None = None
    ablation: dict[str, Metrics] = Field(default_factory=dict)
    ci95: Ci95 | None = None


class FrameSummary(ApiModel):
    rank: int
    sample_token: str
    scene_name: str
    frame_idx: int
    best_cam: str
    thumb_url: str
    S: float = Field(alias="S")  # hợp đồng giữ chữ S hoa
    r_nov: float
    r_unc: float
    r_qry: float
    qry_best: str = ""
    reason: str = ""
    tags: list[str] = Field(default_factory=list)
    cams_available: list[Cam] = Field(default_factory=list)
    r_rar: float = 0.0      # pipeline LiDAR; mock camera cũ không có ⇒ mặc định 0
    bev_url: str = ""       # pipeline LiDAR; mock camera cũ không có ⇒ mặc định rỗng


class FramesPage(ApiModel):
    items: list[FrameSummary]
    total: int
    budget_b: int


class SelectionResult(ApiModel):
    selection_id: str
    params: dict
    pool_size: int
    budget_b: int
    warnings: list[str] = Field(default_factory=list)
    metrics: MetricsBlock | None = None
    preview: list[FrameSummary] = Field(default_factory=list)
    pipeline: Pipeline = "camera"
    tier_available: list[int] = Field(default_factory=list)


class Box2D(ApiModel):
    category: str
    corners: list[float] = Field(min_length=16, max_length=16)
    visibility: str = ""


class CamScore(ApiModel):
    nov: float
    unc: float
    qry: float
    s: float


class CamDetail(ApiModel):
    cam: Cam
    image_url: str
    width: int = 1600
    height: int = 900
    boxes: list[Box2D] = Field(default_factory=list)
    score: CamScore
    q_ok: bool


class LidarRef(ApiModel):
    url: str
    num_points: int
    format: Literal["f16-xyzi"] = "f16-xyzi"


class Box3D(ApiModel):
    category: str
    corners: list[float] = Field(min_length=24, max_length=24)


class CamPose(ApiModel):
    cam: Cam
    translation: list[float]
    rotation: list[float]
    intrinsic: list[float]


class FrameDetail(FrameSummary):
    timestamp: int
    cams: list[CamDetail] = Field(default_factory=list)
    lidar: LidarRef | None = None
    boxes3d: list[Box3D] = Field(default_factory=list, alias="boxes3d")  # hợp đồng: chữ d thường
    cam_poses: list[CamPose] = Field(default_factory=list)


class Histogram(ApiModel):
    bins: list[float]
    counts: list[int]
    budget_threshold: float


class Analysis(ApiModel):
    pool: dict
    selected: dict
    histogram: Histogram


class RemoteParams(ApiModel):
    """Tham số train Tầng 1 từ xa (01-CONTRACTS §2.1)."""
    epochs: int = Field(default=20, ge=1, le=200)
    sweeps: Literal[1, 10] = 1
    batch: int = Field(default=4, ge=1, le=16)


class RemoteTask(ApiModel):
    task_id: str
    job_id: str
    dataset_id: str
    state: Literal["queued", "leased", "done", "failed", "cancelled"]
    params: RemoteParams
    created_at: str
    leased_at: str | None = None
    lease_until: str | None = None
    attempts: int = 0
    error: str | None = None


class HeartbeatIn(ApiModel):
    stage: Literal["train", "infer"]
    progress: float = Field(ge=0, le=1)


class FailIn(ApiModel):
    error: str
