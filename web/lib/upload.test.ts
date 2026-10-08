import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { ApiError } from "@/lib/api/client";

import { formatEta, summarizeUploads, uploadFiles } from "./upload";

const CS = 1000; // chunkSize nhỏ cho test
const mkFile = (name: string, size: number, seed = 1) =>
  new File([Uint8Array.from({ length: size }, (_, i) => (i * 7 + seed) & 0xff)], name);

interface Put {
  name: string;
  start: number;
  end: number;
  total: number;
  fileSize: string | null;
  bytes: Uint8Array;
}

/** Server giả: giữ bytes theo file, kiểm offset như route thật; `script` điều khiển lỗi theo lần PUT. */
function fakeServer(opts: { initial?: Record<string, { size: number; received: number }>; script?: (n: number, p: Put) => Response | Error | undefined } = {}) {
  const files = new Map<string, { size: number; data: number[] }>();
  for (const [k, v] of Object.entries(opts.initial ?? {})) files.set(k, { size: v.size, data: new Array(v.received).fill(0) });
  const puts: Put[] = [];
  let inFlight = 0;
  let maxInFlight = 0;
  const fn = vi.fn(async (url: string, init?: RequestInit) => {
    const method = init?.method ?? "GET";
    if (method === "POST" && url === "/api/uploads") return Response.json({ uploadId: "u1" });
    if (method === "GET" && url === "/api/uploads/u1") {
      return Response.json({ files: [...files].map(([name, f]) => ({ name, size: f.size, received: f.data.length })) });
    }
    const m = /^\/api\/uploads\/u1\/files\/(.+)$/.exec(url);
    if (method === "PUT" && m) {
      inFlight++;
      maxInFlight = Math.max(maxInFlight, inFlight);
      try {
        const name = decodeURIComponent(m[1]);
        const h = new Headers(init!.headers);
        const r = /^bytes (\d+)-(\d+)\/(\d+)$/.exec(h.get("content-range") ?? "")!;
        const bytes = new Uint8Array(await (init!.body as Blob).arrayBuffer());
        const put: Put = { name, start: +r[1], end: +r[2], total: +r[3], fileSize: h.get("x-file-size"), bytes };
        puts.push(put);
        await Promise.resolve();
        const scripted = opts.script?.(puts.length, put);
        if (scripted instanceof Error) throw scripted;
        if (scripted) return scripted;
        const f = files.get(name) ?? { size: put.total, data: [] as number[] };
        files.set(name, f);
        if (put.start !== f.data.length) {
          return Response.json({ error: { code: "offset_mismatch", message: "Sai vị trí" }, received: f.data.length }, { status: 409 });
        }
        f.data.push(...bytes);
        return Response.json({ received: f.data.length, size: f.size, complete: f.data.length === f.size });
      } finally {
        inFlight--;
      }
    }
    throw new Error(`unexpected ${method} ${url}`);
  });
  return { fn, puts, files, maxInFlight: () => maxInFlight };
}

let sleeps: number[];
const sleep = vi.fn(async (ms: number) => {
  sleeps.push(ms);
});
beforeEach(() => {
  sleeps = [];
  sleep.mockClear();
  delete process.env.NEXT_PUBLIC_MOCK;
});
afterEach(() => {
  vi.unstubAllGlobals();
  delete process.env.NEXT_PUBLIC_MOCK;
});

const run = (files: File[], extra: Parameters<typeof uploadFiles>[1] extends infer O ? Partial<O> : never = {}) =>
  uploadFiles(files, { onProgress: () => {}, chunkSize: CS, sleep, ...extra });

describe("uploadFiles", () => {
  it("creates a session, sends 50 MB-style slices sequentially and reports progress", async () => {
    const srv = fakeServer();
    vi.stubGlobal("fetch", srv.fn);
    const f = mkFile("a.zip", 2500);
    const progress: [string, number, number][] = [];
    const ids: string[] = [];
    const res = await run([f], { onProgress: (n, r, t) => progress.push([n, r, t]), onUploadId: (i) => ids.push(i) });
    expect(res).toEqual({ uploadId: "u1" });
    expect(ids).toEqual(["u1"]);
    expect(srv.puts.map((p) => [p.start, p.end, p.total, p.fileSize])).toEqual([
      [0, 999, 2500, "2500"],
      [1000, 1999, 2500, "2500"],
      [2000, 2499, 2500, "2500"],
    ]);
    expect(Buffer.from(srv.files.get("a.zip")!.data).equals(Buffer.from(await f.arrayBuffer()))).toBe(true);
    expect(progress).toEqual([["a.zip", 0, 2500], ["a.zip", 1000, 2500], ["a.zip", 2000, 2500], ["a.zip", 2500, 2500]]);
    expect(srv.maxInFlight()).toBe(1);
  });

  it("uploads several files one after another", async () => {
    const srv = fakeServer();
    vi.stubGlobal("fetch", srv.fn);
    await run([mkFile("a.zip", 1500), mkFile("b.zip", 500, 3), mkFile("vcf_manifest.json", 200, 4)]);
    expect(srv.puts.map((p) => p.name)).toEqual(["a.zip", "a.zip", "b.zip", "vcf_manifest.json"]);
    expect(srv.maxInFlight()).toBe(1);
  });

  it("asks the status first and resumes from the confirmed byte", async () => {
    const srv = fakeServer({ initial: { "a.zip": { size: 2500, received: 1000 } } });
    vi.stubGlobal("fetch", srv.fn);
    const first: number[] = [];
    await run([mkFile("a.zip", 2500)], { uploadId: "u1", onProgress: (_n, r) => first.push(r) });
    expect(srv.fn.mock.calls[0][0]).toBe("/api/uploads/u1"); // không tạo phiên mới, hỏi status trước
    expect(srv.puts.map((p) => p.start)).toEqual([1000, 2000]);
    expect(first[0]).toBe(1000); // tiến độ đã khôi phục hiện ngay
  });

  it("picking an already complete file again is a no-op (ca 2)", async () => {
    const srv = fakeServer({ initial: { "a.zip": { size: 1500, received: 1500 } } });
    vi.stubGlobal("fetch", srv.fn);
    const progress: number[] = [];
    await run([mkFile("a.zip", 1500)], { uploadId: "u1", onProgress: (_n, r) => progress.push(r) });
    expect(srv.puts).toHaveLength(0);
    expect(progress).toEqual([1500]);
  });

  it("retries a failed chunk with 1 s / 2 s backoff and then succeeds", async () => {
    const srv = fakeServer({
      script: (n) => (n === 1 ? new TypeError("network") : n === 2 ? Response.json({ error: { code: "x", message: "m" } }, { status: 503 }) : undefined),
    });
    vi.stubGlobal("fetch", srv.fn);
    await run([mkFile("a.zip", 500)]);
    expect(srv.puts).toHaveLength(3);
    expect(sleeps).toEqual([1000, 2000]);
    expect(srv.files.get("a.zip")!.data).toHaveLength(500);
  });

  it("gives up after 3 retries (backoff 1/2/4 s) with the last error", async () => {
    const srv = fakeServer({ script: () => Response.json({ error: { code: "worker_down", message: "Máy chủ lỗi" } }, { status: 503 }) });
    vi.stubGlobal("fetch", srv.fn);
    const err = await run([mkFile("a.zip", 500)]).catch((e) => e);
    expect(err).toBeInstanceOf(ApiError);
    expect(err.code).toBe("worker_down");
    expect(srv.puts).toHaveLength(4);
    expect(sleeps).toEqual([1000, 2000, 4000]);
  });

  it("a 409 offset_mismatch re-syncs to `received` without burning a retry", async () => {
    const srv = fakeServer({ initial: { "a.zip": { size: 1500, received: 0 } } });
    // phiên đã có 1000 byte mà status ban đầu chưa thấy (hai tab): PUT đầu bị 409 rồi tiếp tục
    let first = true;
    const wrapped = vi.fn(async (url: string, init?: RequestInit) => {
      if (first && init?.method === "GET") {
        first = false;
        srv.files.get("a.zip")!.data.push(...new Array(1000).fill(0));
        return Response.json({ files: [{ name: "a.zip", size: 1500, received: 0 }] });
      }
      return srv.fn(url, init);
    });
    vi.stubGlobal("fetch", wrapped);
    await run([mkFile("a.zip", 1500)], { uploadId: "u1" });
    expect(srv.puts.map((p) => p.start)).toEqual([0, 1000]);
    expect(sleeps).toEqual([]);
    expect(srv.files.get("a.zip")!.data).toHaveLength(1500);
  });

  it("a non-retryable 4xx throws immediately", async () => {
    const srv = fakeServer({ script: () => Response.json({ error: { code: "bad_name", message: "Tên file không hợp lệ." } }, { status: 400 }) });
    vi.stubGlobal("fetch", srv.fn);
    const err = await run([mkFile("a.zip", 500)]).catch((e) => e);
    expect(err).toBeInstanceOf(ApiError);
    expect(err.code).toBe("bad_name");
    expect(srv.puts).toHaveLength(1);
    expect(sleeps).toEqual([]);
  });

  it("abort lets the current chunk finish, sends no further chunk, and rejects with AbortError", async () => {
    const ac = new AbortController();
    const srv = fakeServer({
      script: (n) => {
        if (n === 1) ac.abort(); // bấm "tạm dừng" khi chunk 1 đang bay
        return undefined;
      },
    });
    vi.stubGlobal("fetch", srv.fn);
    const err = await run([mkFile("a.zip", 3000)], { signal: ac.signal }).catch((e) => e);
    expect(err).toBeInstanceOf(DOMException);
    expect(err.name).toBe("AbortError");
    expect(srv.puts).toHaveLength(1);
    expect(srv.files.get("a.zip")!.data).toHaveLength(1000); // chunk đang bay vẫn xong trọn vẹn
  });

  it("an already-aborted signal does no network at all", async () => {
    const srv = fakeServer();
    vi.stubGlobal("fetch", srv.fn);
    const ac = new AbortController();
    ac.abort();
    const err = await run([mkFile("a.zip", 500)], { signal: ac.signal }).catch((e) => e);
    expect(err.name).toBe("AbortError");
    expect(srv.fn).not.toHaveBeenCalled();
  });

  it("pausing then calling again with the same uploadId continues where it stopped", async () => {
    const ac = new AbortController();
    const srv = fakeServer({ script: (n) => (n === 2 ? (ac.abort(), undefined) : undefined) });
    vi.stubGlobal("fetch", srv.fn);
    const f = mkFile("a.zip", 3500);
    let id = "";
    await run([f], { signal: ac.signal, onUploadId: (i) => (id = i) }).catch(() => {});
    expect(srv.files.get("a.zip")!.data).toHaveLength(2000);
    await run([f], { uploadId: id });
    expect(Buffer.from(srv.files.get("a.zip")!.data).subarray(2000).equals(Buffer.from(await f.arrayBuffer()).subarray(2000))).toBe(true);
    expect(srv.files.get("a.zip")!.data).toHaveLength(3500);
  });

  it("rejects bad names and empty files before touching the network", async () => {
    const srv = fakeServer();
    vi.stubGlobal("fetch", srv.fn);
    for (const f of [mkFile("evil.exe", 10), mkFile("a.zip", 0)]) {
      const err = await run([f]).catch((e) => e);
      expect(err).toBeInstanceOf(ApiError);
    }
    expect(srv.fn).not.toHaveBeenCalled();
  });

  it("mock mode simulates progress with no network", async () => {
    process.env.NEXT_PUBLIC_MOCK = "1";
    const srv = fakeServer();
    vi.stubGlobal("fetch", srv.fn);
    const progress: number[] = [];
    const res = await run([mkFile("a.zip", 2500)], { onProgress: (_n, r) => progress.push(r) });
    expect(res.uploadId).toBe("mock-upload");
    expect(progress.at(-1)).toBe(2500);
    expect(progress.length).toBeGreaterThan(2);
    expect(srv.fn).not.toHaveBeenCalled();
  });
});

describe("summarizeUploads / formatEta", () => {
  it("tổng hợp danh sách upload", () => {
    const r = summarizeUploads([
      { name: "a.zip", received: 50, total: 100 },
      { name: "b.zip", received: 0, total: 100, failed: true },
    ]);
    expect(r).toEqual({ count: 2, totalBytes: 200, receivedBytes: 50, pct: 25, failed: 1 });
    expect(summarizeUploads([]).pct).toBe(0);
  });
  it("định dạng ETA mm:ss", () => {
    expect(formatEta(75)).toBe("01:15");
    expect(formatEta(null)).toBe("đang ước tính…");
  });
});
