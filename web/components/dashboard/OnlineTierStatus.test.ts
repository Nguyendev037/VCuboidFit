import React from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it, vi } from "vitest";
import { OnlineTierStatus } from "./OnlineTierStatus";
import type { Tier1Info } from "@/lib/api/types";

const tier0 = { state: "done", nTotal: 121, nKeep: 118, durationSec: 6.06 };
const tier1: Tier1Info = { state: "failed", reason: "inference-failed", canRun: true, novSource: null };

describe("online tier card controls", () => {
  it("forwards the run callback and preserves disabled/error controls", () => {
    const onRunTier1 = vi.fn();
    const props = { tier0, tier1, onRunTier1, runBusy: true, runError: "run-request-failed" };
    const tree = OnlineTierStatus(props);
    const card = tree.props.children[1];
    expect(card.props.onRunTier1).toBe(onRunTier1);
    expect(card.props.runBusy).toBe(true);
    const html = renderToStaticMarkup(React.createElement(OnlineTierStatus, props));
    expect(html).toContain("Chạy lại Tầng 1 trên máy này");
    expect(html).toContain("disabled=\"\"");
    expect(html).toContain("run-request-failed");
    expect(html).toContain("inference-failed");
  });

  it("keeps frame, drop and duration metrics", () => {
    const html = renderToStaticMarkup(React.createElement(OnlineTierStatus, { tier0, tier1 }));
    expect(html).toContain("118 / 121");
    expect(html).toContain("Bị loại (quá ít điểm)");
    expect(html).toContain("6,1 s");
    expect(html).toContain("Hiếm trong dữ liệu");
  });

  it("keeps active progress and missing novelty signal explanations", () => {
    const render = (patch: Partial<Tier1Info>) => renderToStaticMarkup(React.createElement(OnlineTierStatus, { tier1: { ...tier1, ...patch } }));
    expect(render({ state: "running" })).toContain("Đang chạy trên GPU");
    expect(render({ state: "done", novSource: "none" })).toContain("Lạ với model chưa khả dụng");
  });
});
