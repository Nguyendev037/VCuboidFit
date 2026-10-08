import React from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it, vi } from "vitest";
import { AdvancedParamsPanel } from "@/components/AdvancedParamsPanel";
import mockSchema from "@/mocks/params-schema.json";
import type { ParamsSchema } from "@/lib/api/types";
import {
  type AdvancedDraft,
  weightPercents,
  draftFromSchema,
  isAdvancedPanelInitiallyOpen,
  normalizeAdvancedParams,
  tier0LockNote,
  sanitizeDraft,
  sanitizeSelectParams,
} from "./advancedParams";

const schema: ParamsSchema = {
  tierAvailable: [0, 1],
  fields: [
    { key: "tier", label: "Tầng", type: "integer", min: 0, max: 1, step: 1, default: 1 },
    { key: "k", label: "k", type: "integer", min: 3, max: 50, step: 1, default: 12 },
    { key: "lam", label: "λ", type: "number", min: 0, max: 1, step: 0.05, default: 0.65 },
    { key: "maxPerScene", label: "m", type: "integer", min: 1, max: 50, step: 1, default: 5 },
    { key: "quotaOff", label: "Không giới hạn", type: "boolean", default: false },
    { key: "alpha", label: "α", type: "number", min: 0, max: 1, step: 0.05, default: 2 },
    { key: "beta", label: "β", type: "number", min: 0, max: 1, step: 0.05, default: 1 },
    { key: "gamma", label: "γ", type: "number", min: 0, max: 1, step: 0.05, default: 1 },
  ],
};

describe("advanced LiDAR params", () => {
  it("đóng mặc định khi localStorage chưa bật", () => {
    const storage = { getItem: vi.fn(() => null) } as unknown as Storage;
    expect(isAdvancedPanelInitiallyOpen(storage)).toBe(false);
  });

  it("dựng draft từ params-schema", () => {
    expect(draftFromSchema(schema)).toMatchObject({
      tier: 1,
      k: 12,
      lam: 0.65,
      maxPerScene: 5,
      alpha: 2,
      beta: 1,
      gamma: 1,
    });
  });

  it("chuẩn hoá alpha + beta + gamma về tổng 1 khi gửi", () => {
    const normalized = normalizeAdvancedParams(draftFromSchema(schema));
    expect(normalized.pipeline).toBe("lidar");
    expect(normalized.alpha + normalized.beta + normalized.gamma).toBeCloseTo(1);
    expect(normalized.alpha).toBeCloseTo(0.5);
    expect(normalized.beta).toBeCloseTo(0.25);
    expect(normalized.gamma).toBeCloseTo(0.25);
  });

  it("tier 0 khoá beta và gamma", () => {
    const normalized = normalizeAdvancedParams({ ...draftFromSchema(schema), tier: 0 });
    expect(normalized.alpha).toBe(1);
    expect(normalized.beta).toBe(0);
    expect(normalized.gamma).toBe(0);
  });

  it("giữ lam và maxPerScene trong payload gửi đi", () => {
    const normalized = normalizeAdvancedParams({
      ...draftFromSchema(schema),
      lam: 0.42,
      maxPerScene: 7,
    });
    expect(normalized.lam).toBe(0.42);
    expect(normalized.maxPerScene).toBe(7);
  });

  it("không tạo alias m cho maxPerScene", () => {
    const normalized = normalizeAdvancedParams(draftFromSchema(schema));
    expect(normalized).not.toHaveProperty("m");
    expect(Object.keys(normalized)).not.toContain("m");
  });

  it("giữ quotaOff và không tạo alias quotaOn", () => {
    const normalized = normalizeAdvancedParams({
      ...draftFromSchema(schema),
      quotaOff: true,
    });
    expect(normalized.quotaOff).toBe(true);
    expect(normalized).not.toHaveProperty("quotaOn");
    expect(Object.keys(normalized)).not.toContain("quotaOn");
    expect(normalized.maxPerScene).toBeNull();
  });

  it("dùng trọng số hiếm khi tổng trọng số tầng 1 bằng 0", () => {
    const normalized = normalizeAdvancedParams({
      ...draftFromSchema(schema),
      alpha: 0,
      beta: 0,
      gamma: 0,
    });
    expect(normalized.alpha + normalized.beta + normalized.gamma).toBe(1);
    expect(normalized.alpha).toBe(1);
    expect(normalized.beta).toBe(0);
    expect(normalized.gamma).toBe(0);
  });

  it("payload chỉ chứa đúng các khoá đã khai báo", () => {
    const normalized = normalizeAdvancedParams(draftFromSchema(schema));
    expect(Object.keys(normalized).sort()).toEqual(
      [
        "alpha",
        "beta",
        "gamma",
        "k",
        "lam",
        "maxPerScene",
        "pipeline",
        "quotaOff",
        "tier",
      ].sort(),
    );
  });
});

describe("panel ngôn ngữ thường", () => {
  const mock = mockSchema as unknown as ParamsSchema;
  const render = (draftPatch: Partial<AdvancedDraft> = {}, sch: ParamsSchema = mock) =>
    renderToStaticMarkup(
      React.createElement(AdvancedParamsPanel, {
        open: true,
        schema: sch,
        draft: { ...draftFromSchema(sch), ...draftPatch },
        applied: false,
        onToggle: () => {},
        onDraftChange: () => {},
        onApply: () => {},
        onReset: () => {},
      }),
    );

  it("không còn ký hiệu toán trong DOM từ mock mới", () => {
    expect(render({ tier: 1 })).not.toMatch(/α|β|γ|λ|MMR|quota|Tier/);
    expect(render({ tier: 0 })).not.toMatch(/α|β|γ|λ|MMR|quota|Tier/);
  });

  it("quy đổi phần trăm trọng số", () => {
    const base = draftFromSchema(mock);
    expect(weightPercents({ ...base, tier: 1, alpha: 0.5, beta: 0.25, gamma: 0.25 })).toEqual({ alpha: 50, beta: 25, gamma: 25 });
    expect(weightPercents({ ...base, tier: 1, alpha: 1, beta: 1, gamma: 0 })).toEqual({ alpha: 50, beta: 50, gamma: 0 });
    const html = render({ tier: 1, alpha: 0.5, beta: 0.25, gamma: 0.25 });
    expect(html).toContain("50%");
    expect(html).toContain("25%");
    expect(html).not.toContain("Tổng trọng số");
  });

  it("tier 0 hiện basicNote và khoá beta/gamma", () => {
    const html = render({ tier: 0 });
    expect(html).toContain("Chế độ Cơ bản chỉ dùng tiêu chí Hiếm trong dữ liệu.");
    expect(html.match(/type="range"[^>]*disabled=""/g)?.length).toBe(2);
    expect(render({ tier: 1 })).not.toContain("Chế độ Cơ bản chỉ dùng");
  });

  it("tier 0 có Tầng 1: ghi chú hướng dẫn chọn Tầng 1 và thanh khoá có tooltip", () => {
    const html = render({ tier: 0 });
    expect(html).toContain("Chọn Tầng 1 ở trên để chỉnh 2 tiêu chí còn lại.");
    expect(html).toContain("Đã khoá ở Tầng 0");
    expect(html.match(/<label[^>]*title="Đã khoá ở Tầng 0[^"]*"/g)?.length).toBe(2);
    expect(render({ tier: 1 })).not.toContain("Đã khoá");
  });

  it("tier 0 không có Tầng 1: ghi chú trỏ docs/run-local.md mục 5", () => {
    const sch = JSON.parse(JSON.stringify(mock)) as ParamsSchema;
    sch.tierAvailable = [0];
    const html = render({ tier: 0 }, sch);
    expect(html).toContain("job này chưa có, xem docs/run-local.md mục 5.");
    expect(html).not.toContain("Chọn Tầng 1 ở trên");
    expect(html.match(/<label[^>]*title="Đã khoá: tiêu chí này cần tín hiệu Tầng 1[^"]*"/g)?.length).toBe(2);
  });

  it("tier0LockNote không có basicNote dùng câu mặc định", () => {
    expect(tier0LockNote({ tier1Available: true })).toBe(
      "Đang ở Tầng 0: chỉ dùng tiêu chí Hiếm trong dữ liệu. Chọn Tầng 1 ở trên để chỉnh 2 tiêu chí còn lại.",
    );
  });

  it("option có disabledReason bị disable và hiện lý do", () => {
    const sch = JSON.parse(JSON.stringify(mock)) as ParamsSchema;
    sch.fields.find((f) => f.key === "tier")!.options![1].disabledReason = "Chưa có model AI";
    const html = render({ tier: 0 }, sch);
    expect(html).toMatch(/<button[^>]*disabled=""[^>]*title="Chưa có model AI"/);
    expect(html).toContain("Chưa có model AI");
    expect(render({ tier: 0 })).not.toMatch(/disabled=""[^>]*aria-pressed/);
  });

  it("hiển thị lam dạng phần trăm và k kèm đơn vị", () => {
    const html = render({ tier: 1, lam: 0.7, k: 10 });
    expect(html).toContain("70% Hiếm nhất · 30% Đa dạng nhất");
    expect(html).toContain("10 frame");
  });

  it("schema cũ không có trường mới vẫn render", () => {
    const html = render({}, schema);
    expect(html).toContain("Tham số nâng cao");
    expect(html).toContain("Tầng 1");
  });

  describe("job không có Tầng 1", () => {
    const tier0 = (() => {
      const sch = JSON.parse(JSON.stringify(mock)) as ParamsSchema;
      sch.tierAvailable = [0];
      return sch;
    })();

    it("A3: thanh β, γ hiển thị 0% (khoá), α 100%", () => {
      expect(weightPercents(draftFromSchema(tier0))).toEqual({ alpha: 100, beta: 0, gamma: 0 });
    });

    it("A5: select không mang tier=1 hay β,γ > 0", () => {
      const out = sanitizeSelectParams({ budget: 0.05, tier: 1 as const, alpha: 0.5, beta: 0.25, gamma: 0.25 }, tier0);
      expect(out).toMatchObject({ tier: 0, alpha: 1, beta: 0, gamma: 0 });
      const keep = { budget: 0.05, tier: 1 as const, beta: 0.3 };
      expect(sanitizeSelectParams(keep, schema)).toBe(keep);
    });

    it("A6: draft cũ của job có Tầng 1 bị reset về mặc định Tầng 0", () => {
      const old: AdvancedDraft = { ...draftFromSchema(schema), tier: 1, alpha: 0.5, beta: 0.25, gamma: 0.25 };
      expect(sanitizeDraft(old, tier0)).toEqual(draftFromSchema(tier0));
      expect(sanitizeDraft(old, schema)).toBe(old);
    });
  });
});
