import React from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it } from "vitest";
import { TierStatus } from "@/components/TierStatus";
import type { JobStatus, Tier1Info } from "@/lib/api/types";
import { isAnalysisReady, isT1OnlyRunning } from "@/lib/tierStatus";

const tier0 = { state: "done", nTotal: 121, nKeep: 118, durationSec: 6.06 };
const t1 = (patch: Partial<Tier1Info>): Tier1Info => ({ state: "skipped", reason: null, canRun: true, novSource: null, ...patch });
const html = (tier1: Tier1Info) =>
  renderToStaticMarkup(React.createElement(TierStatus, { tier0, tier1, onRunTier1: () => {} }));

describe("TierStatus (plan 09 §8)", () => {
  it("thẻ Tầng 0 hiện số frame, số bị loại, thời gian và tiêu chí", () => {
    const out = html(t1({}));
    expect(out).toContain("118 / 121");
    expect(out).toContain("Bị loại (quá ít điểm)");
    expect(out).toContain("6,1 s");
    expect(out).toContain("Hiếm trong dữ liệu");
  });

  it("skipped có canRun ⇒ hiện lý do và nút chạy trên máy này", () => {
    const out = html(t1({ reason: "Lúc phân tích, máy chưa bật model Tầng 1." }));
    expect(out).toContain("Lúc phân tích, máy chưa bật model Tầng 1.");
    expect(out).toContain("Chạy Tầng 1 trên máy này");
  });

  it("failed ⇒ nút chạy lại; running ⇒ không có nút, có tiến trình", () => {
    expect(html(t1({ state: "failed", reason: "x" }))).toContain("Chạy lại Tầng 1 trên máy này");
    const running = html(t1({ state: "running" }));
    expect(running).not.toContain("trên máy này</button>");
    expect(running).toContain("Đang chạy trên GPU");
  });

  it("máy không chạy được ⇒ không có nút, gợi ý Colab; done + novSource none ⇒ cảnh báo Lạ với model", () => {
    const out = html(t1({ canRun: false, reason: "Máy này chưa có model Tầng 1." }));
    expect(out).not.toContain("Chạy Tầng 1 trên máy này");
    expect(out).toContain("Colab");
    expect(html(t1({ state: "done", novSource: "none" }))).toContain("Lạ với model chưa khả dụng");
    const ready = html(t1({ state: "ready", canRun: false }));
    expect(ready).toContain("Tầng 1 chạy cùng lúc khi phân tích");
    expect(ready).not.toContain("Colab");
  });
});

describe("isT1OnlyRunning / isAnalysisReady", () => {
  const job = (patch: Partial<JobStatus>): JobStatus => ({
    jobId: "j", state: "running", stage: "t1", pipeline: "lidar", done: 0, total: 1, etaSec: 0,
    stages: [{ name: "lidar_index", state: "done", durationSec: 1, peakVramMb: 0 }, { name: "t0", state: "done", durationSec: 1, peakVramMb: 0 }],
    ...patch,
  });
  it("chỉ còn t1 chạy ⇒ kết quả xem được; t0 chưa xong ⇒ chưa", () => {
    expect(isT1OnlyRunning(job({}))).toBe(true);
    expect(isAnalysisReady(job({}))).toBe(true);
    const early = job({ stage: "t0", stages: [{ name: "t0", state: "running", durationSec: 0, peakVramMb: 0 }] });
    expect(isAnalysisReady(early)).toBe(false);
    expect(isAnalysisReady(job({ state: "done" }))).toBe(true);
  });
});
