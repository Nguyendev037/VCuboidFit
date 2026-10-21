import type { RareAnalysis, RareEvaluation } from "./api/types";
import { EVAL_AXIS_LABELS, EVAL_ROW_LABELS, OBJECT_CLASS_LABELS, PRED_TAG_LABELS, RARE_PANELS, REASON_CODE_LABELS } from "./glossary";

export const pctText = (x: number) => `${Math.round(x * 100)}\u202f%`;
export const numberText = (x: number) => x.toLocaleString("vi-VN", { maximumFractionDigits: 4 });
const ratio = (n: number, total: number) => total > 0 ? n / total : 0;
export function tagRows(a: RareAnalysis) {
  return a.tagRates.map(r => ({ ...r, label: PRED_TAG_LABELS[r.tag], liftText: r.lift === null ? "—" : `×${r.lift.toFixed(1).replace(".", ",")}` }));
}
export function reasonRows(a: RareAnalysis) {
  return a.reasons.map(r => ({ ...r, label: REASON_CODE_LABELS[r.code], fraction: ratio(r.frames, a.selected.frames) }));
}
export function classRows(a: RareAnalysis) {
  const selected = a.classMix.reduce((n, r) => n + r.selected, 0);
  const pool = a.classMix.reduce((n, r) => n + r.pool, 0);
  return [...a.classMix].sort((x, y) => Number(x.cls === "other") - Number(y.cls === "other")).map(r => ({ ...r, label: OBJECT_CLASS_LABELS[r.cls], selectedPct: ratio(r.selected, selected), poolPct: ratio(r.pool, pool) }));
}
export function distanceRows(a: RareAnalysis) {
  const selected = a.distance.selected.reduce((n, v) => n + v, 0);
  const pool = a.distance.pool.reduce((n, v) => n + v, 0);
  return a.distance.edges.map((edge, i, edges) => ({ label: i === edges.length - 1 ? `≥ ${edge} m` : `${edge}–${edges[i + 1]} m`, selected: a.distance.selected[i], pool: a.distance.pool[i], selectedPct: ratio(a.distance.selected[i], selected), poolPct: ratio(a.distance.pool[i], pool) }));
}
export function sceneRows(a: RareAnalysis) {
  return a.scenes.map(r => ({ ...r, label: `${RARE_PANELS.scene} ${r.order}`, fraction: ratio(r.selected, r.pool) }));
}
export function evaluationRows(e: RareEvaluation) {
  return (Object.keys(EVAL_ROW_LABELS) as Array<keyof typeof EVAL_ROW_LABELS>).flatMap(key => {
    const row = e.rows.find(r => r.key === key);
    return row ? [{ ...row, label: EVAL_ROW_LABELS[key], fraction: ratio(row.iy, Math.max(...e.rows.map(r => r.iy))), valueText: `${numberText(row.iy)}${row.key === "random" && row.iyStd !== null ? ` ± ${numberText(row.iyStd)}` : ""}` }] : [];
  });
}
export function axisRows(e: RareEvaluation) {
  return e.byAxis.map(r => ({ ...r, label: EVAL_AXIS_LABELS[r.axis] }));
}
export function scoreRows(a: RareAnalysis) {
  const h = a.scoreHistogram;
  const total = h.counts.reduce((n, v) => n + v, 0);
  const max = Math.max(...h.counts, 0);
  return { total, threshold: h.threshold, thresholdPct: h.threshold * 100, rows: h.counts.map((count, i) => ({ label: `${numberText(h.edges[i])}–${numberText(h.edges[i + 1])}`, count, height: max > 0 ? count / max * 100 : 0 })) };
}
export function kpiRows(a: RareAnalysis) {
  return [
    { label: RARE_PANELS.selected, value: `${a.selected.frames}/${a.pool.eligible}`, detail: `${pctText(ratio(a.selected.frames, a.pool.eligible))} ${RARE_PANELS.poolShare}` },
    { label: RARE_PANELS.covered, value: `${a.selected.scenes}/${a.pool.scenes}` },
    { label: RARE_PANELS.rare, value: `${a.selected.taggedRare}/${a.selected.frames}`, detail: `${RARE_PANELS.poolPrefix} ${a.pool.taggedRare}/${a.pool.eligible}` },
    { label: RARE_PANELS.vru, value: `${a.selected.vru} ${RARE_PANELS.object}` },
  ];
}
