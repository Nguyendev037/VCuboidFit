import { errorResponse } from "@/lib/server/http";
import { isValidUploadId, listUploadFiles, uploadExists } from "@/lib/server/workspace";

export const runtime = "nodejs";
export const dynamic = "force-dynamic";

/** {files:[{name,size,received}]} để tiếp tục upload. */
export async function GET(_req: Request, ctx: { params: Promise<{ id: string }> }): Promise<Response> {
  const { id } = await ctx.params;
  if (!isValidUploadId(id)) return errorResponse(400, "bad_upload_id", "Mã phiên upload không hợp lệ.");
  if (!(await uploadExists(id))) return errorResponse(404, "upload_not_found", "Không tìm thấy phiên upload.");
  return Response.json({ files: await listUploadFiles(id) });
}
