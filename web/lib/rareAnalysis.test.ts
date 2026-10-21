import { describe, expect, it } from "vitest";
import { rareFixture as a, evaluation } from "@/components/dashboard/rare/rareFixture";
import { axisRows, classRows, distanceRows, evaluationRows, kpiRows, pctText, reasonRows, sceneRows, scoreRows, tagRows } from "./rareAnalysis";
import { EVAL_ROW_LABELS } from "./glossary";

describe("rare analysis presentation", () => {
  it("dịch tag và định dạng lift một chữ số lẻ", () => {
    expect(tagRows(a)[1]).toMatchObject({ label: "Tổ hợp hiếm", liftText: "×2,2" });
    expect(tagRows({ ...a, tagRates: [{ ...a.tagRates[0], lift: null }] })[0].liftText).toBe("—");
  });
  it("nhãn sáu bin khoảng cách, bin cuối mở", () => {
    expect(distanceRows(a).map(r => r.label)).toEqual(["0–10 m", "10–20 m", "20–30 m", "30–40 m", "40–50 m", "≥ 50 m"]);
    expect(distanceRows(a)[0].selectedPct).toBeCloseTo(4 / 12);
    expect(distanceRows(a)[0].poolPct).toBeCloseTo(20 / 60);
  });
  it("năm hàng đánh giá đúng thứ tự dù API đổi thứ tự; không tự tạo số", () => {
    const rows = evaluationRows({ ...evaluation, rows: [...evaluation.rows].reverse() });
    expect(rows.map(r => r.key)).toEqual(["ours", "score_only", "crowd", "random", "oracle"]);
    expect(rows.map(r => r.label)).toEqual(Object.values(EVAL_ROW_LABELS));
    expect(rows[3].valueText).toBe("0,2 ± 0,08");
    expect(evaluationRows({ ...evaluation, rows: [] })).toEqual([]);
  });
  it("phần trăm dùng dấu cách hẹp", () => expect(pctText(0.3846)).toBe("38\u202f%"));
  it("dịch lý do và cảnh mà không lộ token", () => {
    expect(reasonRows(a).map(r => r.label)).toEqual(["Tổ hợp hiếm", "Người/xe hai bánh", "Khái niệm ảnh (OpenCLIP)", "Không có vật"]);
    expect(sceneRows(a)[0]).toMatchObject({ label: "Cảnh 1", fraction: 1 / 31 });
  });
  it("chuẩn hoá lớp riêng từng nhóm và đặt vật khác cuối", () => {
    const rows = classRows({ ...a, classMix: [...a.classMix].reverse() });
    expect(rows.at(-1)?.label).toBe("Vật khác");
    expect(rows.reduce((n, r) => n + r.selectedPct, 0)).toBeCloseTo(1);
    expect(rows.reduce((n, r) => n + r.poolPct, 0)).toBeCloseTo(1);
  });
  it("pool rỗng không sinh NaN hay Infinity", () => {
    const empty = { ...a, pool: { frames: 0, eligible: 0, scenes: 0, objects: 0, vru: 0, taggedRare: 0 }, selected: { frames: 0, scenes: 0, objects: 0, vru: 0, taggedRare: 0 }, classMix: a.classMix.map(r => ({ ...r, selected: 0, pool: 0 })), distance: { ...a.distance, selected: Array<number>(6).fill(0), pool: Array<number>(6).fill(0) } };
    expect(classRows(empty).every(r => r.selectedPct === 0 && r.poolPct === 0)).toBe(true);
    expect(distanceRows(empty).every(r => r.selectedPct === 0 && r.poolPct === 0)).toBe(true);
    expect(kpiRows(empty)[0].detail).toBe("0\u202f% của pool");
    expect(reasonRows(empty).every(r => r.fraction === 0)).toBe(true);
  });
  it("histogram giữ nguyên tổng và ngưỡng; trục đánh giá dịch đủ", () => {
    expect(scoreRows(a)).toMatchObject({ total: 121, threshold: 0.6, thresholdPct: 60 });
    expect(scoreRows(a).rows).toHaveLength(20);
    expect(axisRows(evaluation).map(r => r.label)).toEqual(["Loại vật hiếm", "Tổ hợp hiếm", "Hành vi hiếm", "Tương tác xung đột", "Vật khó quan sát"]);
  });
});