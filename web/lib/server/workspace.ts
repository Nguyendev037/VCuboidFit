import { promises as fs } from "node:fs";
import path from "node:path";

import { isAllowedUploadName } from "@/lib/constants";

const UPLOAD_ID_RE = /^[A-Za-z0-9_-]{8,64}$/;
const META_SUFFIX = ".meta.json";

/** WORKSPACE (tuyệt đối). Mặc định: <repo>/workspace, cạnh thư mục web/. */
export function workspaceDir(): string {
  return path.resolve(process.env.WORKSPACE || path.join(process.cwd(), "..", "workspace"));
}

export function maxUploadBytes(): number {
  const gb = Number(process.env.MAX_UPLOAD_GB);
  return (Number.isFinite(gb) && gb > 0 ? gb : 100) * 1024 ** 3;
}

export const isValidUploadId = (id: string) => UPLOAD_ID_RE.test(id);

export function uploadDir(id: string): string {
  return path.join(workspaceDir(), "uploads", id);
}

/** Đường dẫn file đích; null nếu tên không hợp lệ (traversal, tuyệt đối, đuôi lạ). */
export function uploadFilePath(id: string, name: string): string | null {
  if (!isValidUploadId(id) || !isAllowedUploadName(name) || path.basename(name) !== name) return null;
  const dir = uploadDir(id);
  const full = path.resolve(dir, name);
  return full.startsWith(dir + path.sep) ? full : null;
}

export async function uploadExists(id: string): Promise<boolean> {
  try {
    return (await fs.stat(uploadDir(id))).isDirectory();
  } catch {
    return false;
  }
}

export async function readMeta(file: string): Promise<{ size: number } | null> {
  try {
    const meta = JSON.parse(await fs.readFile(file + META_SUFFIX, "utf8"));
    return typeof meta.size === "number" ? meta : null;
  } catch {
    return null;
  }
}

export const writeMeta = (file: string, size: number) =>
  fs.writeFile(file + META_SUFFIX, JSON.stringify({ size }), "utf8");

export async function fileSize(file: string): Promise<number> {
  try {
    return (await fs.stat(file)).size;
  } catch {
    return 0;
  }
}

export interface UploadFile {
  name: string;
  size: number;
  received: number;
}

export async function listUploadFiles(id: string): Promise<UploadFile[]> {
  const dir = uploadDir(id);
  const out: UploadFile[] = [];
  for (const entry of (await fs.readdir(dir)).sort()) {
    if (!entry.endsWith(META_SUFFIX)) continue;
    const name = entry.slice(0, -META_SUFFIX.length);
    const meta = await readMeta(path.join(dir, name));
    if (meta) out.push({ name, size: meta.size, received: await fileSize(path.join(dir, name)) });
  }
  return out;
}

/** Tổng dung lượng khai báo của các file trong phiên, trừ `except`. */
export async function declaredTotal(id: string, except?: string): Promise<number> {
  return (await listUploadFiles(id)).filter((f) => f.name !== except).reduce((n, f) => n + f.size, 0);
}

const locks = new Map<string, Promise<unknown>>();
/** Tuần tự hoá các thao tác trên cùng một file (trong một tiến trình). */
export async function withLock<T>(key: string, fn: () => Promise<T>): Promise<T> {
  const prev = locks.get(key) ?? Promise.resolve();
  const run = prev.then(fn, fn);
  const tail = run.catch(() => undefined);
  locks.set(key, tail);
  try {
    return await run;
  } finally {
    if (locks.get(key) === tail) locks.delete(key);
  }
}
