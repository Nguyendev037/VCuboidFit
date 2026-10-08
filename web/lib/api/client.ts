// Client API duy nhất của UI. Không gọi fetch thẳng tới worker ở nơi khác (xem 00-ARCHITECTURE §4).
// NEXT_PUBLIC_MOCK=1 ⇒ đọc web/mocks/*.json (lib/api/mock.ts).
import { ApiError, toApiError } from "./errors";
import { mockApi } from "./mock";
import type {
  Analysis,
  DatasetReport,
  FrameDetail,
  FrameQuery,
  FramesPage,
  FrameSummary,
  JobStatus,
  JobSummary,
  SelectionInfo,
  Pipeline,
  ParamsSchema,
  SelectionResult,
  SelectParams,
  UploadStatus,
} from "./types";

export { ApiError } from "./errors";

/** Chế độ dữ liệu mẫu: biến môi trường, hoặc nút "Chạy thử" trên trang chủ (sessionStorage). */
export const DEMO_KEY = "vcf-demo";
const isMock = () => {
  if (process.env.NEXT_PUBLIC_MOCK === "1") return true;
  try {
    return typeof window !== "undefined" && window.sessionStorage.getItem(DEMO_KEY) === "1";
  } catch {
    return false;
  }
};
const seg = encodeURIComponent;

async function request<T>(method: string, path: string, body?: unknown): Promise<T> {
  let res: Response;
  try {
    res = await fetch(path, {
      method,
      headers: body === undefined ? undefined : { "content-type": "application/json" },
      body: body === undefined ? undefined : JSON.stringify(body),
    });
  } catch {
    throw new ApiError("network", "Không kết nối được máy chủ. Hãy kiểm tra mạng rồi thử lại.");
  }
  if (!res.ok) throw await toApiError(res);
  const text = await res.text();
  return (text ? JSON.parse(text) : undefined) as T;
}

function query(params: Record<string, string | number | undefined>): string {
  const qs = new URLSearchParams();
  for (const [k, v] of Object.entries(params)) if (v !== undefined) qs.set(k, String(v));
  const s = qs.toString();
  return s ? `?${s}` : "";
}

export function createUpload(): Promise<{ uploadId: string }> {
  return isMock() ? mockApi.createUpload() : request("POST", "/api/uploads");
}

export function uploadStatus(id: string): Promise<UploadStatus> {
  return isMock() ? mockApi.uploadStatus(id) : request("GET", `/api/uploads/${seg(id)}`);
}

export function finalizeUpload(id: string): Promise<DatasetReport> {
  return isMock() ? mockApi.finalizeUpload(id) : request("POST", `/api/uploads/${seg(id)}/finalize`);
}

export function getDataset(id: string): Promise<DatasetReport> {
  return isMock() ? mockApi.getDataset(id) : request("GET", `/api/datasets/${seg(id)}`);
}

export function createJob(datasetId: string, pipeline?: Pipeline): Promise<{ jobId: string }> {
  return isMock()
    ? mockApi.createJob(datasetId, pipeline)
    : request("POST", "/api/jobs", { datasetId, ...(pipeline ? { pipeline } : {}) });
}

export function getJob(id: string): Promise<JobStatus> {
  return isMock() ? mockApi.getJob(id) : request("GET", `/api/jobs/${seg(id)}`);
}

export function listJobs(): Promise<JobSummary[]> {
  return isMock() ? mockApi.listJobs() : request<{ items: JobSummary[] }>("GET", "/api/jobs").then((r) => r.items);
}

export interface DeleteJobsResult {
  deleted: string[];
  skipped: { jobId: string; reason: string }[];
}

export function deleteJob(jobId: string): Promise<DeleteJobsResult> {
  return isMock()
    ? Promise.resolve({ deleted: [jobId], skipped: [] })
    : request<{ deleted: string[] }>("DELETE", `/api/jobs/${seg(jobId)}`).then((r) => ({ deleted: r.deleted, skipped: [] }));
}

export function deleteAllJobs(): Promise<DeleteJobsResult> {
  return isMock() ? Promise.resolve({ deleted: [], skipped: [] }) : request("DELETE", "/api/jobs");
}

export function listSelections(jobId: string): Promise<SelectionInfo[]> {
  return isMock() ? mockApi.listSelections(jobId) : request<{ items: SelectionInfo[] }>("GET", `/api/jobs/${seg(jobId)}/selections`).then((r) => r.items);
}

export function getSelection(jobId: string, sid: string): Promise<SelectionResult> {
  return isMock() ? mockApi.getSelection(jobId, sid) : request("GET", `/api/jobs/${seg(jobId)}/selections/${seg(sid)}`);
}

export function cancelJob(id: string): Promise<void> {
  return isMock() ? mockApi.cancelJob(id) : request("POST", `/api/jobs/${seg(id)}/cancel`);
}

export function select(jobId: string, params: SelectParams): Promise<SelectionResult> {
  if (isMock()) return mockApi.select(jobId, params);
  const apiParams = { ...params };
  delete apiParams.pipeline;
  if (typeof apiParams.diversity === "number") {
    apiParams.diversity = apiParams.diversity <= 0.35
      ? "low"
      : apiParams.diversity <= 0.65
        ? "medium"
        : "high";
  }
  return request("POST", `/api/jobs/${seg(jobId)}/select`, apiParams);
}

export function getParamsSchema(jobId: string): Promise<ParamsSchema> {
  return isMock()
    ? mockApi.getParamsSchema(jobId)
    : request("GET", `/api/jobs/${seg(jobId)}/params-schema`);
}

export function listFrames(jobId: string, sid: string, q: FrameQuery = {}): Promise<FrameSummary[]> {
  if (isMock()) return mockApi.listFrames(jobId, sid, q);
  const qs = query({ budget: q.budget, sort: q.sort, tag: q.tag, page: q.page, pageSize: q.pageSize });
  return request<FramesPage | FrameSummary[]>("GET", `/api/jobs/${seg(jobId)}/selections/${seg(sid)}/frames${qs}`).then(
    (res) => (Array.isArray(res) ? res : res.items)
  );
}

/** Selection id is passed to the worker as `sid`; the review page calls it `sel` in its URL. */
export function getFrame(jobId: string, token: string, sid?: string): Promise<FrameDetail> {
  return isMock()
    ? mockApi.getFrame(jobId, token, sid)
    : request("GET", `/api/jobs/${seg(jobId)}/frames/${seg(token)}${query({ sid })}`);
}

export function getAnalysis(jobId: string, sid: string): Promise<Analysis> {
  return isMock()
    ? mockApi.getAnalysis(jobId, sid)
    : request("GET", `/api/jobs/${seg(jobId)}/selections/${seg(sid)}/analysis`);
}

/** Đường dẫn tải selected_5pct.csv theo budget hiện tại (dùng làm href). */
export function exportUrl(jobId: string, sid: string, budget: number): string {
  return `/api/jobs/${seg(jobId)}/selections/${seg(sid)}/export.csv${query({ budget })}`;
}
