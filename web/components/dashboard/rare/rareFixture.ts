import type { RareAnalysis, RareEvaluation } from "@/lib/api/types";

/** Fixture contract đầy đủ, chỉ dùng trong unit test. */
export const evaluation: RareEvaluation = {
  axis: "r2_combo", inSample: true, B: 7, nTargets: 10,
  rows: [
    { key: "ours", iy: 0.8, iyStd: null, nInstances: 6, irecall: 0.6 },
    { key: "score_only", iy: 0.7, iyStd: null, nInstances: 5, irecall: 0.5 },
    { key: "crowd", iy: 0.6, iyStd: null, nInstances: 4, irecall: 0.4 },
    { key: "random", iy: 0.2, iyStd: 0.08, nInstances: 1.4, irecall: 0.14 },
    { key: "oracle", iy: 1.2, iyStd: null, nInstances: 9, irecall: 0.9 },
  ],
  byAxis: (["r1_class", "r2_combo", "r3_behavior", "i_conflict", "h_hard"] as const).map(axis => ({ axis, targets: 10, ours: 6, randomMean: 1.4 })),
};
export const rareFixture: RareAnalysis = {
  version: 1,
  pool: { frames: 125, eligible: 121, scenes: 4, objects: 100, vru: 60, taggedRare: 20 },
  selected: { frames: 7, scenes: 4, objects: 15, vru: 12, taggedRare: 2 },
  tagRates: (["R1", "R2", "R3", "H", "C", "I"] as const).map(tag => ({ tag, selected: 2, selectedPct: 0.2857, poolPct: 0.1286, lift: 2.2222 })),
  reasons: [{ code: "slice", frames: 3 }, { code: "vru", frames: 2 }, { code: "concept", frames: 1 }, { code: "none", frames: 1 }],
  classMix: [
    { cls: "pedestrian", selected: 6, pool: 30 }, { cls: "bicycle", selected: 3, pool: 15 },
    { cls: "motorcycle", selected: 2, pool: 10 }, { cls: "vru_unknown", selected: 1, pool: 5 },
    { cls: "other", selected: 3, pool: 40 },
  ],
  distance: { edges: [0, 10, 20, 30, 40, 50], selected: [4, 3, 2, 1, 1, 1], pool: [20, 10, 10, 8, 7, 5] },
  scenes: [1, 2, 3, 4].map((order, i) => ({ scene: `private-token-${i}`, order, pool: i === 0 ? 31 : 30, selected: i === 0 ? 1 : 2 })),
  scoreHistogram: { edges: Array.from({ length: 21 }, (_, i) => i / 20), counts: [7, ...Array<number>(19).fill(6)], threshold: 0.6 },
  evaluation, evaluationReason: "ok",
};