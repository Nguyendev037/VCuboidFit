import { describe, it, expect } from "vitest";
import { reasonText, gtTagLabel, METRICS, SETTINGS } from "./glossary";

describe("glossary", () => {
  it("reasonText converts correctly", () => {
    expect(reasonText("rarity p97")).toBe("Hiếm trong dữ liệu — top 3%");
    expect(reasonText("novelty p90")).toBe("Lạ với model — top 10%");
    expect(reasonText("uncertainty p95")).toBe("Model chưa chắc chắn — top 5%");
    expect(reasonText("rarity p100")).toBe("Hiếm trong dữ liệu — top 0%");
  });

  it("gtTagLabel converts correctly", () => {
    expect(gtTagLabel("Rare GT A")).toBe("Môi trường khó");
    expect(gtTagLabel("Rare GT B")).toBe("Vật thể rất hiếm");
    expect(gtTagLabel("Unknown")).toBe("Unknown");
  });

  it("METRICS and SETTINGS have valid non-empty labels and tooltips, without math symbols", () => {
    const checkNoMath = (str: string | undefined) => {
      if (!str) return;
      expect(str).not.toMatch(/[αβγλ]|MMR|quota|Tier/);
    };

    Object.values(METRICS).forEach((metric) => {
      expect(metric.label).toBeTruthy();
      expect(metric.tooltip).toBeTruthy();
      checkNoMath(metric.label);
      checkNoMath(metric.tooltip);
      checkNoMath(metric.howToRead);
    });

    Object.values(SETTINGS).forEach((setting) => {
      expect(setting.label).toBeTruthy();
      expect(setting.tooltip).toBeTruthy();
      checkNoMath(setting.label);
      checkNoMath(setting.tooltip);
      checkNoMath(setting.detail);
    });
  });
});
