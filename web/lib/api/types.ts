// TẠM: viết tay theo spec §4.2 — sẽ thay bằng bản sinh từ OpenAPI (Plan 3)
// Tên trường KHÔNG được đổi khi thay bằng bản sinh. Nguồn: planning/02_*/specs/01-CONTRACTS.md §2.

export const CAMS = [
  "CAM_FRONT_LEFT",
  "CAM_FRONT",
  "CAM_FRONT_RIGHT",
  "CAM_BACK_LEFT",
  "CAM_BACK",
  "CAM_BACK_RIGHT",
] as const;
export type Cam = (typeof CAMS)[number];

export const PRESETS = ["balanced", "rare_first", "hard_for_model", "safety_scenarios"] as const;
export type Preset = (typeof PRESETS)[number];

export const METHODS = ["hybrid", "novelty", "uncertainty", "query", "hybrid_nodiv", "random"] as const;
export type Method = (typeof METHODS)[number];
export type Pipeline = "lidar" | "camera";

/** Lỗi: mọi route trả `{error: {code, message}}`; `message` là câu tiếng Việt cho người dùng. */
export interface ApiErrorBody {
  error: { code: string; message: string };
}

// ---- Upload ----
export interface UploadFileStatus {
  name: string;
  size: number;
  received: number;
}
export interface UploadStatus {
  files: UploadFileStatus[];
}

// ---- Dataset ----
export interface DatasetReport {
  datasetId: string;
  ok: boolean;
  scenes: number;
  frames: number;
  imagesByCam: Record<Cam, number>;
  hasLidar: boolean;
  hasAnnotations: boolean;
  version: string;
  errors: string[];
  warnings: string[];
}

export interface DatasetProgress {
  uploadId: string;
  phase: "extract" | "merge" | "validate" | "done" | "error";
  done: number;
  total: number;
  unit: "bytes" | "files" | "steps";
  elapsedSec: number;
  etaSec: number | null;
  updatedAt: string;
}

// ---- Job ----
export type JobState = "queued" | "running" | "done" | "failed" | "cancelled";
export type JobStage = "index" | "dino" | "det" | "clip" | "merge" | "lidar_index" | "t0" | "t1";
export interface StageInfo {
  name: string;
  state: string;
  durationSec: number;
  peakVramMb: number;
}
export interface JobStatus {
  jobId: string;
  state: JobState;
  stage: JobStage;
  pipeline?: Pipeline;
  done: number;
  total: number;
  etaSec: number;
  stages: StageInfo[];
  error?: { code: string; message: string };
}

export interface JobSummary {
  jobId: string;
  datasetId: string;
  pipeline: Pipeline;
  state: JobState;
  createdAt: string;
  finishedAt: string | null;
  scenes: number;
  frames: number;
  version: string;
  lastSelectionId: string | null;
}

export interface SelectionInfo {
  selectionId: string;
  params: SelectParams;
  createdAt: string;
}

export interface FramesPage {
  items: FrameSummary[];
  total: number;
  budgetB: number;
}

// ---- Selection ----
export interface SelectParams {
  budget: number;
  pipeline?: Pipeline;
  preset?: Preset;
  diversity?: number | string;
  queries?: string[] | { id: string; text: string }[];
  tier?: 0 | 1 | null;
  k?: number;
  alpha?: number;
  beta?: number;
  gamma?: number;
  lam?: number;
  maxPerScene?: number | null;
  quotaOff?: boolean;
  minGap?: number;
  cameras?: Cam[];
  minLuma?: number;
  minBlurVar?: number;
  min_gap?: number;
  min_luma?: number;
  min_blur_var?: number;
  budget_max?: number;
}

export type Group = "A" | "B" | "C";
export type LidarGroup = "A" | "B" | "Bp" | "C";
export interface MetricsBlockCi {
  low: number;
  high: number;
}
export interface Metrics {
  recall: number;
  nRecall?: number;
  sceneRecall?: number;
  nBoxes?: number;
  uplift: number;
  precision: number;
  coverage: number;
  coverageGain: number;
  redundancy: number;
  /** Mock responses may place ci95 here; API responses place it on MetricsBlock. */
  ci95?: MetricsBlockCi | null;
  byGroup?: Record<Group | LidarGroup, number> | Record<string, number>;
}
export interface MetricsBlock {
  hybrid: Metrics;
  random?: { mean: Metrics; std: Metrics } | null;
  ablation?: Record<Method, Metrics> | Record<string, Metrics>;
  ci95?: MetricsBlockCi | null;
}

export interface FrameSummary {
  rank: number;
  sampleToken: string;
  sceneName: string;
  frameIdx: number;
  bestCam: Cam | string;
  thumbUrl: string;
  S: number;
  rRar?: number;
  bevUrl?: string;
  rNov: number;
  rUnc: number;
  rQry: number;
  qryBest?: string;
  reason: string;
  tags: string[];
  camsAvailable: Cam[];
}

export interface SelectionResult {
  selectionId: string;
  params: SelectParams | Record<string, unknown>;
  pipeline?: Pipeline;
  tierAvailable?: number[];
  poolSize: number;
  budgetB: number;
  warnings: string[];
  metrics: MetricsBlock | null;
  /** Frame xem trước */
  preview: FrameSummary[];
}

export interface FrameQuery {
  budget?: number;
  sort?: "rank" | "score";
  tag?: string;
  page?: number;
  pageSize?: number;
}

// ---- Frame detail ----
export interface Box2D {
  category: string;
  /** 8 hoặc 16 toạ độ góc chiếu */
  corners: number[];
  visibility?: string | number;
}
export interface CamDetail {
  cam: Cam;
  imageUrl: string;
  width?: number;
  height?: number;
  boxes: Box2D[];
  score: { nov: number; unc: number; qry: number; s: number };
  qOk: boolean;
}
export interface FrameDetail extends FrameSummary {
  timestamp: number;
  cams: CamDetail[];
  lidar: { url: string; numPoints: number; format?: "f16-xyzi" | string } | null;
  /** hệ ego; corners = 8 góc × xyz */
  boxes3d: { category: string; corners: number[] }[];
  camPoses: { cam: Cam; translation: number[]; rotation: number[]; intrinsic: number[][] }[];
}

export type ParamsFieldType = "number" | "integer" | "boolean" | "enum" | "int" | "float" | "bool";
export interface ParamsSchemaField {
  key: string;
  label: string;
  type: ParamsFieldType;
  min?: number;
  max?: number;
  step?: number;
  default?: number | boolean | string | null;
  help?: string;
  minLabel?: string;
  maxLabel?: string;
  display?: "choice" | "count" | "percent" | "toggle";
  unit?: string;
  group?: string;
  options?: ParamsSchemaOption[];
}
export interface ParamsSchemaOption {
  value: number;
  label: string;
  hint?: string;
  disabledReason?: string | null;
}
export interface ParamsSchemaGroup {
  label?: string;
  help?: string;
  basicNote?: string;
}
export interface ParamsSchema {
  fields: ParamsSchemaField[];
  tierAvailable: number[];
  groups?: Record<string, ParamsSchemaGroup>;
}

// ---- Tầng 1 chạy từ xa (Colab) — 01-CONTRACTS §2.2 ----
export type RemoteTaskState = "queued" | "leased" | "done" | "failed" | "cancelled";
export interface RemoteTask {
  taskId: string;
  jobId: string;
  datasetId: string;
  state: RemoteTaskState;
  params: { epochs: number; sweeps: number; batch: number };
  createdAt: string;
  leasedAt?: string | null;
  leaseUntil?: string | null;
  attempts: number;
  error?: string | null;
}
/** `enabled=false` ⇔ worker trả 404 `remote_disabled`; `task=null` ⇔ job chưa có việc nào. */
export interface T1RemoteStatus {
  enabled: boolean;
  task: RemoteTask | null;
}

// ---- Analysis (spec tổng §3.1 / §3.2 & worker API) ----
export interface CountPct {
  count: number;
  pct: number;
}

export interface PoolAnalysis {
  scenes: number;
  frames: number;
  images: number;
  imagesByCam: Record<Cam, number> | Record<string, number>;
  hasLidar?: boolean;
  hasAnnotations?: boolean;
  /** Trùng lặp: cos > 0.95; frames = tổng (kích thước nhóm − 1) */
  duplicates: { frames: number | CountPct; groups: number };
  /** Quá an toàn: rNov ≤ 0.3 và rQry ≤ 0.3 */
  tooSafe: number | CountPct;
  /** Dễ với model: rUnc ≤ 0.2 và có detection ≥ 0.5 */
  easyForModel?: number | CountPct;
  easy?: number | CountPct;
  /** Không gán nhãn được, tách theo lý do */
  unlabelable: {
    total: number | CountPct;
    dark: number;
    blurry: number;
    noObject?: number;
    noObjects?: number;
  };
  /** Giá trị cao: S ≥ p90 */
  highValue: number | CountPct;
  /** Bị loại bởi bộ lọc camera */
  excludedByCamera: number | CountPct;
  /** Hiếm (ground truth); null khi dataset không có nhãn */
  rare?: { total: number; A: number; B: number; C: number } | null;
  rareGt?: {
    total: number | CountPct;
    A: number | CountPct;
    B: number | CountPct;
    C: number | CountPct;
  } | null;
}
export interface SelectedAnalysis {
  metrics?: Metrics | MetricsBlock | null;
  random?: { mean: Metrics; std: Metrics } | null;
  ablation?: Record<Method, Metrics> | Record<string, Metrics> | null;
  recallByGroup?: Record<Group, number> | Record<string, number> | null;
  reasonDistribution?: { novelty: number; uncertainty: number; query: number };
  reasons?: { novelty: number; uncertainty: number; query: number };
  scenesCovered: number;
  duplicatesInSelected?: number;
  duplicatesInSelection?: number;
}
export interface Analysis {
  pool: PoolAnalysis;
  selected: SelectedAnalysis;
  histogram: { bins: number[]; counts: number[]; budgetThreshold: number };
}
