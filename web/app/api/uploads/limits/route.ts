import { promises as fs } from "node:fs";

import { maxUploadBytes, workspaceDir } from "@/lib/server/workspace";

export const runtime = "nodejs";
export const dynamic = "force-dynamic";

/** Dung lượng còn trống của ổ chứa workspace; `statfs` không hỗ trợ (Node cũ) ⇒ null, không ném. */
async function freeBytes(): Promise<number | null> {
  try {
    const stat = await fs.statfs(workspaceDir());
    return stat.bavail * stat.bsize;
  } catch {
    return null;
  }
}

/** `{maxUploadBytes, freeBytes}` để ô tải lên báo giới hạn trước khi gửi (01-CONTRACTS §4). */
export async function GET(): Promise<Response> {
  return Response.json({ maxUploadBytes: maxUploadBytes(), freeBytes: await freeBytes() });
}
