import { access, readFile } from "node:fs/promises";
import path from "node:path";

export const BENCH_METHODS = ["M0", "M1", "M2", "M3"] as const;
export type BenchMethodId = typeof BENCH_METHODS[number];
export type BenchMethod = { name: string; iy: number; ci_lo: number; ci_hi: number; status: "ok" | "chưa đo" };
export type DemoBench = {
  schema: "vcf-demo-bench-v1";
  source: { run_id: string };
  label: string;
  pool: number;
  scenes: number;
  capture_primary: string;
  budget_B: number;
  methods: Partial<Record<BenchMethodId, BenchMethod>>;
  primary: { pair: string; delta: number; ci_lo: number; ci_hi: number; conclusion: string };
  figures: string[];
};

function isObject(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}
function isNumber(value: unknown): value is number {
  return typeof value === "number" && Number.isFinite(value);
}
function isBench(value: unknown): value is DemoBench {
  if (!isObject(value) || value.schema !== "vcf-demo-bench-v1") return false;
  if (!isObject(value.source) || typeof value.source.run_id !== "string") return false;
  if (typeof value.label !== "string" || typeof value.capture_primary !== "string") return false;
  if (![value.pool, value.scenes, value.budget_B].every(isNumber)) return false;
  if (!isObject(value.primary) || typeof value.primary.pair !== "string" || typeof value.primary.conclusion !== "string") return false;
  if (![value.primary.delta, value.primary.ci_lo, value.primary.ci_hi].every(isNumber)) return false;
  if (!Array.isArray(value.figures) || !value.figures.every(figure => typeof figure === "string")) return false;
  if (!isObject(value.methods)) return false;
  const methods = value.methods;
  return BENCH_METHODS.every(id => {
    const method = methods[id];
    if (method === undefined) return true;
    return isObject(method) && typeof method.name === "string"
      && (method.status === "ok" || method.status === "chưa đo")
      && [method.iy, method.ci_lo, method.ci_hi].every(isNumber);
  });
}

/** Read C1 without calculating metrics; missing/invalid files keep the C4 state visible. */
export async function loadDemoBench(): Promise<{ bench: DemoBench | null; figureUrl: string | null }> {
  const directory = path.join(process.cwd(), "public", "demo");
  try {
    const value: unknown = JSON.parse(await readFile(path.join(directory, "bench_pitch.json"), "utf8"));
    if (!isBench(value)) return { bench: null, figureUrl: null };
    let figureUrl: string | null = null;
    if (value.figures.includes("fig_iy_budget.png")) {
      try {
        await access(path.join(directory, "fig_iy_budget.png"));
        figureUrl = "/demo/fig_iy_budget.png";
      } catch { /* Optional figure: measurements remain available. */ }
    }
    return { bench: value, figureUrl };
  } catch {
    return { bench: null, figureUrl: null };
  }
}
