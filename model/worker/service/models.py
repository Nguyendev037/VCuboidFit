"""Hợp đồng API (spec tổng §4.2). JSON camelCase, Python snake_case."""
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field
from pydantic.alias_generators import to_camel

from c4.lidar.params import LidarParams
from c4.params import SelectParams

Cam = Literal["CAM_FRONT", "CAM_FRONT_LEFT", "CAM_FRONT_RIGHT",
              "CAM_BACK", "CAM_BACK_LEFT", "CAM_BACK_RIGHT"]
Pipeline = Literal["lidar", "camera"]
Stage = Literal["index", "dino", "det", "clip", "merge", "lidar_index", "t0", "t1", "camera"]
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
    engine_version: str | None = None
    profile: Literal["lidar_only", "multisensor"] | None = None
    strategy: Literal["balanced", "vru_priority", "diversity"] | None = None
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


class GateSummary(ApiModel):
    valid: int
    suspect: int
    outlier: int


class TagSummary(ApiModel):
    R1: int = Field(alias="R1")
    R2: int = Field(alias="R2")
    R3: int = Field(alias="R3")
    H: int = Field(alias="H")
    C: int = Field(alias="C")
    I: int = Field(alias="I")


class ContextSummary(ApiModel):
    night: int
    glare: int
    rain: int
    review: int


class ContextCam(ApiModel):
    tags: list[str]
    probs: dict[str, dict[str, float]]
    cv_flags: list[str]
    review: bool
    review_reasons: list[str]


class FrameContext(ApiModel):
    per_cam: dict[str, ContextCam]
    sun_elev_deg: float | None = None


class ReviewItem(ApiModel):
    sample_token: str
    cam: str
    review_reasons: list[str]


class ReviewQueue(ApiModel):
    items: list[ReviewItem]


class RareObject(BaseModel):
    """Columns of rare_objects, preserving the table contract's field names."""
    sample_token: str
    object_id: str
    source: Literal["cluster", "pointpillars", "merged"]
    cls_pred: str
    cx: float
    cy: float
    cz: float
    l: float
    w: float
    h: float
    yaw: float
    pts: int
    dist_m: float
    track_id: str
    speed_mps: float | None
    score_shape: float
    score_slice: float
    score_vru: float
    score_unc: float
    r_sem: float | None
    concept_top: str | None
    concept_score: float | None
    s_obj: float
    missed_by_model: bool
    reasons: str


PredTag = Literal["R1", "R2", "R3", "H", "C", "I"]
ReasonCode = Literal["slice", "vru", "shape", "unc", "sem", "concept", "none"]
ObjClass = Literal["pedestrian", "bicycle", "motorcycle", "vru_unknown", "other"]
EvalAxis = Literal["r1_class", "r2_combo", "r3_behavior", "i_conflict", "h_hard"]


class RareSelectedSummary(ApiModel):
    frames: int
    scenes: int
    objects: int
    vru: int
    tagged_rare: int


class RarePoolSummary(RareSelectedSummary):
    eligible: int


class RareTagRate(ApiModel):
    tag: PredTag
    selected: int
    selected_pct: float
    pool_pct: float
    lift: float | None


class RareReason(ApiModel):
    code: ReasonCode
    frames: int


class RareClassMix(ApiModel):
    cls: ObjClass
    selected: int
    pool: int


class RareDistance(ApiModel):
    edges: list[float]
    selected: list[int]
    pool: list[int]


class RareScene(ApiModel):
    scene: str
    order: int
    pool: int
    selected: int


class RareScoreHistogram(ApiModel):
    edges: list[float]
    counts: list[int]
    threshold: float


class RareEvaluationRow(ApiModel):
    key: Literal["ours", "score_only", "crowd", "random", "oracle"]
    iy: float
    iy_std: float | None
    n_instances: float
    irecall: float


class RareEvaluationAxis(ApiModel):
    axis: EvalAxis
    targets: int
    ours: int
    random_mean: float


class RareEvaluation(ApiModel):
    axis: Literal["r2_combo"]
    in_sample: Literal[True]
    B: int = Field(alias="B")
    n_targets: int
    rows: list[RareEvaluationRow]
    by_axis: list[RareEvaluationAxis]


class RareAnalysis(ApiModel):
    version: Literal[1]
    pool: RarePoolSummary
    selected: RareSelectedSummary
    tag_rates: list[RareTagRate]
    reasons: list[RareReason]
    class_mix: list[RareClassMix]
    distance: RareDistance
    scenes: list[RareScene]
    score_histogram: RareScoreHistogram
    evaluation: RareEvaluation | None
    evaluation_reason: Literal["ok", "no_annotations", "no_targets", "too_large", "error"]


class SelectionResult(ApiModel):
    rare_analysis: RareAnalysis | None = None
    engine_version: Literal["c4_legacy", "rare_v24"] = "c4_legacy"
    gate_summary: GateSummary | None = None
    tag_summary: TagSummary | None = None
    evaluation_available: bool = False
    warning_codes: list[str] = Field(default_factory=list)
    context_summary: ContextSummary | None = None
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
    objects: list[RareObject] = Field(default_factory=list)
    pred_tags: list[str] = Field(default_factory=list)
    context: FrameContext | None = None
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
