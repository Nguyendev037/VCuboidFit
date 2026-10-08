// Uploader trình duyệt: chunk 50 MB tuần tự, tiếp tục được, thử lại 3 lần, tạm dừng bằng AbortSignal.
import { createUpload, uploadStatus } from "@/lib/api/client";
import { ApiError, genericMessage } from "@/lib/api/errors";
import { CHUNK, isAllowedUploadName } from "@/lib/constants";

export interface UploadOptions {
  onProgress(fileName: string, received: number, total: number): void;
  /** Tạm dừng: chunk đang gửi vẫn hoàn tất, không gửi chunk tiếp theo; gọi lại để tiếp tục. */
  signal?: AbortSignal;
  /** Tiếp tục một phiên đã có (lưu `onUploadId` để tiếp tục sau khi tải lại trang). */
  uploadId?: string;
  onUploadId?(uploadId: string): void;
  /** Chỉ để test; mặc định 50 MB. */
  chunkSize?: number;
  /** Chỉ để test. */
  sleep?(ms: number, signal?: AbortSignal): Promise<void>;
}

const MAX_RETRIES = 3;
const MAX_RESYNCS = 10;
const BACKOFF_MS = [1000, 2000, 4000];

const abortError = () => new DOMException("Đã tạm dừng upload.", "AbortError");
const throwIfAborted = (signal?: AbortSignal) => {
  if (signal?.aborted) throw abortError();
};

function defaultSleep(ms: number, signal?: AbortSignal): Promise<void> {
  return new Promise((resolve, reject) => {
    if (signal?.aborted) return reject(abortError());
    const t = setTimeout(() => {
      signal?.removeEventListener("abort", onAbort);
      resolve();
    }, ms);
    const onAbort = () => {
      clearTimeout(t);
      reject(abortError());
    };
    signal?.addEventListener("abort", onAbort, { once: true });
  });
}

async function readError(res: Response): Promise<{ error: ApiError; received?: number }> {
  let body: { error?: { code?: string; message?: string }; received?: number } = {};
  try {
    body = await res.json();
  } catch {
    // không phải JSON
  }
  const e = body.error;
  const error =
    e && typeof e.code === "string" && typeof e.message === "string"
      ? new ApiError(e.code, e.message, res.status)
      : new ApiError(`http_${res.status}`, genericMessage(res.status), res.status);
  return { error, received: typeof body.received === "number" ? body.received : undefined };
}

/** Gửi một chunk, thử lại lỗi mạng/5xx. Trả về số byte server đã nhận. */
async function sendChunk(
  uploadId: string,
  file: File,
  start: number,
  end: number,
  opts: UploadOptions,
): Promise<number> {
  const sleep = opts.sleep ?? defaultSleep;
  const url = `/api/uploads/${encodeURIComponent(uploadId)}/files/${encodeURIComponent(file.name)}`;
  let lastError: ApiError | undefined;
  for (let attempt = 0; attempt <= MAX_RETRIES; attempt++) {
    if (attempt > 0) await sleep(BACKOFF_MS[attempt - 1], opts.signal);
    let res: Response;
    try {
      res = await fetch(url, {
        method: "PUT",
        headers: {
          "Content-Type": "application/octet-stream",
          "Content-Range": `bytes ${start}-${end - 1}/${file.size}`,
          "X-File-Size": String(file.size),
        },
        body: file.slice(start, end),
      });
    } catch {
      lastError = new ApiError("network", "Mất kết nối khi tải lên. Hãy kiểm tra mạng rồi thử lại.");
      continue;
    }
    if (res.ok) {
      const body = await res.json().catch(() => ({}));
      return typeof body.received === "number" ? body.received : end;
    }
    const { error, received } = await readError(res);
    if (res.status === 409 && error.code === "offset_mismatch" && received !== undefined) return received;
    if (res.status < 500) throw error; // lỗi phía người dùng: thử lại vô ích
    lastError = error;
  }
  throw lastError!;
}

async function mockUpload(files: File[], opts: UploadOptions): Promise<{ uploadId: string }> {
  const sleep = opts.sleep ?? defaultSleep;
  const uploadId = opts.uploadId ?? "mock-upload";
  opts.onUploadId?.(uploadId);
  for (const f of files) {
    for (let i = 0; i <= 5; i++) {
      throwIfAborted(opts.signal);
      opts.onProgress(f.name, Math.round((f.size * i) / 5), f.size);
      if (i < 5) await sleep(40, opts.signal);
    }
  }
  return { uploadId };
}

export async function uploadFiles(files: File[], opts: UploadOptions): Promise<{ uploadId: string }> {
  for (const f of files) {
    if (!isAllowedUploadName(f.name)) {
      throw new ApiError("bad_name", `Tên file không hợp lệ: ${f.name}. Chỉ nhận .zip, .rar, .7z, .001… hoặc vcf_manifest.json.`);
    }
    if (f.size === 0) throw new ApiError("empty_file", `File ${f.name} rỗng.`);
  }
  throwIfAborted(opts.signal);
  if (process.env.NEXT_PUBLIC_MOCK === "1") return mockUpload(files, opts);

  const chunk = opts.chunkSize ?? CHUNK;
  const uploadId = opts.uploadId ?? (await createUpload()).uploadId;
  opts.onUploadId?.(uploadId);
  const status = await uploadStatus(uploadId);
  const known = new Map(status.files.map((s) => [s.name, s]));

  for (const file of files) {
    const st = known.get(file.name);
    let received = st && st.size === file.size ? Math.min(st.received, file.size) : 0;
    opts.onProgress(file.name, received, file.size);
    let resyncs = 0;
    while (received < file.size) {
      throwIfAborted(opts.signal);
      const end = Math.min(received + chunk, file.size);
      const next = await sendChunk(uploadId, file, received, end, opts);
      if (next !== end && ++resyncs > MAX_RESYNCS) {
        throw new ApiError("resync_loop", "Máy chủ liên tục báo sai vị trí byte. Hãy tạo phiên upload mới.");
      }
      received = next;
      opts.onProgress(file.name, received, file.size);
    }
  }
  return { uploadId };
}
