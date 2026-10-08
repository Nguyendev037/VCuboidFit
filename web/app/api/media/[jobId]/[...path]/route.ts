import { createReadStream, promises as fs } from "node:fs";
import path from "node:path";
import { Readable } from "node:stream";

import { errorResponse } from "@/lib/server/http";
import { workspaceDir } from "@/lib/server/workspace";

export const runtime = "nodejs";
export const dynamic = "force-dynamic";

const IMAGE_EXT = [".webp", ".jpg", ".jpeg", ".png"];
/** Mỗi loại media chỉ phục vụ đúng các đuôi này — không bao giờ phát file json/metadata của dataset. */
// `.f16` là đường dẫn chuẩn cho point cloud: trình quản lý tải (IDM…) bắt mọi URL đuôi `.bin` /
// `application/octet-stream` như một file tải về. File trên đĩa vẫn là `<token>.bin`.
const KINDS: Record<string, string[]> = { thumbs: IMAGE_EXT, bev: IMAGE_EXT, lidar: [".f16", ".bin"], images: IMAGE_EXT };
const TYPES: Record<string, string> = {
  ".webp": "image/webp",
  ".jpg": "image/jpeg",
  ".jpeg": "image/jpeg",
  ".png": "image/png",
  ".bin": "application/octet-stream",
  ".f16": "application/x-vcf-lidar-f16",
};
const CACHE = "public, max-age=31536000, immutable";
const ID_RE = /^[A-Za-z0-9_-]{1,64}$/;

const unsafeSegment = (s: string) =>
  s === "" || s === "." || s === ".." || /[/\\:\0]/.test(s);

function parseRange(header: string, size: number): { start: number; end: number } | "invalid" {
  const m = /^bytes=(\d*)-(\d*)$/.exec(header.trim());
  if (!m || (m[1] === "" && m[2] === "")) return "invalid";
  let start: number;
  let end: number;
  if (m[1] === "") {
    const n = Number(m[2]);
    if (n === 0) return "invalid";
    start = Math.max(0, size - n);
    end = size - 1;
  } else {
    start = Number(m[1]);
    end = m[2] === "" ? size - 1 : Math.min(Number(m[2]), size - 1);
  }
  return start >= size || end < start ? "invalid" : { start, end };
}

const badPath = () => errorResponse(400, "bad_path", "Đường dẫn media không hợp lệ.");
const notFound = () => errorResponse(404, "not_found", "Không tìm thấy tệp media.");

/** `thumbs/<file>`, `lidar/<file>` trong jobs/<jobId>/media; `images/<img_path>` trong data/ của dataset của job. */
export async function GET(req: Request, ctx: { params: Promise<{ jobId: string; path: string[] }> }): Promise<Response> {
  const { jobId, path: segs } = await ctx.params;
  if (!ID_RE.test(jobId)) return badPath();
  if (segs.length < 2 || segs.some(unsafeSegment)) return badPath();
  const allowedExt = KINDS[segs[0]];
  const ext = path.extname(segs[segs.length - 1]).toLowerCase();
  if (!allowedExt || !allowedExt.includes(ext)) return badPath();

  const jobDir = path.join(workspaceDir(), "jobs", jobId);
  try {
    if (!(await fs.stat(jobDir)).isDirectory()) return notFound();
  } catch {
    return notFound();
  }

  let base: string;
  if (segs[0] === "images") {
    try {
      const job = JSON.parse(await fs.readFile(path.join(jobDir, "job.json"), "utf8"));
      const datasetId = job.datasetId ?? job.dataset_id;
      if (typeof datasetId !== "string" || !ID_RE.test(datasetId)) return notFound();
      base = path.join(workspaceDir(), "datasets", datasetId, "data");
    } catch {
      return notFound();
    }
  } else {
    base = path.join(jobDir, "media", segs[0]);
  }

  // lidar/<token>.f16 ⇒ đọc file <token>.bin
  const rel = segs[0] === "lidar" && ext === ".f16"
    ? [...segs.slice(1, -1), segs[segs.length - 1].slice(0, -4) + ".bin"]
    : segs.slice(1);
  const full = path.resolve(base, ...rel);
  if (!full.startsWith(base + path.sep)) return badPath();
  let size: number;
  try {
    // realpath chặn symlink thoát khỏi thư mục gốc
    const [realBase, realFull] = await Promise.all([fs.realpath(base), fs.realpath(full)]);
    if (!realFull.startsWith(realBase + path.sep)) return badPath();
    const st = await fs.stat(realFull);
    if (!st.isFile()) return notFound();
    size = st.size;
  } catch {
    return notFound();
  }

  const headers: Record<string, string> = {
    "content-type": TYPES[ext],
    "accept-ranges": "bytes",
    "cache-control": CACHE,
  };
  const rangeHeader = req.headers.get("range");
  let start = 0;
  let end = size - 1;
  let status = 200;
  if (rangeHeader !== null) {
    const range = parseRange(rangeHeader, size);
    if (range === "invalid") {
      return Response.json(
        { error: { code: "range_not_satisfiable", message: "Phạm vi byte yêu cầu không hợp lệ." } },
        { status: 416, headers: { "content-range": `bytes */${size}` } },
      );
    }
    ({ start, end } = range);
    status = 206;
    headers["content-range"] = `bytes ${start}-${end}/${size}`;
  }
  headers["content-length"] = String(size === 0 ? 0 : end - start + 1);
  const stream = size === 0 ? null : (Readable.toWeb(createReadStream(full, { start, end })) as unknown as ReadableStream);
  return new Response(stream, { status, headers });
}
