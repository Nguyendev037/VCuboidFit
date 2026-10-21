import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { GET, POST } from "./[...path]/route";

const ctx = (path: string[]) => ({ params: Promise.resolve({ path }) });
let fetchMock: ReturnType<typeof vi.fn>;

beforeEach(() => {
  process.env.WORKER_URL = "http://worker.test:8001";
  fetchMock = vi.fn().mockResolvedValue(new Response("{}", { headers: { "content-type": "application/json" } }));
  vi.stubGlobal("fetch", fetchMock);
});
afterEach(() => {
  vi.unstubAllGlobals();
  delete process.env.WORKER_URL;
});

describe("GPU agent queue through the API proxy", () => {
  it("forwards /remote/t1/next with the agent token", async () => {
    const res = await GET(
      new Request("http://x/api/remote/t1/next", { headers: { authorization: "Bearer t" } }),
      ctx(["remote", "t1", "next"]));
    expect(res.status).toBe(200);
    const [url, init] = fetchMock.mock.calls[0];
    expect(url).toBe("http://worker.test:8001/remote/t1/next");
    expect(init.headers.authorization).toBe("Bearer t");
  });

  it("buffers a multipart result upload so the worker gets a Content-Length", async () => {
    const form = new FormData();
    form.append("signals", new Blob([new Uint8Array([1, 2, 3])]), "signals.parquet");
    await POST(
      new Request("http://x/api/remote/t1/abc/result", { method: "POST", body: form, headers: { "x-lease-id": "L" } }),
      ctx(["remote", "t1", "abc", "result"]));
    const [url, init] = fetchMock.mock.calls[0];
    expect(url).toBe("http://worker.test:8001/remote/t1/abc/result");
    expect(init.duplex).toBeUndefined();
    expect(init.body).toBeInstanceOf(ArrayBuffer);
    expect((init.body as ArrayBuffer).byteLength).toBeGreaterThan(3);
    expect(init.headers["x-lease-id"]).toBe("L");
    expect(init.headers["content-type"]).toMatch(/^multipart\/form-data; boundary=/);
  });
});
