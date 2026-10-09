import { errorResponse } from "@/lib/server/http";
import { workerFetch } from "@/lib/server/worker";

export const runtime = "nodejs";
export const dynamic = "force-dynamic";

/** Chỉ các tiền tố này được chuyển cho worker; mọi thứ khác 404 (upload/media/login có route riêng).
 *  `params-schema` = lược đồ theo máy khi chưa có job (plan 09 D1), chỉ GET. */
const ALLOWED_PREFIXES = new Set(["datasets", "jobs", "params-schema"]);
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
  if (!ALLOWED_PREFIXES.has(path[0]) || (path[0] === "params-schema" && (path.length > 1 || req.method !== "GET"))) {
    return errorResponse(404, "not_found", "Không tìm thấy tài nguyên được yêu cầu.");
  }

  const target = `/${path.map(encodeURIComponent).join("/")}${new URL(req.url).search}`;
  const hasBody = req.method !== "GET" && req.method !== "HEAD";
  const body = hasBody ? await req.text() : "";
  const headers: Record<string, string> = {};
  if (body) headers["content-type"] = req.headers.get("content-type") ?? "application/json";

  const res = await workerFetch(target, { method: req.method, headers, body: body || undefined });

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
