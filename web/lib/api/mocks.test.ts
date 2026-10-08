// Mock JSON phải khớp 01-CONTRACTS §2/§3 (tên trường cố định). Test này chặn mock lệch kiểu.
import { describe, expect, it } from "vitest";

import analysis from "@/mocks/analysis.json";
import analysisLidar from "@/mocks/analysis-lidar.json";
import datasetReport from "@/mocks/dataset-report.json";
import framesPage1 from "@/mocks/frames-page1.json";
import jobDone from "@/mocks/job-done.json";
import jobRunning from "@/mocks/job-running.json";
import paramsSchema from "@/mocks/params-schema.json";
import uploadStatus from "@/mocks/upload-status.json";

import { MOCK_FRAME_TOKENS, MOCK_PRESETS, loadMock } from "./mock";
import { CAMS } from "./types";
import type { Cam, FrameDetail, FrameSummary, SelectionResult } from "./types";

const FRAME_SUMMARY_KEYS = [
  "rank", "sampleToken", "sceneName", "frameIdx", "bestCam", "thumbUrl", "S", "rNov", "rUnc",
  "rQry", "qryBest", "reason", "tags", "camsAvailable",
];
const METRIC_KEYS = ["recall", "uplift", "precision", "coverage", "coverageGain", "redundancy", "byGroup"];

function expectKeys(obj: object, keys: string[]) {
  for (const k of keys) expect(obj, `thiếu trường ${k}`).toHaveProperty(k);
}

function frameItems(value: typeof framesPage1): FrameSummary[] {
  return Array.isArray(value) ? value : (value as { items: FrameSummary[] }).items;
}

describe("mock files match the contract", () => {
  it("dataset-report.json", () => {
    expectKeys(datasetReport, ["datasetId", "ok", "scenes", "frames", "imagesByCam", "hasLidar",
      "hasAnnotations", "version", "errors", "warnings"]);
    expect(Object.keys(datasetReport.imagesByCam).sort()).toEqual([...CAMS].sort());
  });

  it("upload-status.json", () => {
    expect(uploadStatus.files.length).toBeGreaterThan(1);
    for (const f of uploadStatus.files) expectKeys(f, ["name", "size", "received"]);
  });

  it("job-running.json / job-done.json", () => {
    for (const j of [jobRunning, jobDone]) {
      expectKeys(j, ["jobId", "state", "stage", "done", "total", "etaSec", "stages"]);
      for (const s of j.stages) expectKeys(s, ["name", "state", "durationSec", "peakVramMb"]);
    }
    expect(jobRunning.state).toBe("running");
    expect(jobDone.state).toBe("done");
    expect(jobDone.stages).toHaveLength(5);
  });

  it("selection-<preset>.json for all four presets", async () => {
    for (const preset of MOCK_PRESETS) {
      const sel = await loadMock<SelectionResult>(`selection-${preset}`);
      expectKeys(sel, ["selectionId", "params", "poolSize", "budgetB", "warnings", "metrics", "preview"]);
      expect(sel.preview.length).toBeGreaterThanOrEqual(4);
      expect(sel.metrics).not.toBeNull();
      const m = sel.metrics!;
      expectKeys(m.hybrid, METRIC_KEYS);
      expect(Object.keys(m.ablation ?? {}).sort()).toEqual(
        ["hybrid_nodiv", "novelty", "query", "uncertainty"]);
      for (const f of sel.preview) expectKeys(f, FRAME_SUMMARY_KEYS);
    }
  });

  it("params-schema.json and selection-lidar.json match the LiDAR delta", async () => {
    expect(paramsSchema.tierAvailable).toContain(0);
    for (const key of ["tier", "k", "lam", "maxPerScene", "quotaOff", "alpha", "beta", "gamma"]) {
      expect(paramsSchema.fields.some((f) => f.key === key), `thiếu field ${key}`).toBe(true);
    }
    const sel = await loadMock<SelectionResult>("selection-lidar");
    expect((sel.params as { pipeline?: string }).pipeline).toBe("lidar");
    expect(sel.tierAvailable).toContain(0);
    expectKeys(sel, ["selectionId", "params", "poolSize", "budgetB", "warnings", "metrics", "preview"]);
    expect(sel.metrics?.hybrid.nRecall).toBeGreaterThan(0);
    for (const f of sel.preview) {
      expectKeys(f, [...FRAME_SUMMARY_KEYS, "rRar", "bevUrl"]);
      expect(f.bestCam).toBe("LIDAR_TOP");
    }
  });

  it("frames-page1.json has frames with the FrameSummary fields", () => {
    const items = frameItems(framesPage1);
    expect(items.length).toBeGreaterThanOrEqual(4);
    for (const f of items) expectKeys(f, FRAME_SUMMARY_KEYS);
    expect(new Set(items.map((f) => f.sampleToken)).size).toBe(items.length);
  });

  it("analysis.json has pool, selected and histogram matching the contract", () => {
    expectKeys(analysis, ["pool", "selected", "histogram"]);
    const p = analysis.pool as typeof analysis.pool & { easy?: unknown; easyForModel?: unknown; rareGt?: unknown };
    expect(p.scenes).toBeGreaterThan(0);
    expect(p.frames).toBeGreaterThan(0);
    expect(p.images).toBeGreaterThan(0);
    expect(p.duplicates).toBeDefined();
    expect(p.tooSafe).toBeDefined();
    expect(p.easy ?? p.easyForModel).toBeDefined();
    expect(p.unlabelable).toBeDefined();
    expect(p.highValue).toBeDefined();
    expect(p.excludedByCamera).toBeDefined();
    expect(("rare" in p ? p.rare : undefined) ?? p.rareGt).toBeDefined();
    const s = analysis.selected as typeof analysis.selected & {
      reasons?: unknown;
      reasonDistribution?: unknown;
      duplicatesInSelection?: unknown;
      duplicatesInSelected?: unknown;
    };
    expect(s.scenesCovered).toBeDefined();
    expect(s.reasons ?? s.reasonDistribution).toBeDefined();
    expect(s.duplicatesInSelection ?? s.duplicatesInSelected).toBeDefined();
    expect(analysis.histogram.counts.length).toBeGreaterThanOrEqual(10);
  });

  it("analysis-lidar.json preserves the selected metrics confidence interval", () => {
    expect(analysisLidar.selected.metrics?.ci95).toEqual({ low: 0.34, high: 0.51 });
  });

  it("frame-detail: >= 5 files, one without CAM_BACK, one without LiDAR", async () => {
    expect(MOCK_FRAME_TOKENS.length).toBeGreaterThanOrEqual(5);
    const details = await Promise.all(MOCK_FRAME_TOKENS.map((t) => loadMock<FrameDetail>(`frame-detail-${t}`)));
    for (const d of details) {
      expectKeys(d, [...FRAME_SUMMARY_KEYS, "timestamp", "cams", "lidar", "boxes3d", "camPoses"]);
      if (d.cams && d.camsAvailable) {
        expect(d.cams.map((c) => c.cam).sort()).toEqual([...d.camsAvailable].sort());
        for (const c of d.cams) expectKeys(c, ["cam", "imageUrl", "score", "qOk"]);
      }
      if (d.boxes3d) {
        for (const b of d.boxes3d) expect(b.corners).toHaveLength(24);
      }
    }
    expect(details.some((d) => !d.camsAvailable?.includes("CAM_BACK" as Cam))).toBe(true);
    expect(details.some((d) => d.lidar === null)).toBe(true);
    expect(details.some((d) => d.lidar && d.lidar.format === "f16-xyzi")).toBe(true);
  });

  it("every frame in frames-page1 has a detail mock that can be opened", async () => {
    const items = frameItems(framesPage1);
    for (const f of items) {
      const detail = await loadMock<FrameDetail>(`frame-detail-${f.sampleToken}`);
      expect(detail.sampleToken).toBe(f.sampleToken);
    }
  });
});
