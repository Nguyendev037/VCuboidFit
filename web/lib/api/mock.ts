// Chế độ mock (NEXT_PUBLIC_MOCK=1): mỗi lời gọi client đọc đúng một file trong web/mocks/.
// Dùng import động nên không có request mạng nào — mọi trang chạy được khi không có worker.
import { ApiError } from "./errors";
import type {
  Analysis,
  DatasetReport,
  FrameDetail,
  FrameQuery,
  FramesPage,
  FrameSummary,
  JobStatus,
  JobSummary,
  ParamsSchema,
  SelectionResult,
  SelectParams,
  UploadStatus,
} from "./types";

export const MOCK_PRESETS = ["balanced", "rare_first", "hard_for_model", "safety_scenarios"] as const;
/** Token có file frame-detail-<token>.json. Bao gồm cả token cũ và token mới từ worker. */
export const MOCK_FRAME_TOKENS = [
  "scene0_f0",
  "scene0_f9",
  "scene1_f5",
  "scene1_f11",
  "scene2_f8",
  "mock-f01",
  "mock-f02",
  "mock-f03",
  "mock-f04",
  "mock-f05",
  "mock-f06",
];
export const MOCK_RUNNING_JOB_ID = "mock-running";

type Loader = () => Promise<{ default: unknown }>;
const LOADERS: Record<string, Loader> = {
  "dataset-report": () => import("@/mocks/dataset-report.json"),
  "upload-status": () => import("@/mocks/upload-status.json"),
  "job-running": () => import("@/mocks/job-running.json"),
  "job-done": () => import("@/mocks/job-done.json"),
  "selection-balanced": () => import("@/mocks/selection-balanced.json"),
  "selection-rare_first": () => import("@/mocks/selection-rare_first.json"),
  "selection-hard_for_model": () => import("@/mocks/selection-hard_for_model.json"),
  "selection-safety_scenarios": () => import("@/mocks/selection-safety_scenarios.json"),
  "selection-lidar": () => import("@/mocks/selection-lidar.json"),
  "params-schema": () => import("@/mocks/params-schema.json"),
  "frames-page1": () => import("@/mocks/frames-page1.json"),
  analysis: () => import("@/mocks/analysis.json"),
  "analysis-lidar": () => import("@/mocks/analysis-lidar.json"),
  "frame-detail-mock-f01": () => import("@/mocks/frame-detail-mock-f01.json"),
  "frame-detail-mock-f02": () => import("@/mocks/frame-detail-mock-f02.json"),
  "frame-detail-mock-f03": () => import("@/mocks/frame-detail-mock-f03.json"),
  "frame-detail-mock-f04": () => import("@/mocks/frame-detail-mock-f04.json"),
  "frame-detail-mock-f05": () => import("@/mocks/frame-detail-mock-f05.json"),
  "frame-detail-mock-f06": () => import("@/mocks/frame-detail-mock-f06.json"),
  "frame-detail-scene0_f0": () => import("@/mocks/frame-detail-scene0_f0.json"),
  "frame-detail-scene0_f9": () => import("@/mocks/frame-detail-scene0_f9.json"),
  "frame-detail-scene1_f5": () => import("@/mocks/frame-detail-scene1_f5.json"),
  "frame-detail-scene1_f11": () => import("@/mocks/frame-detail-scene1_f11.json"),
  "frame-detail-scene2_f8": () => import("@/mocks/frame-detail-scene2_f8.json"),
};

export async function loadMock<T>(name: string): Promise<T> {
  const load = LOADERS[name];
  if (!load) throw new ApiError("not_found", "Không có dữ liệu mẫu cho yêu cầu này.", 404);
  return (await load()).default as T;
}

export const mockApi = {
  listJobs: async (): Promise<JobSummary[]> => {
    const dataset = await loadMock<DatasetReport>("dataset-report");
    return [{ jobId: "mock-job", datasetId: dataset.datasetId, pipeline: dataset.hasLidar ? "lidar" : "camera", state: "done", createdAt: "", finishedAt: null, scenes: dataset.scenes, frames: dataset.frames, version: dataset.version, lastSelectionId: dataset.hasLidar ? "sel-lidar" : "sel-balanced" }];
  },
  listSelections: async (_id: string) => {
    const dataset = await loadMock<DatasetReport>("dataset-report");
    const result = await loadMock<SelectionResult>(dataset.hasLidar ? "selection-lidar" : "selection-balanced");
    return [{ selectionId: result.selectionId, params: result.params as SelectParams, createdAt: "" }];
  },
  getSelection: (_jobId: string, sid: string) => loadMock<SelectionResult>(sid.includes("lidar") ? "selection-lidar" : `selection-${sid.replace(/^sel-/, "")}`),
  createUpload: async () => ({ uploadId: "mock-upload" }),
  uploadStatus: (_id: string) => loadMock<UploadStatus>("upload-status"),
  finalizeUpload: (_id: string) => loadMock<DatasetReport>("dataset-report"),
  getDataset: (_id: string) => loadMock<DatasetReport>("dataset-report"),
  createJob: async (_datasetId: string, _pipeline?: string) => ({ jobId: "mock-job" }),
  getJob: (id: string) => loadMock<JobStatus>(id === MOCK_RUNNING_JOB_ID ? "job-running" : "job-done"),
  cancelJob: async (_id: string) => undefined,
  select: (_jobId: string, params: SelectParams) =>
    loadMock<SelectionResult>(params.pipeline === "lidar" ? "selection-lidar" : `selection-${params.preset ?? "balanced"}`),
  getParamsSchema: (_jobId: string) => loadMock<ParamsSchema>("params-schema"),
  listFrames: async (_jobId: string, _sid: string, query: FrameQuery) => {
    if ((query.page ?? 1) > 1) return [] as FrameSummary[];
    if (_sid.includes("lidar")) {
      return (await loadMock<SelectionResult>("selection-lidar")).preview;
    }
    const res = await loadMock<FramesPage | FrameSummary[]>("frames-page1");
    return Array.isArray(res) ? res : res.items;
  },
  getFrame: (_jobId: string, token: string, _sid?: string) =>
    loadMock<FrameDetail>(`frame-detail-${token}`),
  getAnalysis: (_jobId: string, _sid: string) => loadMock<Analysis>(_sid.includes("lidar") ? "analysis-lidar" : "analysis"),
};
