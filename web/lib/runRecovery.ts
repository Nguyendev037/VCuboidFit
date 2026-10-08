import type { SelectParams, Pipeline } from "./api/types";

export const LAST_RUN_KEY = "vcf-last-run";
export interface RunBookmark { jobId: string; selectionId?: string; datasetId?: string; demo: boolean }

export function readRunBookmark(search: string, storage?: Pick<Storage, "getItem">): RunBookmark | null {
  const query = new URLSearchParams(search);
  if (query.has("job")) return { jobId: query.get("job")!, selectionId: query.get("sel") || undefined, ...(query.get("dataset") ? { datasetId: query.get("dataset")! } : {}), demo: query.get("demo") === "1" };
  try {
    const value = JSON.parse(storage?.getItem(LAST_RUN_KEY) ?? "null");
    return value && typeof value.jobId === "string" && typeof value.demo === "boolean"
      ? { jobId: value.jobId, selectionId: typeof value.selectionId === "string" ? value.selectionId : undefined, ...(typeof value.datasetId === "string" ? { datasetId: value.datasetId } : {}), demo: value.demo } : null;
  } catch { return null; }
}

export function saveRunBookmark(bookmark: RunBookmark, url: URL, storage?: Pick<Storage, "setItem">): string {
  url.searchParams.set("job", bookmark.jobId);
  if (bookmark.datasetId) url.searchParams.set("dataset", bookmark.datasetId);
  else url.searchParams.delete("dataset");
  if (bookmark.selectionId) url.searchParams.set("sel", bookmark.selectionId);
  else url.searchParams.delete("sel");
  if (bookmark.demo) url.searchParams.set("demo", "1");
  else url.searchParams.delete("demo");
  try { storage?.setItem(LAST_RUN_KEY, JSON.stringify(bookmark)); } catch { /* URL works without storage. */ }
  return url.pathname + url.search + url.hash;
}

export function recoveryParams(params: SelectParams, pipeline: Pipeline): SelectParams {
  const resolved = params as SelectParams & { m?: number | null };
  const { m, ...rest } = resolved;
  return { ...rest, ...(m !== undefined ? { maxPerScene: m, quotaOff: m === null } : {}), pipeline, budget: params.budget ?? 0.05, preset: params.preset ?? "balanced",
    diversity: typeof params.diversity === "number" ? params.diversity : params.diversity === "low" ? 0.2 : params.diversity === "high" ? 0.8 : 0.5 };
}

export function paramsEqual(a: SelectParams, b: SelectParams): boolean {
  const sorted = (p: SelectParams) => JSON.stringify(Object.fromEntries(Object.entries(p).filter(([, v]) => v !== undefined).sort(([x], [y]) => x.localeCompare(y))));
  return sorted(a) === sorted(b);
}

export function recoveryQueries(params: SelectParams | undefined, tags: string[]): SelectParams["queries"] {
  const saved = params?.queries;
  return saved && JSON.stringify(saved.map((q) => typeof q === "string" ? q : q.text)) === JSON.stringify(tags) ? saved : tags;
}

export function inheritedRunParams(params: SelectParams | undefined, overrides: { preset: boolean; diversity: boolean }): Partial<SelectParams> {
  const inherited = { ...params };
  if (overrides.preset) { delete inherited.alpha; delete inherited.beta; delete inherited.gamma; }
  if (overrides.diversity) delete inherited.lam;
  return inherited;
}
