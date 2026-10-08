import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import analysis from "@/mocks/analysis.json";
import framesPage1 from "@/mocks/frames-page1.json";
import jobDone from "@/mocks/job-done.json";
import jobRunning from "@/mocks/job-running.json";
import paramsSchema from "@/mocks/params-schema.json";
import selectionRare from "@/mocks/selection-rare_first.json";
import selectionLidar from "@/mocks/selection-lidar.json";

import * as api from "./client";
import { ApiError } from "./client";
import type { FrameSummary, SelectParams } from "./types";

const PARAMS: SelectParams = {
  budget: 0.05,
  preset: "rare_first",
  diversity: 0.5,
  queries: ["người đi bộ ban đêm"],
  maxPerScene: 3,
};

function frameItems(value: typeof framesPage1): FrameSummary[] {
  return Array.isArray(value) ? value : (value as { items: FrameSummary[] }).items;
}

function jsonResponse(body: unknown, status = 200) {
  return new Response(JSON.stringify(body), {
    status,
    headers: { "content-type": "application/json" },
  });
}

let fetchMock: ReturnType<typeof vi.fn>;
beforeEach(() => {
  fetchMock = vi.fn();
  vi.stubGlobal("fetch", fetchMock);
  delete process.env.NEXT_PUBLIC_MOCK;
});
afterEach(() => {
  vi.unstubAllGlobals();
  delete process.env.NEXT_PUBLIC_MOCK;
});

describe("real mode", () => {
  it("reads persisted jobs and selections without creating a GPU job", async () => {
    fetchMock.mockResolvedValueOnce(jsonResponse({ items: [{ jobId: "j1" }] }))
      .mockResolvedValueOnce(jsonResponse({ items: [{ selectionId: "s1" }] }))
      .mockResolvedValueOnce(jsonResponse(selectionLidar));
    expect(await api.listJobs()).toEqual([{ jobId: "j1" }]);
    expect(await api.listSelections("j1")).toEqual([{ selectionId: "s1" }]);
    expect(await api.getSelection("j1", "s1")).toEqual(selectionLidar);
    expect(fetchMock.mock.calls.map(([url, init]) => [url, init.method])).toEqual([
      ["/api/jobs", "GET"], ["/api/jobs/j1/selections", "GET"], ["/api/jobs/j1/selections/s1", "GET"],
    ]);
  });
  it("select() posts the camelCase body to /api/jobs/x/select", async () => {
    fetchMock.mockResolvedValue(jsonResponse(selectionRare));
    const res = await api.select("x", PARAMS);
    expect(res.selectionId).toBe(selectionRare.selectionId);
    const [url, init] = fetchMock.mock.calls[0];
    expect(url).toBe("/api/jobs/x/select");
    expect(init.method).toBe("POST");
    expect(new Headers(init.headers).get("content-type")).toBe("application/json");
    expect(JSON.parse(init.body)).toEqual({ ...PARAMS, diversity: "medium" });
  });

  it("maps the error envelope to ApiError with the Vietnamese message", async () => {
    fetchMock.mockResolvedValue(
      jsonResponse({ error: { code: "worker_down", message: "Không kết nối được worker." } }, 503),
    );
    const err = await api.getJob("j1").catch((e) => e);
    expect(err).toBeInstanceOf(ApiError);
    expect(err.code).toBe("worker_down");
    expect(err.message).toBe("Không kết nối được worker.");
    expect(err.status).toBe(503);
  });

  it("turns a non-envelope failure (HTML 502) into a generic ApiError", async () => {
    fetchMock.mockResolvedValue(new Response("<html>bad gateway</html>", { status: 502 }));
    const err = await api.getJob("j1").catch((e) => e);
    expect(err).toBeInstanceOf(ApiError);
    expect(err.code).toBe("http_502");
    expect(err.message).toMatch(/[À-ỹ]/); // có dấu tiếng Việt
  });

  it("turns a network failure into ApiError(network)", async () => {
    fetchMock.mockRejectedValue(new TypeError("fetch failed"));
    const err = await api.getDataset("d1").catch((e) => e);
    expect(err).toBeInstanceOf(ApiError);
    expect(err.code).toBe("network");
  });

  it("builds the right URL + method for every call", async () => {
    fetchMock.mockImplementation(async () => jsonResponse({}));
    await api.createUpload();
    await api.uploadStatus("u1");
    await api.finalizeUpload("u1");
    await api.getDataset("d1");
    await api.createJob("d1");
    await api.createJob("d2", "lidar");
    await api.getJob("j1");
    await api.cancelJob("j1");
    await api.listFrames("j1", "s1", { budget: 0.05, sort: "score", tag: "Hiếm", page: 2, pageSize: 24 });
    await api.getFrame("j1", "tok", "s1");
    await api.getAnalysis("j1", "s1");
    await api.getParamsSchema("j1");
    await api.select("j1", { budget: 0.05, pipeline: "lidar", lam: 0.7, diversity: 0.5 });
    const calls = fetchMock.mock.calls.map(([u, i]) => `${i?.method ?? "GET"} ${u}`);
    expect(calls).toEqual([
      "POST /api/uploads",
      "GET /api/uploads/u1",
      "POST /api/uploads/u1/finalize",
      "GET /api/datasets/d1",
      "POST /api/jobs",
      "POST /api/jobs",
      "GET /api/jobs/j1",
      "POST /api/jobs/j1/cancel",
      "GET /api/jobs/j1/selections/s1/frames?budget=0.05&sort=score&tag=Hi%E1%BA%BFm&page=2&pageSize=24",
      "GET /api/jobs/j1/frames/tok?sid=s1",
      "GET /api/jobs/j1/selections/s1/analysis",
      "GET /api/jobs/j1/params-schema",
      "POST /api/jobs/j1/select",
    ]);
    expect(JSON.parse(fetchMock.mock.calls[4][1].body)).toEqual({ datasetId: "d1" });
    expect(JSON.parse(fetchMock.mock.calls[5][1].body)).toEqual({ datasetId: "d2", pipeline: "lidar" });
    expect(JSON.parse(fetchMock.mock.calls[12][1].body)).toEqual({ budget: 0.05, lam: 0.7, diversity: "medium" });
  });

  it("encodes path segments", async () => {
    fetchMock.mockImplementation(async () => jsonResponse({}));
    await api.getJob("a/b c");
    expect(fetchMock.mock.calls[0][0]).toBe("/api/jobs/a%2Fb%20c");
  });

  it("exportUrl points at export.csv with the current budget", () => {
    expect(api.exportUrl("j1", "s1", 0.05)).toBe("/api/jobs/j1/selections/s1/export.csv?budget=0.05");
  });
});

describe("mock mode (NEXT_PUBLIC_MOCK=1)", () => {
  beforeEach(() => {
    process.env.NEXT_PUBLIC_MOCK = "1";
  });

  it("getJob returns mocks/job-done.json and never touches the network", async () => {
    expect(await api.getJob("any")).toEqual(jobDone);
    expect(fetchMock).not.toHaveBeenCalled();
  });

  it("getJob('mock-running') returns job-running.json so UIs can show progress", async () => {
    expect(await api.getJob("mock-running")).toEqual(jobRunning);
  });

  it("select picks selection-<preset>.json", async () => {
    expect(await api.select("j", PARAMS)).toEqual(selectionRare);
  });

  it("select picks selection-lidar.json and params-schema for LiDAR mode", async () => {
    expect(await api.select("j", { ...PARAMS, pipeline: "lidar" })).toEqual(selectionLidar);
    expect(await api.getParamsSchema("j")).toEqual(paramsSchema);
  });

  it("listFrames returns page 1 and an empty page afterwards", async () => {
    const expectedFrames = frameItems(framesPage1);
    expect(await api.listFrames("j", "s", {})).toEqual(expectedFrames);
    expect(await api.listFrames("j", "s", { page: 9 })).toEqual([]);
  });

  it("getAnalysis returns analysis.json", async () => {
    expect(await api.getAnalysis("j", "s")).toEqual(analysis);
  });

  it("getFrame returns the detail for a known token and ApiError(not_found) otherwise", async () => {
    const firstFrame = frameItems(framesPage1)[0];
    const token = firstFrame.sampleToken;
    const detail = await api.getFrame("j", token, "s");
    expect(detail.sampleToken).toBe(token);
    const err = await api.getFrame("j", "nope", "s").catch((e) => e);
    expect(err).toBeInstanceOf(ApiError);
    expect(err.code).toBe("not_found");
  });

  it("upload calls resolve from mocks and no fetch happens", async () => {
    expect((await api.createUpload()).uploadId).toBeTruthy();
    expect((await api.uploadStatus("u")).files.length).toBeGreaterThan(0);
    expect((await api.finalizeUpload("u")).ok).toBe(true);
    expect((await api.getDataset("d")).datasetId).toBeTruthy();
    expect((await api.createJob("d")).jobId).toBeTruthy();
    await api.cancelJob("j");
    expect(fetchMock).not.toHaveBeenCalled();
  });
});

describe("delete history", () => {
  it("deleteJob sends DELETE and returns deleted ids", async () => {
    fetchMock.mockResolvedValueOnce(jsonResponse({ deleted: ["j1"] }));
    expect(await api.deleteJob("j1")).toEqual({ deleted: ["j1"], skipped: [] });
    expect(fetchMock.mock.calls[0][0]).toBe("/api/jobs/j1");
    expect(fetchMock.mock.calls[0][1].method).toBe("DELETE");
  });

  it("deleteJob maps 409 job_active to ApiError", async () => {
    fetchMock.mockResolvedValueOnce(
      jsonResponse({ error: { code: "job_active", message: "Lần chạy đang chạy, hãy huỷ trước khi xoá." } }, 409),
    );
    await expect(api.deleteJob("j1")).rejects.toMatchObject({ code: "job_active", status: 409 });
  });

  it("deleteAllJobs returns deleted and skipped", async () => {
    const body = { deleted: ["a"], skipped: [{ jobId: "b", reason: "active" }] };
    fetchMock.mockResolvedValueOnce(jsonResponse(body));
    expect(await api.deleteAllJobs()).toEqual(body);
    expect(fetchMock.mock.calls[0][0]).toBe("/api/jobs");
  });
});
