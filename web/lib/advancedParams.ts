import type { ParamsSchema } from "@/lib/api/types";

export interface AdvancedDraft {
  tier: 0 | 1;
  k: number;
  lam: number;
  maxPerScene: number;
  quotaOff: boolean;
  alpha: number;
  beta: number;
  gamma: number;
}

export interface AdvancedSubmitParams extends Omit<AdvancedDraft, "maxPerScene"> {
  pipeline: "lidar";
  maxPerScene: number | null;
}

const FALLBACK_DRAFT: AdvancedDraft = {
  tier: 0,
  k: 10,
  lam: 0.7,
  maxPerScene: 4,
  quotaOff: false,
  alpha: 1,
  beta: 0,
  gamma: 0,
};

export function isAdvancedPanelInitiallyOpen(storage?: Storage | null): boolean {
  try {
    return storage?.getItem("vcf-advanced-open") === "1";
  } catch {
    return false;
  }
}

export function draftFromSchema(schema?: ParamsSchema | null): AdvancedDraft {
  const field = (key: string) => schema?.fields.find((f) => f.key === key);
  const numberDefault = (key: string, fallback: number) => {
    const value = field(key)?.default;
    return typeof value === "number" ? value : fallback;
  };
  const boolDefault = (key: string, fallback: boolean) => {
    const value = field(key)?.default;
    return typeof value === "boolean" ? value : fallback;
  };
  const tierDefault = numberDefault("tier", schema?.tierAvailable.includes(1) ? 1 : 0);
  const tier = tierDefault === 1 && schema?.tierAvailable.includes(1) ? 1 : 0;
  return {
    tier,
    k: numberDefault("k", FALLBACK_DRAFT.k),
    lam: numberDefault("lam", FALLBACK_DRAFT.lam),
    maxPerScene: numberDefault("maxPerScene", numberDefault("m", FALLBACK_DRAFT.maxPerScene)),
    quotaOff: boolDefault("quotaOff", FALLBACK_DRAFT.quotaOff),
    alpha: numberDefault("alpha", tier === 0 ? 1 : 0.5),
    beta: tier === 0 ? 0 : numberDefault("beta", 0.25),
    gamma: tier === 0 ? 0 : numberDefault("gamma", 0.25),
  };
}

export function normalizeAdvancedParams(draft: AdvancedDraft): AdvancedSubmitParams {
  if (draft.tier === 0) {
    return {
      ...draft,
      pipeline: "lidar",
      alpha: 1,
      beta: 0,
      gamma: 0,
      maxPerScene: draft.quotaOff ? null : draft.maxPerScene,
    };
  }

  const sum = draft.alpha + draft.beta + draft.gamma;
  if (sum === 0) {
    return {
      ...draft,
      pipeline: "lidar",
      alpha: 1,
      beta: 0,
      gamma: 0,
      maxPerScene: draft.quotaOff ? null : draft.maxPerScene,
    };
  }
  const divisor = sum;
  return {
    ...draft,
    pipeline: "lidar",
    alpha: draft.alpha / divisor,
    beta: draft.beta / divisor,
    gamma: draft.gamma / divisor,
    maxPerScene: draft.quotaOff ? null : draft.maxPerScene,
  };
}

/** Phần trăm đã quy đổi (tổng = 100) của 3 tiêu chí, đúng như khi gửi đi. */
export function weightPercents(draft: AdvancedDraft): { alpha: number; beta: number; gamma: number } {
  const n = normalizeAdvancedParams(draft);
  const alpha = Math.round(n.alpha * 100);
  const beta = Math.round(n.beta * 100);
  return { alpha, beta, gamma: Math.max(0, 100 - alpha - beta) };
}
