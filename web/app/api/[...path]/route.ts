import { errorResponse } from "@/lib/server/http";
import { workerFetch } from "@/lib/server/worker";

export const runtime = "nodejs";
export const dynamic = "force-dynamic";

/** Chỉ các tiền tố này được chuyển cho worker; mọi thứ khác 404 (upload/media/login có route riêng).
 *  `params-schema` = lược đồ theo máy khi chưa có job (plan 09 D1), chỉ GET. */
/** `remote` = GPU agent pull queue (token-auth in the worker; proxy.ts skips the demo password). */
const ALLOWED_PREFIXES = new Set(["datasets", "jobs", "params-schema", "sessions", "health", "gpu", "remote"]);
/** Header của worker được trả về trình duyệt (không rò hop-by-hop, cookie…). */
const FORWARD_HEADERS = ["content-type", "content-disposition", "cache-control", "etag", "last-modified"];

const unsafeSegment = (s: string) =>
  s === "" || s === "." || s === ".." || /[/\\\0]/.test(s);

type Ctx = { params: Promise<{ path: string[] }> };

async function handle(req: Request, ctx: Ctx): Promise<Response> {
  const { path } = await ctx.params;
  if (path.some(unsafeSegment)) {
    return errorResponse(400, "bad_path", "Đường dẫn yêu cầu không hợp lệ.");
  }
  const sessionsEnabled = process.env.NEXT_PUBLIC_VCF_SESSIONS === "1";
  const prefixEnabled = ALLOWED_PREFIXES.has(path[0]) &&
    (sessionsEnabled || !["sessions", "health", "gpu"].includes(path[0]));
  const gpuAllowed = path[0] !== "gpu" || (path.length === 2 && ((path[1] === "warm" && req.method === "POST") || (path[1] === "status" && req.method === "GET")));
  if (!gpuAllowed || !prefixEnabled || (path[0] === "params-schema" && (path.length > 1 || req.method !== "GET"))) {
    return errorResponse(404, "not_found", "Không tìm thấy tài nguyên được yêu cầu.");
  }

  const target = `/${path.map(encodeURIComponent).join("/")}${new URL(req.url).search}`;
  const hasBody = req.method !== "GET" && req.method !== "HEAD";
  const contentType = req.headers.get("content-type") ?? "";
  // Buffer non-JSON bodies (GPU agent multipart result): a streamed body goes out chunked without
  // Content-Length and the worker's body_guard answers 411, so Tier 1 results never landed (2026-10-22).
  const body = hasBody
    ? contentType.includes("application/json")
      ? await req.text()
      : await req.arrayBuffer()
    : undefined;
  const headers: Record<string, string> = {};
  const sid = req.headers.get("cookie")?.match(/(?:^|;\s*)vcf_sid=([0-9a-f]{32})(?:;|$)/)?.[1];
  if (sid) headers["x-vcf-session"] = sid;
  for (const name of ["content-type", "authorization", "x-lease-id"]) {
    const value = req.headers.get(name);
    if (value) headers[name] = value;
  }

  const res = await workerFetch(target, { method: req.method, headers, body });

  const out = new Headers();
  for (const h of FORWARD_HEADERS) {
    const v = res.headers.get(h);
    if (v !== null) out.set(h, v);
  }
  return new Response(res.body, { status: res.status, headers: out });
}

export const GET = handle;
export const POST = handle;
export const PUT = handle;
export const PATCH = handle;
export const DELETE = handle;
