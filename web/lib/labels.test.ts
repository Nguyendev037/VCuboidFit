import { describe, expect, it } from "vitest";
import { recallRows, stageLabel } from "./constants";

describe("stageLabel", () => {
  it("lidar: nhãn LiDAR", () => {
    expect(stageLabel("lidar_index", "lidar")).toBe("Chỉ mục LiDAR");
    expect(stageLabel("t0", "lidar")).toBe("Descriptor Tầng 0");
  });
  it("camera giữ nguyên nhãn cũ", () => {
    expect(stageLabel("dino", "camera")).toBe("Độ hiếm");
    expect(stageLabel("clip", "camera")).toBe("Khớp kịch bản");
  });
  it("stage lạ trả lại tên gốc", () => {
    expect(stageLabel("xyz", "lidar")).toBe("xyz");
  });
});

describe("recallRows", () => {
  const rec = (recall: number) => ({ recall });
  it("lidar: ánh xạ key ablation sang tiếng Việt, không có Query", () => {
    const rows = recallRows("lidar", {
      hybrid: rec(0.07),
      ablation: { t0_rar_topk: rec(0.1), coreset_z0: rec(0.04), hybrid_nodiv: rec(0.05), t1_nov_mmr: rec(0.06), t1_unc_mmr: rec(0.03) },
      random: { mean: rec(0.06) },
    });
    expect(rows.map((r) => r.name)).toEqual([
      "VCuboidFIT Hybrid", "Tầng 0 · chỉ xếp hạng", "Coreset (đa dạng thuần)", "Không đa dạng",
      "Chỉ Lạ với model", "Chỉ Không chắc", "Random",
    ]);
    expect(rows.some((r) => /kịch bản/i.test(r.name))).toBe(false);
  });
  it("camera giữ nhãn cũ gồm Khớp kịch bản", () => {
    const names = recallRows("camera", { hybrid: rec(0.4), ablation: { novelty: rec(0.2) } }).map((r) => r.name);
    expect(names).toEqual(["VCuboidFIT Hybrid", "Độ hiếm", "Độ khó", "Khớp kịch bản", "Coreset", "Random"]);
  });
});
