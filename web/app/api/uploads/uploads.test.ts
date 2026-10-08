// Route handlers gọi trực tiếp bằng Request thật trên WORKSPACE tạm (TESTING-ACCEPTANCE §2 ca 1, 2).
import { existsSync, mkdtempSync, readFileSync, readdirSync, rmSync, statSync } from "node:fs";
import { tmpdir } from "node:os";
import path from "node:path";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { CHUNK } from "@/lib/constants";

import { GET as getStatus } from "./[id]/route";
import { POST as finalize } from "./[id]/finalize/route";
import { PUT as putChunk } from "./[id]/files/[name]/route";
import { POST as createUpload } from "./route";

let ws: string;
beforeEach(() => {
  ws = mkdtempSync(path.join(tmpdir(), "vcf-ws-"));
  process.env.WORKSPACE = ws;
  delete process.env.MAX_UPLOAD_GB;
  process.env.WORKER_URL = "http://worker.test:8001";
});
afterEach(() => {
  vi.unstubAllGlobals();
  rmSync(ws, { recursive: true, force: true });
  delete process.env.WORKSPACE;
  delete process.env.MAX_UPLOAD_GB;
  delete process.env.WORKER_URL;
});

const bytes = (n: number, seed = 1) => Uint8Array.from({ length: n }, (_, i) => (i * 31 + seed * 17) & 0xff);

async function newUpload(): Promise<string> {
  const res = await createUpload();
  expect(res.status).toBe(200);
  const { uploadId } = await res.json();
  expect(uploadId).toMatch(/^[A-Za-z0-9_-]{8,64}$/);
  return uploadId;
}

function put(id: string, name: string, start: number, body: BodyInit, total: number, len?: number, extra: Record<string, string> = {}) {
  const n = len ?? (body as Uint8Array).byteLength;
  return putChunk(
    new Request(`http://x/api/uploads/${id}/files/${encodeURIComponent(name)}`, {
      method: "PUT",
      headers: { "content-range": `bytes ${start}-${start + n - 1}/${total}`, "x-file-size": String(total), ...extra },
      body,
      // @ts-expect-error Node fetch: body stream cần duplex
      duplex: "half",
    }),
    { params: Promise.resolve({ id, name }) },
  );
}

const status = async (id: string) =>
  (await getStatus(new Request(`http://x/api/uploads/${id}`), { params: Promise.resolve({ id }) })).json();
const dest = (id: string, name: string) => path.join(ws, "uploads", id, name);

describe("create + status", () => {
  it("POST /api/uploads creates the directory; GET lists nothing yet", async () => {
    const id = await newUpload();
    expect(statSync(path.join(ws, "uploads", id)).isDirectory()).toBe(true);
    expect(await status(id)).toEqual({ files: [] });
  });

  it("GET on an unknown upload is 404 with the envelope; a hostile id is 400", async () => {
    const r = await getStatus(new Request("http://x"), { params: Promise.resolve({ id: "abcdefgh12345678" }) });
    expect(r.status).toBe(404);
    expect((await r.json()).error.code).toBe("upload_not_found");
    const bad = await getStatus(new Request("http://x"), { params: Promise.resolve({ id: "../../etc" }) });
    expect(bad.status).toBe(400);
  });
});

describe("chunk upload", () => {
  it("two chunks assemble the exact bytes and status tracks received", async () => {
    const id = await newUpload();
    const all = bytes(1500);
    let r = await put(id, "a.zip", 0, all.slice(0, 1000), 1500);
    expect(r.status).toBe(200);
    expect((await r.json()).received).toBe(1000);
    expect((await status(id)).files).toEqual([{ name: "a.zip", size: 1500, received: 1000 }]);
    r = await put(id, "a.zip", 1000, all.slice(1000), 1500);
    expect(r.status).toBe(200);
    expect(readFileSync(dest(id, "a.zip")).equals(Buffer.from(all))).toBe(true);
    expect((await status(id)).files).toEqual([{ name: "a.zip", size: 1500, received: 1500 }]);
    expect(readdirSync(path.join(ws, "uploads", id)).some((f) => f.endsWith(".part"))).toBe(false);
  });

  it("wrong offset → 409 with the envelope and `received` so the client can continue", async () => {
    const id = await newUpload();
    await put(id, "a.zip", 0, bytes(1000), 3000);
    const r = await put(id, "a.zip", 2000, bytes(500), 3000);
    expect(r.status).toBe(409);
    const body = await r.json();
    expect(body.received).toBe(1000);
    expect(body.error.code).toBe("offset_mismatch");
    expect(statSync(dest(id, "a.zip")).size).toBe(1000);
  });

  it("first chunk not at offset 0 → 409 received 0", async () => {
    const id = await newUpload();
    const r = await put(id, "a.zip", 500, bytes(500), 1000);
    expect(r.status).toBe(409);
    expect((await r.json()).received).toBe(0);
  });

  it("a chunk whose body stream dies midway leaves the file exactly as it was (ca 1)", async () => {
    const id = await newUpload();
    const first = bytes(1000, 1);
    await put(id, "a.zip", 0, first, 3000);
    const dying = new ReadableStream<Uint8Array>({
      start(c) {
        c.enqueue(bytes(600, 2));
      },
      async pull() {
        await new Promise((r) => setTimeout(r, 40)); // để 600 byte đầu kịp xuống đĩa trước khi đứt
        throw new Error("socket hang up");
      },
    });
    const r = await put(id, "a.zip", 1000, dying, 3000, 1000);
    expect(r.status).toBe(400);
    expect((await r.json()).error.code).toBe("chunk_aborted");
    expect(readFileSync(dest(id, "a.zip")).equals(Buffer.from(first))).toBe(true);
    expect(existsSync(dest(id, "a.zip.part"))).toBe(false);
    // tiếp tục từ byte đã xác nhận
    const rest = await put(id, "a.zip", 1000, bytes(2000, 3), 3000);
    expect(rest.status).toBe(200);
    expect(statSync(dest(id, "a.zip")).size).toBe(3000);
  });

  it("body shorter than the declared Content-Range is rejected and nothing is appended", async () => {
    const id = await newUpload();
    const r = await put(id, "a.zip", 0, bytes(400), 1000, 1000);
    expect(r.status).toBe(400);
    expect(existsSync(dest(id, "a.zip"))).toBe(false);
  });

  it("re-PUT of an already complete file is 200 and changes nothing (ca 2)", async () => {
    const id = await newUpload();
    const all = bytes(800);
    await put(id, "a.zip", 0, all, 800);
    const r = await put(id, "a.zip", 0, bytes(800, 9), 800);
    expect(r.status).toBe(200);
    expect((await r.json()).received).toBe(800);
    expect(readFileSync(dest(id, "a.zip")).equals(Buffer.from(all))).toBe(true);
  });

  it("same name with a different size is 409 size_mismatch", async () => {
    const id = await newUpload();
    await put(id, "a.zip", 0, bytes(500), 1000);
    const r = await put(id, "a.zip", 500, bytes(700), 1200);
    expect(r.status).toBe(409);
    expect((await r.json()).error.code).toBe("size_mismatch");
  });

  it("rejects traversal, absolute and disallowed names with 400 and writes nothing", async () => {
    const id = await newUpload();
    for (const name of ["../../x.zip", "..\\..\\x.zip", "/etc/passwd.zip", "C:\\x.zip", "evil.exe", "a.meta.json", ""]) {
      const r = await put(id, name, 0, bytes(10), 10);
      expect(r.status, name).toBe(400);
    }
    expect(readdirSync(path.join(ws, "uploads", id))).toEqual([]);
    expect(readdirSync(ws)).toEqual(["uploads"]);
  });

  it("accepts the allowed names: .zip .rar .7z .001 and vcf_manifest.json", async () => {
    const id = await newUpload();
    for (const name of ["vcf_part_001.zip", "x (1).rar", "d.7z", "multi.002", "vcf_manifest.json", "UP.ZIP"]) {
      const r = await put(id, name, 0, bytes(10), 10);
      expect(r.status, name).toBe(200);
    }
  });

  it("chunk larger than 50 MB + 1 KB → 413 before reading the body", async () => {
    const id = await newUpload();
    const declared = CHUNK + 1025;
    const r = await put(id, "big.zip", 0, bytes(10), declared * 2, declared);
    expect(r.status).toBe(413);
    expect(existsSync(dest(id, "big.zip"))).toBe(false);
  });

  it("a chunk of exactly CHUNK + 1 KB is allowed by the limit (boundary)", async () => {
    const id = await newUpload();
    const r = await put(id, "edge.zip", 0, bytes(10), 10_000_000_000, CHUNK + 1024);
    expect(r.status).toBe(400); // qua giới hạn 413, rồi bị bắt vì thân ngắn hơn khai báo
  });

  it("total upload size is capped by MAX_UPLOAD_GB", async () => {
    process.env.MAX_UPLOAD_GB = "0.000001"; // ≈ 1073 byte
    const id = await newUpload();
    expect((await put(id, "a.zip", 0, bytes(500), 1000)).status).toBe(200);
    const r = await put(id, "b.zip", 0, bytes(500), 1000); // 1000 + 1000 > cap
    expect(r.status).toBe(413);
    expect((await r.json()).error.code).toBe("upload_too_large");
  });

  it("PUT to an unknown upload is 404", async () => {
    const r = await put("abcdefgh12345678", "a.zip", 0, bytes(10), 10);
    expect(r.status).toBe(404);
  });

  it("malformed or missing Content-Range is 400", async () => {
    const id = await newUpload();
    for (const header of [undefined, "bytes 5-2/10", "items 0-9/10", "bytes 0-9/*"]) {
      const headers: Record<string, string> = header ? { "content-range": header } : {};
      const r = await putChunk(
        new Request("http://x", {
          method: "PUT",
          headers,
          body: bytes(10),
          // @ts-expect-error Node fetch: body stream cần duplex
          duplex: "half",
        }),
        { params: Promise.resolve({ id, name: "a.zip" }) },
      );
      expect(r.status, String(header)).toBe(400);
    }
  });

  it("serialises two simultaneous chunks of the same file (no interleaved bytes)", async () => {
    const id = await newUpload();
    const all = bytes(3000);
    const [r1, r2] = await Promise.all([
      put(id, "a.zip", 0, all.slice(0, 1500), 3000),
      put(id, "a.zip", 1500, all.slice(1500), 3000),
    ]);
    // thứ tự không xác định: hoặc cả hai 200, hoặc chunk 2 bị 409 vì tới trước
    const codes = [r1.status, r2.status];
    expect(codes[0]).toBe(200);
    if (codes[1] === 409) {
      expect((await put(id, "a.zip", 1500, all.slice(1500), 3000)).status).toBe(200);
    }
    expect(readFileSync(dest(id, "a.zip")).equals(Buffer.from(all))).toBe(true);
  });
});

describe("finalize", () => {
  it("incomplete file → 409 and the worker is not called", async () => {
    const id = await newUpload();
    await put(id, "a.zip", 0, bytes(500), 1000);
    const fetchMock = vi.fn();
    vi.stubGlobal("fetch", fetchMock);
    const r = await finalize(new Request("http://x", { method: "POST" }), { params: Promise.resolve({ id }) });
    expect(r.status).toBe(409);
    expect((await r.json()).error.code).toBe("upload_incomplete");
    expect(fetchMock).not.toHaveBeenCalled();
  });

  it("no files at all → 409", async () => {
    const id = await newUpload();
    const r = await finalize(new Request("http://x", { method: "POST" }), { params: Promise.resolve({ id }) });
    expect(r.status).toBe(409);
  });

  it("complete → proxies POST {WORKER_URL}/datasets {uploadId} and returns the report", async () => {
    const id = await newUpload();
    await put(id, "a.zip", 0, bytes(500), 500);
    const report = { datasetId: "ds1", ok: true };
    const fetchMock = vi.fn().mockResolvedValue(new Response(JSON.stringify(report), { status: 200, headers: { "content-type": "application/json" } }));
    vi.stubGlobal("fetch", fetchMock);
    const r = await finalize(new Request("http://x", { method: "POST" }), { params: Promise.resolve({ id }) });
    expect(r.status).toBe(200);
    expect(await r.json()).toEqual(report);
    const [url, init] = fetchMock.mock.calls[0];
    expect(url).toBe("http://worker.test:8001/datasets");
    expect(init.method).toBe("POST");
    expect(JSON.parse(init.body)).toEqual({ uploadId: id });
  });

  it("worker unreachable → 503 worker_down envelope (Vietnamese)", async () => {
    const id = await newUpload();
    await put(id, "a.zip", 0, bytes(500), 500);
    vi.stubGlobal("fetch", vi.fn().mockRejectedValue(new TypeError("fetch failed")));
    const r = await finalize(new Request("http://x", { method: "POST" }), { params: Promise.resolve({ id }) });
    expect(r.status).toBe(503);
    expect(await r.json()).toEqual({
      error: { code: "worker_down", message: "Không kết nối được worker xử lý. Hãy kiểm tra worker đã chạy chưa." },
    });
  });
});
