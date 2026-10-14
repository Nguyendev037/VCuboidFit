import type { ParamsSchema, Preset, SelectParams } from "./api/types";

export type Weights = { rare: number; novel: number; unsure: number }; // tổng = 1

export function effectiveWeights(input: {
  preset: Preset;
  presets?: ParamsSchema["presets"];
  tier1Available: boolean; // false ⇒ Tầng 0
  expert?: { alpha?: number; beta?: number; gamma?: number } | null; // advancedParams đã Áp dụng
}): Weights | null {
  if (!input.tier1Available) {
    return { rare: 1, novel: 0, unsure: 0 };
  }

  const expert = input.expert;
  const hasExpertWeights =
    expert != null &&
    (typeof expert.alpha === "number" || typeof expert.beta === "number" || typeof expert.gamma === "number");

  if (hasExpertWeights) {
    const a = expert.alpha ?? 0;
    const b = expert.beta ?? 0;
    const g = expert.gamma ?? 0;
    if (![a, b, g].every(Number.isFinite)) return null;
    const sum = a + b + g;
    if (sum <= 0) return null;
    return { rare: a / sum, novel: b / sum, unsure: g / sum };
  }

  const presetTuple = input.presets?.[input.preset];
  if (presetTuple) {
    if (!Array.isArray(presetTuple) || presetTuple.length !== 3 || !presetTuple.every(Number.isFinite)) return null;
    const [r, n, u] = presetTuple;
    const sum = r + n + u;
    if (sum <= 0) return null;
    return { rare: r / sum, novel: n / sum, unsure: u / sum };
  }

  return null;
}

export const SPREAD_ON = { diversity: 0.5 } as const; // = mặc định cũ ("medium", λ 0.7, m 4)
export const SPREAD_OFF = { diversity: 0.2, quotaOff: true } as const; // "low" (λ 0.9), không giới hạn/cảnh

export function spreadParams(on: boolean): Partial<SelectParams> {
  return on ? { diversity: 0.5 } : { diversity: 0.2, quotaOff: true };
}

/** Lần chạy khôi phục mà người dùng chưa chạm công tắc ⇒ giữ nguyên diversity/quotaOff đã lưu (vd "high"). */
export function spreadRequest(spread: boolean, keepRestored: boolean): Partial<SelectParams> {
  return keepRestored ? {} : spreadParams(spread);
}

export function spreadFromParams(p: Partial<SelectParams>): boolean {
  if (p.quotaOff === true) return false;
  if (typeof p.diversity === "number" && p.diversity <= 0.35) return false;
  if (typeof p.diversity === "string" && (p.diversity === "low" || Number(p.diversity) <= 0.35)) return false;
  return true;
}

export function minScenes(frames: number, perScene: number | null, totalScenes?: number): number | null {
  if (perScene === null || perScene <= 0) return null;
  const needed = Math.ceil(frames / perScene);
  return typeof totalScenes === "number" && totalScenes > 0 ? Math.min(needed, totalScenes) : needed;
}
