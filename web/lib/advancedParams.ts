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

/** Ghi chú giải thích vì sao 2 tiêu chí bị khoá ở Tầng 0 (chỉ thêm chữ UI, không đổi giá trị gửi API). */
export function tier0LockNote(opts: { basicNote?: string; tier1Available: boolean }): string {
  const lead = opts.basicNote?.trim() || "Đang ở Tầng 0: chỉ dùng tiêu chí Hiếm trong dữ liệu.";
  const tail = opts.tier1Available
    ? "Chọn Tầng 1 ở trên để chỉnh 2 tiêu chí còn lại."
    : "Lạ với model và Model chưa chắc chắn cần tín hiệu Tầng 1 (model seed) — job này chưa có, xem docs/run-local.md mục 5.";
  return `${lead} ${tail}`;
}

/** Tooltip trên thanh bị khoá ở Tầng 0. */
export function tier0LockTitle(tier1Available: boolean): string {
  return tier1Available
    ? "Đã khoá ở Tầng 0 (chỉ có tín hiệu hình học). Chọn Tầng 1 để chỉnh tiêu chí này."
    : "Đã khoá: tiêu chí này cần tín hiệu Tầng 1 (model seed), job này chưa có.";
}

/** Job có dùng được Tầng 1 không (chưa tải schema ⇒ chưa biết ⇒ coi như có, để không khoá nhầm). */
export function hasTier1(schema?: ParamsSchema | null): boolean {
  return !schema || schema.tierAvailable.includes(1);
}

/** A6: job không có Tầng 1 mà draft còn tầng 1 / β,γ cũ ⇒ về mặc định Tầng 0 của schema. */
export function sanitizeDraft(draft: AdvancedDraft | null, schema?: ParamsSchema | null): AdvancedDraft {
  const base = draftFromSchema(schema);
  if (!draft) return base;
  if (hasTier1(schema)) return draft;
  return draft.tier === 0 && draft.beta === 0 && draft.gamma === 0 ? draft : base;
}

/** A5: không bao giờ gửi tier=1 hay β,γ > 0 khi job không có Tầng 1. */
export function sanitizeSelectParams<T extends { tier?: 0 | 1 | null; alpha?: number; beta?: number; gamma?: number }>(
  params: T,
  schema?: ParamsSchema | null,
): T {
  if (hasTier1(schema)) return params;
  const out = { ...params, tier: 0 as const };
  if (params.beta || params.gamma) Object.assign(out, { alpha: 1, beta: 0, gamma: 0 });
  return out;
}
