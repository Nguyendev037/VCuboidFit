import React from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it } from "vitest";
import { SelectionTable } from "../SelectionTable";
import { FilterBar } from "../FilterBar";
import { rareFixture } from "./rareFixture";
import { RARE_PANELS as T } from "@/lib/glossary";
import type { SelectionResult } from "@/lib/api/types";

const result: SelectionResult = {
  engineVersion: "rare_v24", rareAnalysis: rareFixture,
  selectionId: "s1", params: {}, poolSize: 121, budgetB: 7, warnings: [], metrics: null, preview: [],
  gateSummary: { valid: 121, suspect: 3, outlier: 1 },
};
const state = {
  activePipeline: "lidar", preset: "balanced", budget: 0.05, debounced: { budget: 0.05 },
  dataset: null, items: [], job: { data: null }, jobId: "j1",
  m: null, result, selection: {}, advancedParams: null,
};
const render = (r: SelectionResult) => renderToStaticMarkup(React.createElement(SelectionTable, { ...state, result: r } as unknown as React.ComponentProps<typeof SelectionTable>));

describe("result integration", () => {
  it("rare thay thẻ cũ bằng các bảng và giữ actions/header/preview", () => {
    const html = render(result);
    expect(html).toContain(T.classes.title);
    expect(html).not.toContain('data-testid="metric-recall"');
    expect(html).toContain("Kết quả");
    expect(html).toContain("Frame tiêu biểu đã chọn");
    expect(html).toContain("121 hợp lệ · 3 đáng ngờ · 1 ngoại lệ");
    expect(html).toContain("Camera xuất ảnh");
    expect(html).toContain(T.queue);
  });
  it.each([undefined, null])("rareAnalysis %s giữ tóm tắt nhưng không vẽ số giả", rareAnalysis => {
    const html = render({ ...result, rareAnalysis });
    expect(html).not.toContain(T.classes.title);
    expect(html).toContain('data-testid="metric-selected"');
    expect(html).not.toContain("Tỉ lệ bắt frame đáng giá");
    expect(html).not.toContain("38 %");
    expect(html).not.toContain("Random trung bình 5");
  });
  it("legacy bỏ qua rareAnalysis và giữ thẻ cũ", () => {
    const html = render({ ...result, engineVersion: "c4_legacy" });
    expect(html).not.toContain(T.classes.title);
    expect(html).toContain('data-testid="metric-recall"');
  });
  it.each([
    ["done", "none", "Hiếm trong dữ liệu 29%, Lạ với model 0%, Model chưa chắc chắn 71%", true],
    ["done", "seed", "Hiếm trong dữ liệu 20%, Lạ với model 30%, Model chưa chắc chắn 50%", false],
    ["running", "none", "Hiếm trong dữ liệu 20%, Lạ với model 30%, Model chưa chắc chắn 50%", false],
  ])("công thức %s/%s chỉ chia lại khi đã done thiếu novelty", (status, novSource, formula, note) => {
    const html = renderToStaticMarkup(React.createElement(FilterBar, {
      ...state, noTier1: false, engineVersion: "rare_v24",
      paramsSchema: { data: { fields: [], tierAvailable: [0, 1], presets: { balanced: [0.2, 0.3, 0.5] } } },
      job: { data: { tier1: { state: status, novSource, reason: null, canRun: false } } },
      t1Local: {}, t1Remote: {}, t1Run: {}, queryTags: [],
    } as unknown as React.ComponentProps<typeof FilterBar>));
    expect(html).toContain(formula);
    expect(html.includes(T.noNovelty)).toBe(note);
  });
});