import React from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it } from "vitest";
import type { Analysis } from "@/lib/api/types";
import { AnalysisPanel } from "./AnalysisPanel";

// Bố cục pool thực tế của API rare_v24, thiếu các trường legacy.
const rareAnalysis = {
  pool: { frames: 100, scenes: 4, images: 0, imagesByCam: {}, hasLidar: true },
  selected: { scenesCovered: 2 },
  histogram: { bins: [0, 0.5, 1], counts: [80, 20], budgetThreshold: 0.5 },
} as Analysis;

describe("AnalysisPanel · phân tích đúng engine", () => {
  it("rare_v24 không render các ô legacy, vẫn giữ phân bố S", () => {
    const html = renderToStaticMarkup(React.createElement(AnalysisPanel, { analysis: rareAnalysis, pipeline: "lidar" }));
    for (const label of ["Trùng lặp", "Quá an toàn", "Dễ với model", "Không gán nhãn", "Loại bởi camera", "Giá trị cao", "Hiếm (GT)"]) {
      expect(html).not.toContain(label);
    }
    expect(html).toContain("Engine rare_v24 chấm theo vật thể; các chỉ số này dành cho engine cũ.");
    expect(html).toContain("Phân bố điểm S toàn dataset");
  });

  it("legacy kể cả toàn số 0 vẫn giữ đủ bảy ô", () => {
    const analysis: Analysis = {
      ...rareAnalysis,
      pool: { ...rareAnalysis.pool, duplicates: { frames: 0, groups: 0 }, tooSafe: 0,
        easyForModel: 0, unlabelable: { total: 0, dark: 0, blurry: 0 },
        excludedByCamera: 0, highValue: 0, rare: null },
    };
    const html = renderToStaticMarkup(React.createElement(AnalysisPanel, { analysis }));
    expect(html.match(/data-testid="metric-card-/g)).toHaveLength(7);
    expect(html).toContain("Trùng lặp");
    expect(html).toContain("Hiếm (GT)");
    expect(html).not.toContain("Engine rare_v24");
  });
});
