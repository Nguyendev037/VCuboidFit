import { errorResponse } from "./http";

export const WORKER_DOWN_MESSAGE = "Không kết nối được worker xử lý. Hãy kiểm tra worker đã chạy chưa.";

export function workerUrl(): string {
  return (process.env.WORKER_URL || `http://127.0.0.1:${process.env.VCF_PORT || "8001"}`).replace(/\/+$/, "");
}

/** Gọi worker; không kết nối được ⇒ Response 503 envelope tiếng Việt (SPEC-P01 bảng lỗi). */
export async function workerFetch(path: string, init?: RequestInit): Promise<Response> {
  try {
    return await fetch(`${workerUrl()}${path}`, init);
  } catch {
    return errorResponse(503, "worker_down", WORKER_DOWN_MESSAGE);
  }
}
