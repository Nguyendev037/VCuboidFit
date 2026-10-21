import { describe, it, expect } from "vitest";
import { PRESETS } from "./api/types";
import { reasonText, gtTagLabel, objectClassLabel, objectReasonText, predTagLabel, METRICS, PANEL_HELP, RARITY_COMPARISON, SETTINGS, UPLOAD_HELP } from "./glossary";

describe("glossary", () => {
  it("reasonText converts correctly", () => {
    expect(reasonText("rarity p97")).toBe("Hiếm trong dữ liệu — top 3%");
    expect(reasonText("novelty p90")).toBe("Lạ với model — top 10%");
    expect(reasonText("uncertainty p95")).toBe("Model chưa chắc chắn — top 5%");
    expect(reasonText("rarity p100")).toBe("Hiếm trong dữ liệu — top 1%");
  });

  it("rare_v24 reasons, object classes and tags read as plain words", () => {
    expect(reasonText("rare motorcycle 26m vru47")).toBe("Xe máy cách 26 m · 47 VRU trong khung (dự đoán)");
    expect(reasonText("rare_v24")).toBe("Điểm vật thể cao trong khung (dự đoán)");
    expect(objectClassLabel("vru_unknown")).toBe("VRU chưa rõ loại");
    expect(objectReasonText("shape p91")).toBe("Hình dạng lạ: 91/100");
    expect(objectReasonText("unc p94")).toBe("Model chưa chắc chắn: 94/100");
    expect(objectReasonText("sem p80")).toBe("Lạ về ngữ nghĩa ảnh: 80/100");
    expect(objectReasonText("concept stroller")).toBe("Gần khái niệm: stroller");
    expect(objectReasonText("zzz p5")).toBe("Điểm thành phần: 5/100");
    expect(predTagLabel("R2")).toBe("Lát cắt hiếm");
    expect(predTagLabel("ZZ")).toBe("ZZ");
  });

  it("gtTagLabel converts correctly", () => {
    expect(gtTagLabel("Rare GT A")).toBe("Môi trường khó");
    expect(gtTagLabel("Rare GT B")).toBe("Vật thể rất hiếm");
    expect(gtTagLabel("Unknown")).toBe("Unknown");
  });

  it("explains estimated rarity when labels are unavailable", () => {
    expect(RARITY_COMPARISON.noLabels).toBe("Không có nhãn nên không chấm được — chỉ có độ hiếm ước lượng.");
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

describe("reasonText top percent", () => {
  it("never shows top 0% (p100 is the top 1%)", () => {
    expect(reasonText("rarity p100")).toContain("top 1%");
    expect(reasonText("novelty p97")).toContain("top 3%");
  });
});

describe("panel and upload help", () => {
  const forbidden = /[αβγλ]|\bMMR\b|preset|quota|chunk|\btier\b|\bk=/i;

  it("contains every contracted help key and every preset", () => {
    expect(Object.keys(PANEL_HELP).sort()).toEqual([
      "budget",
      "engine",
      "expert",
      "formula",
      "fullConfig",
      "preset.balanced",
      "preset.hard_for_model",
      "preset.rare_first",
      "preset.safety_scenarios",
      "priority",
      "profile",
      "spread",
      "tierLock",
      "w.novel",
      "w.rare",
      "w.unsure",
    ]);
    expect(Object.keys(UPLOAD_HELP).sort()).toEqual(["dropzone", "limit", "limitFallback", "notice"]);
    for (const preset of PRESETS) {
      expect(PANEL_HELP[`preset.${preset}`]).toBeDefined();
    }
  });

  it("keeps labels, descriptions, and tooltips within copy rules", () => {
    for (const [key, item] of Object.entries(PANEL_HELP)) {
      expect(item.label.length, key).toBeLessThanOrEqual(40);
      expect(item.tooltip.length, key).toBeLessThanOrEqual(220);
      if (item.desc) expect(item.desc.length, key).toBeLessThanOrEqual(45);
      expect(`${item.label} ${item.desc ?? ""} ${item.tooltip}`, key).not.toMatch(forbidden);
    }
    for (const [key, item] of Object.entries(UPLOAD_HELP)) {
      expect(item.label.length, key).toBeLessThanOrEqual(90);
      if (key === "notice") expect(item.tooltip.length, key).toBeLessThanOrEqual(300);
      else expect(item.tooltip.length, key).toBeLessThanOrEqual(220);
      expect(`${item.label} ${item.desc ?? ""} ${item.tooltip}`, key).not.toMatch(forbidden);
    }
  });
});
