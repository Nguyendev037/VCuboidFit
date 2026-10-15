import { randomUUID } from "node:crypto";
import { promises as fs } from "node:fs";

import { uploadDir } from "@/lib/server/workspace";

export const runtime = "nodejs";
export const dynamic = "force-dynamic";

/** Tạo phiên upload → {uploadId}. */
export async function POST(req?: Request): Promise<Response> {
  const uploadId = randomUUID().replaceAll("-", "");
  await fs.mkdir(uploadDir(uploadId), { recursive: true });
  const sid = req?.headers.get("cookie")?.match(/(?:^|;\s*)vcf_sid=([0-9a-f]{32})(?:;|$)/)?.[1];
  if (sid) await fs.writeFile(uploadDir(uploadId) + "/session.json", JSON.stringify({ sessionId: sid }), "utf8");
  return Response.json({ uploadId });
}
