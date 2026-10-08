import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { DELETE, GET, POST } from "./[...path]/route";

const ctx = (path: string[]) => ({ params: Promise.resolve({ path }) });
let fetchMock: ReturnType<typeof vi.fn>;

beforeEach(() => {
  process.env.WORKER_URL = "http://worker.test:8001";
  fetchMock = vi.fn();
  vi.stubGlobal("fetch", fetchMock);
});
afterEach(() => {
  vi.unstubAllGlobals();
  delete process.env.WORKER_URL;
});

const json = (body: unknown, status = 200, headers: Record<string, string> = {}) =>
  new Response(JSON.stringify(body), { status, headers: { "content-type": "application/json", ...headers } });

describe("worker proxy", () => {
  it("forwards GET with the query string and returns the worker's status and body", async () => {
    fetchMock.mockResolvedValue(json({ jobId: "j1", state: "running" }));
    const res = await GET(new Request("http://x/api/jobs/j1?verbose=1"), ctx(["jobs", "j1"]));
    expect(res.status).toBe(200);
    expect(await res.json()).toEqual({ jobId: "j1", state: "running" });
    const [url, init] = fetchMock.mock.calls[0];
    expect(url).toBe("http://worker.test:8001/jobs/j1?verbose=1");
    expect(init.method).toBe("GET");
    expect(init.body).toBeUndefined();
  });

  it("forwards a JSON POST body and content-type", async () => {
    fetchMock.mockResolvedValue(json({ selectionId: "s1" }, 201));
    const body = { budget: 0.05, preset: "balanced", queries: ["xe máy"] };
    const res = await POST(
      new Request("http://x/api/jobs/j1/select", {
        method: "POST",
        headers: { "content-type": "application/json" },
        body: JSON.stringify(body),
      }),
      ctx(["jobs", "j1", "select"]),
    );
    expect(res.status).toBe(201);
    const [url, init] = fetchMock.mock.calls[0];
    expect(url).toBe("http://worker.test:8001/jobs/j1/select");
    expect(init.method).toBe("POST");
    expect(JSON.parse(init.body)).toEqual(body);
    expect(new Headers(init.headers).get("content-type")).toBe("application/json");
  });

  it("passes worker error statuses and envelopes through untouched", async () => {
    const env = { error: { code: "bad_params", message: "Tham số không hợp lệ." } };
    fetchMock.mockResolvedValue(json(env, 422));
    const res = await POST(new Request("http://x/api/jobs", { method: "POST", body: "{}" }), ctx(["jobs"]));
    expect(res.status).toBe(422);
    expect(await res.json()).toEqual(env);
  });

  it("forwards DELETE and datasets/**", async () => {
    fetchMock.mockResolvedValue(new Response(null, { status: 204 }));
    const res = await DELETE(new Request("http://x/api/datasets/d1", { method: "DELETE" }), ctx(["datasets", "d1"]));
    expect(res.status).toBe(204);
    expect(fetchMock.mock.calls[0][0]).toBe("http://worker.test:8001/datasets/d1");
  });

  it("worker down → 503 envelope with the Vietnamese message", async () => {
    fetchMock.mockRejectedValue(new TypeError("fetch failed"));
    const res = await GET(new Request("http://x/api/jobs/j1"), ctx(["jobs", "j1"]));
    expect(res.status).toBe(503);
    expect(await res.json()).toEqual({
      error: { code: "worker_down", message: "Không kết nối được worker xử lý. Hãy kiểm tra worker đã chạy chưa." },
    });
  });

  it("only datasets and jobs prefixes are proxied; anything else is 404 and never reaches the worker", async () => {
    for (const path of [["uploads", "x"], ["admin"], ["health"], ["media", "j", "x"], ["JOBS", "j1"]]) {
      const res = await GET(new Request("http://x/api/" + path.join("/")), ctx(path));
      expect(res.status, path.join("/")).toBe(404);
      expect((await res.json()).error.code).toBe("not_found");
    }
    expect(fetchMock).not.toHaveBeenCalled();
  });

  it("dot segments cannot escape the allowed prefix", async () => {
    for (const path of [["jobs", "..", "admin"], ["jobs", ".", "x"], ["jobs", "", "x"], ["jobs", "a/b"], ["jobs", "a\\b"]]) {
      const res = await GET(new Request("http://x/api/x"), ctx(path));
      expect(res.status, JSON.stringify(path)).toBe(400);
    }
    expect(fetchMock).not.toHaveBeenCalled();
  });

  it("streams export.csv through with its headers", async () => {
    const csv = "rank,sample_token\n1,mock-f01\n2,mock-f02\n";
    fetchMock.mockResolvedValue(
      new Response(csv, {
        status: 200,
        headers: {
          "content-type": "text/csv; charset=utf-8",
          "content-disposition": 'attachment; filename="selected_5pct.csv"',
        },
      }),
    );
    const res = await GET(
      new Request("http://x/api/jobs/j1/selections/s1/export.csv?budget=0.05"),
      ctx(["jobs", "j1", "selections", "s1", "export.csv"]),
    );
    expect(fetchMock.mock.calls[0][0]).toBe("http://worker.test:8001/jobs/j1/selections/s1/export.csv?budget=0.05");
    expect(res.headers.get("content-type")).toBe("text/csv; charset=utf-8");
    expect(res.headers.get("content-disposition")).toBe('attachment; filename="selected_5pct.csv"');
    expect(await res.text()).toBe(csv);
  });

  it("does not leak hop-by-hop headers or cookies from the worker", async () => {
    fetchMock.mockResolvedValue(json({}, 200, { connection: "keep-alive", "keep-alive": "timeout=5", "set-cookie": "w=1" }));
    const res = await GET(new Request("http://x/api/jobs/j1"), ctx(["jobs", "j1"]));
    expect(res.headers.get("connection")).toBeNull();
    expect(res.headers.get("set-cookie")).toBeNull();
  });
});
