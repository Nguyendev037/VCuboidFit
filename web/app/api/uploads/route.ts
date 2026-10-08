import { randomUUID } from "node:crypto";
import { promises as fs } from "node:fs";

import { uploadDir } from "@/lib/server/workspace";

export const runtime = "nodejs";
export const dynamic = "force-dynamic";

/** Tạo phiên upload → {uploadId}. */
export async function POST(): Promise<Response> {
  const uploadId = randomUUID().replaceAll("-", "");
  await fs.mkdir(uploadDir(uploadId), { recursive: true });
  return Response.json({ uploadId });
}
