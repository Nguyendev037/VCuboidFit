import { existsSync } from "node:fs";
import path from "node:path";
import { execFileSync } from "node:child_process";
import { fileURLToPath } from "node:url";
import { afterEach, expect, it, vi } from "vitest";
import { SAMPLES, loadLatest } from "./LiveShowcase";
import { chooseShowcaseFrame, loadShowcaseDetail } from "./showcaseFrames";
import { listJobs, listSelections, listFrames } from "@/lib/api/client";
vi.mock("@/lib/api/client", () => ({ listJobs: vi.fn(), listSelections: vi.fn(), listFrames: vi.fn(), getFrame: vi.fn() }));
afterEach(() => { vi.restoreAllMocks(); vi.unstubAllGlobals(); vi.useRealTimers(); });

it("selects exactly the six mock-f01..06 fixtures for the offline showcase", () => {
  expect(SAMPLES.map(frame => frame.sampleToken)).toEqual(
    Array.from({ length: 6 }, (_, i) => `mock-f0${i + 1}`),
  );
});

it("uses the sample run for mock jobs without loading legacy selections", async () => {
  vi.mocked(listJobs).mockResolvedValue([{ jobId: "mock-job" }] as Awaited<ReturnType<typeof listJobs>>);
  expect(await loadLatest()).toBeNull();
  expect(listSelections).not.toHaveBeenCalled();
});

it("keeps the latest real worker job and selection", async () => {
  vi.mocked(listJobs).mockResolvedValue([{ jobId: "real", state: "done", pipeline: "lidar", lastSelectionId: "sel" }] as Awaited<ReturnType<typeof listJobs>>);
  vi.mocked(listSelections).mockResolvedValue([]);
  vi.mocked(listFrames).mockResolvedValue(SAMPLES);
  expect(await loadLatest()).toEqual({ jobId: "real", sid: "sel", frames: SAMPLES });
});

it("skips failed frames, wraps and terminates after all tokens fail", () => {
  expect(chooseShowcaseFrame(SAMPLES, 0, ["mock-f01"])?.sampleToken).toBe("mock-f02");
  expect(chooseShowcaseFrame(SAMPLES, 5, ["mock-f06"])?.sampleToken).toBe("mock-f01");
  expect(chooseShowcaseFrame(SAMPLES, 99)?.sampleToken).toBe("mock-f06");
  expect(chooseShowcaseFrame(SAMPLES, 0, SAMPLES.map(frame => frame.sampleToken))).toBeNull();
  expect(chooseShowcaseFrame([], 0)).toBeNull();
});

it("rejects failed detail and failed media so callers can advance", async () => {
  await expect(loadShowcaseDetail(() => Promise.reject(new Error("detail HTTP 500")))).rejects.toThrow("500");
  vi.stubGlobal("fetch", vi.fn().mockResolvedValue({ ok: false, status: 404 }));
  await expect(loadShowcaseDetail(() => Promise.resolve(SAMPLES[0]))).rejects.toThrow("Media HTTP 404");
});

it("accepts available media including a frame without LiDAR", async () => {
  const fetch = vi.fn().mockResolvedValue({ ok: true });
  vi.stubGlobal("fetch", fetch);
  expect(await loadShowcaseDetail(() => Promise.resolve(SAMPLES[4]))).toBe(SAMPLES[4]);
  expect(fetch).toHaveBeenCalledTimes(7);
});

it("bounds a hung frame request to eight seconds", async () => {
  vi.useFakeTimers();
  vi.spyOn(AbortSignal, "timeout").mockImplementation(ms => {
    const controller = new AbortController();
    setTimeout(() => controller.abort(), ms);
    return controller.signal;
  });
  const result = expect(loadShowcaseDetail(() => new Promise(() => {}))).rejects.toThrow("timed out");
  await vi.advanceTimersByTimeAsync(8_000);
  await result;
});

it("every landing sample asset is present and publishable on a clean clone", () => {
  const webRoot = fileURLToPath(new URL("../../", import.meta.url));
  const tracked = new Set(execFileSync("git", ["ls-files", "public/demo/showcase"], { cwd: webRoot, encoding: "utf8" }).trim().split(/\r?\n/));
  const urls = SAMPLES.flatMap(frame => [frame.thumbUrl, ...frame.cams.map(cam => cam.imageUrl), ...(frame.lidar ? [frame.lidar.url] : [])]);
  for (const url of urls) {
    expect(url).toMatch(/^\/demo\/showcase\//);
    expect(existsSync(path.join(webRoot, "public", url))).toBe(true);
    expect(tracked.has(`public${url}`)).toBe(true);
  }
});
