import { createReadStream, createWriteStream, promises as fs } from "node:fs";
import { Readable, Transform } from "node:stream";
import { pipeline } from "node:stream/promises";
import type { ReadableStream as NodeWebStream } from "node:stream/web";

import { CHUNK, CHUNK_SLACK } from "@/lib/constants";
import { errorResponse } from "@/lib/server/http";
import {
  declaredTotal,
  fileSize,
  isValidUploadId,
  maxUploadBytes,
  readMeta,
  uploadExists,
  uploadFilePath,
  withLock,
  writeMeta,
} from "@/lib/server/workspace";

export const runtime = "nodejs";
export const dynamic = "force-dynamic";

const RANGE_RE = /^bytes (\d+)-(\d+)\/(\d+)$/;

class LengthMismatch extends Error {}

/**
 * Một chunk ≤ 50 MB, `Content-Range: bytes start-end/total`.
 * Chunk được ghi vào `<name>.part` rồi mới nối vào `<name>` khi đã nhận ĐỦ, nên chunk đứt giữa chừng
 * không để lại byte nào trong file đích; client tiếp tục từ `received`.
 */
export async function PUT(req: Request, ctx: { params: Promise<{ id: string; name: string }> }): Promise<Response> {
  const { id, name } = await ctx.params;
  if (!isValidUploadId(id)) return errorResponse(400, "bad_upload_id", "Mã phiên upload không hợp lệ.");
  const file = uploadFilePath(id, name);
  if (!file) {
    return errorResponse(400, "bad_name", "Tên file không hợp lệ. Chỉ nhận .zip, .rar, .7z, .001… hoặc vcf_manifest.json.");
  }

  const m = RANGE_RE.exec(req.headers.get("content-range") ?? "");
  if (!m) return errorResponse(400, "bad_range", "Thiếu hoặc sai header Content-Range (bytes start-end/total).");
  const [start, end, total] = [Number(m[1]), Number(m[2]), Number(m[3])];
  const len = end - start + 1;
  if (total <= 0 || end < start || end >= total) {
    return errorResponse(400, "bad_range", "Content-Range không hợp lệ.");
  }
  const declaredSize = req.headers.get("x-file-size");
  if (declaredSize !== null && Number(declaredSize) !== total) {
    return errorResponse(400, "bad_range", "X-File-Size không khớp tổng trong Content-Range.");
  }
  if (len > CHUNK + CHUNK_SLACK) {
    return errorResponse(413, "chunk_too_large", "Mỗi lần gửi tối đa 50 MB.");
  }
  if (!(await uploadExists(id))) return errorResponse(404, "upload_not_found", "Không tìm thấy phiên upload.");

  return withLock(`${id}/${name}`, async () => {
    const meta = await readMeta(file);
    if (meta && meta.size !== total) {
      return errorResponse(409, "size_mismatch", "Đã có file cùng tên nhưng kích thước khác. Hãy đổi tên hoặc tạo phiên upload mới.");
    }
    const current = await fileSize(file);
    if (meta && current === meta.size) {
      return Response.json({ received: current, size: total, complete: true }); // đã đủ: không làm gì
    }
    if (start !== current) {
      return errorResponse(409, "offset_mismatch", "Sai vị trí byte. Hãy tiếp tục từ vị trí đã nhận.", { received: current });
    }
    if (!meta) {
      if ((await declaredTotal(id, name)) + total > maxUploadBytes()) {
        return errorResponse(413, "upload_too_large", "Tổng dung lượng upload vượt giới hạn cho phép.");
      }
      await writeMeta(file, total);
    }

    const part = `${file}.part`;
    let count = 0;
    try {
      if (!req.body) throw new LengthMismatch();
      const counter = new Transform({
        transform(chunk: Buffer, _enc, cb) {
          count += chunk.length;
          cb(count > len ? new LengthMismatch() : null, chunk);
        },
      });
      await pipeline(Readable.fromWeb(req.body as unknown as NodeWebStream), counter, createWriteStream(part));
      if (count !== len) throw new LengthMismatch();
      await pipeline(createReadStream(part), createWriteStream(file, { flags: "a" }));
    } catch (e) {
      await fs.rm(part, { force: true });
      if (e instanceof LengthMismatch) {
        return errorResponse(400, "length_mismatch", "Dung lượng chunk không khớp Content-Range.");
      }
      return errorResponse(400, "chunk_aborted", "Chunk bị ngắt giữa chừng. Hãy gửi lại từ vị trí đã nhận.");
    }
    await fs.rm(part, { force: true });
    const received = await fileSize(file);
    return Response.json({ received, size: total, complete: received === total });
  });
}
