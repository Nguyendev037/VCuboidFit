import React from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it } from "vitest";
import { RareResultPanels } from "./RareResultPanels";
import { rareFixture } from "./rareFixture";
import { RARE_PANELS as T } from "@/lib/glossary";
import type { RareAnalysis } from "@/lib/api/types";
const render = (analysis: RareAnalysis = rareFixture) => renderToStaticMarkup(React.createElement(RareResultPanels, { analysis }));
describe("rare result panels", () => {
  it("chỉ hiện tổng quan: 4 số + một thanh ngang loại vật, không lộ mã hay số bịa", () => {
    const html = render();
    expect(html).toContain(T.classes.title);
    for (const key of ["tags", "reasons", "distance", "scenes", "scores", "evaluation"] as const) expect(html).not.toContain(T[key].title);
    for (const value of ["38 %", "R2", "slice", "pedestrian", "vru_unknown", "private-token"]) expect(html).not.toContain(value);
    expect(html).toContain("7/121");
    expect(html).toContain("Người đi bộ");
    expect(html).toContain("bg-emerald-500");
  });
  it("thanh ngang loại vật có nhãn đọc được cho từng loại", () => {
    const html = render();
    expect(html).toMatch(/aria-label="Người đi bộ: Lô \d+ \(/);
  });
});
