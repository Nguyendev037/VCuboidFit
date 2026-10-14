import { describe, expect, it } from "vitest";
import {
  effectiveWeights,
  minScenes,
  SPREAD_OFF,
  SPREAD_ON,
  spreadFromParams,
  spreadParams,
} from "./panelParams";
import type { Preset } from "./api/types";

describe("panelParams", () => {
  describe("T-A1: spreadParams(true)", () => {
    it("returns deep-equal { diversity: 0.5 } without quotaOff key", () => {
      const res = spreadParams(true);
      expect(res).toEqual({ diversity: 0.5 });
      expect("quotaOff" in res).toBe(false);
      expect(SPREAD_ON).toEqual({ diversity: 0.5 });
    });
  });

  describe("T-A2: spreadParams(false) and spreadFromParams round-trips", () => {
    it("spreadParams(false) returns diversity 0.2 and quotaOff true", () => {
      const res = spreadParams(false);
      expect(res).toEqual({ diversity: 0.2, quotaOff: true });
      expect(SPREAD_OFF).toEqual({ diversity: 0.2, quotaOff: true });
    });

    it("spreadFromParams handles 4 required cases accurately", () => {
      // 1: diversity: 0.5 -> true
      expect(spreadFromParams({ diversity: 0.5 })).toBe(true);

      // 2: diversity: 0.2, quotaOff: true -> false
      expect(spreadFromParams({ diversity: 0.2, quotaOff: true })).toBe(false);

      // 3: diversity: 0.8 -> true
      expect(spreadFromParams({ diversity: 0.8 })).toBe(true);

      // 4: quotaOff alone -> false
      expect(spreadFromParams({ quotaOff: true })).toBe(false);

      // Extra roundtrip check
      expect(spreadFromParams(spreadParams(true))).toBe(true);
      expect(spreadFromParams(spreadParams(false))).toBe(false);
    });
  });

  describe("T-A3: effectiveWeights priority and normalization", () => {
    const mockPresets: Record<Preset, [number, number, number]> = {
      balanced: [0.5, 0.25, 0.25],
      rare_first: [0.7, 0.2, 0.1],
      hard_for_model: [0.2, 0.3, 0.5],
      safety_scenarios: [0.5, 0.1, 0.4],
    };

    it("tier1Available = false returns { rare: 1, novel: 0, unsure: 0 }", () => {
      const res = effectiveWeights({
        preset: "balanced",
        presets: mockPresets,
        tier1Available: false,
      });
      expect(res).toEqual({ rare: 1, novel: 0, unsure: 0 });
    });

    it("uses expert normalized alpha/beta/gamma when provided", () => {
      const res = effectiveWeights({
        preset: "balanced",
        presets: mockPresets,
        tier1Available: true,
        expert: { alpha: 2, beta: 1, gamma: 1 },
      });
      expect(res).toEqual({ rare: 0.5, novel: 0.25, unsure: 0.25 });
    });

    it("expert with partial weights defaults missing to 0", () => {
      const res = effectiveWeights({
        preset: "balanced",
        presets: mockPresets,
        tier1Available: true,
        expert: { alpha: 3, beta: 1 },
      });
      expect(res).toEqual({ rare: 0.75, novel: 0.25, unsure: 0 });
    });

    it("expert with sum <= 0 returns null", () => {
      const res = effectiveWeights({
        preset: "balanced",
        presets: mockPresets,
        tier1Available: true,
        expert: { alpha: 0, beta: 0, gamma: 0 },
      });
      expect(res).toBeNull();
    });

    it("missing presets returns null when tier1 is available and no expert", () => {
      const res = effectiveWeights({
        preset: "balanced",
        tier1Available: true,
      });
      expect(res).toBeNull();
    });

    it("preset with sum <= 0 returns null", () => {
      const res = effectiveWeights({
        preset: "balanced",
        presets: { balanced: [0, 0, 0] },
        tier1Available: true,
      });
      expect(res).toBeNull();
    });

    it("preset not found in presets returns null", () => {
      const res = effectiveWeights({
        preset: "unknown_preset" as unknown as Preset,
        presets: mockPresets,
        tier1Available: true,
      });
      expect(res).toBeNull();
    });

    it("normal preset calculation matches normalized tuple", () => {
      const res = effectiveWeights({
        preset: "balanced",
        presets: mockPresets,
        tier1Available: true,
      });
      expect(res).toEqual({ rare: 0.5, novel: 0.25, unsure: 0.25 });
    });
  });

  describe("minScenes", () => {
    it("returns null if perScene is null or <= 0", () => {
      expect(minScenes(100, null, 20)).toBeNull();
      expect(minScenes(100, 0, 20)).toBeNull();
      expect(minScenes(100, -1, 20)).toBeNull();
    });

    it("calculates min(ceil(frames / perScene), totalScenes)", () => {
      // 100 frames / 4 = 25 scenes needed; totalScenes = 10 -> returns 10
      expect(minScenes(100, 4, 10)).toBe(10);
      // 10 frames / 4 = 3 scenes needed; totalScenes = 10 -> returns 3
      expect(minScenes(10, 4, 10)).toBe(3);
      // without totalScenes
      expect(minScenes(10, 4)).toBe(3);
    });
  });
});
