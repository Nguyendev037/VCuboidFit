import { errorResponse } from "@/lib/server/http";
import { workerFetch } from "@/lib/server/worker";
import { isValidUploadId, listUploadFiles, uploadExists } from "@/lib/server/workspace";

export const runtime = "nodejs";
export const dynamic = "force-dynamic";

/** Kiểm tra mọi file đã đủ byte rồi chuyển cho worker `POST /datasets` → DatasetReport. */
export async function POST(_req: Request, ctx: { params: Promise<{ id: string }> }): Promise<Response> {
  const { id } = await ctx.params;
  if (!isValidUploadId(id)) return errorResponse(400, "bad_upload_id", "Mã phiên upload không hợp lệ.");
  if (!(await uploadExists(id))) return errorResponse(404, "upload_not_found", "Không tìm thấy phiên upload.");

  const files = await listUploadFiles(id);
  if (files.length === 0) return errorResponse(409, "no_files", "Chưa có file nào được tải lên.");
  const incomplete = files.filter((f) => f.received < f.size).map((f) => f.name);
  if (incomplete.length) {
    return errorResponse(409, "upload_incomplete", `Còn file chưa tải xong: ${incomplete.join(", ")}.`, { incomplete });
  }

  const res = await workerFetch("/datasets", {
    method: "POST",
    headers: { "content-type": "application/json" },
    body: JSON.stringify({ uploadId: id }),
  });
  return new Response(await res.text(), {
    status: res.status,
    headers: { "content-type": res.headers.get("content-type") ?? "application/json" },
  });
}
