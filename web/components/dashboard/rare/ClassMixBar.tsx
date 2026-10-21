import React from "react";
import type { RareAnalysis } from "@/lib/api/types";
import { classRows, pctText } from "@/lib/rareAnalysis";
import { RARE_PANELS as T } from "@/lib/glossary";
import { Panel } from "./BarRow";

/** Thanh ngang: mỗi loại vật hai thanh, tỉ trọng trong lô (xanh lá) và trong cả pool (xám). */
export function ClassMixBar({ analysis }: { analysis: RareAnalysis }) {
  return (
    <Panel title={T.classes.title} tooltip={T.classes.tooltip}>
      <div className="flex items-center gap-3 text-xs text-slate-500">
        <span className="inline-flex items-center gap-1">
          <span aria-hidden="true" className="h-2 w-2 rounded-full bg-emerald-500" />
          <span>{T.batch}</span>
        </span>
        <span className="inline-flex items-center gap-1">
          <span aria-hidden="true" className="h-2 w-2 rounded-full bg-slate-300" />
          <span>{T.pool}</span>
        </span>
      </div>
      <div className="space-y-3 pt-1">
        {classRows(analysis).map(r => (
          <div
            key={r.cls}
            role="img"
            aria-label={`${r.label}: ${T.batch} ${r.selected} (${pctText(r.selectedPct)}), ${T.pool} ${r.pool} (${pctText(r.poolPct)})`}
            className="flex items-center gap-3 text-xs"
          >
            <span className="w-36 shrink-0 truncate text-sm text-slate-700" title={r.label}>{r.label}</span>
            <div className="flex-1 space-y-1">
              {([["selectedPct", "bg-emerald-500"], ["poolPct", "bg-slate-300"]] as const).map(([key, color]) => (
                <div key={key} className="h-3.5 overflow-hidden rounded-full bg-slate-100">
                  <div className={`h-full rounded-full ${color}`} style={{ width: `${r[key] * 100}%` }} />
                </div>
              ))}
            </div>
            <span className="w-24 shrink-0 text-right font-mono text-xs text-slate-600">
              {pctText(r.selectedPct)} / {pctText(r.poolPct)}
            </span>
          </div>
        ))}
      </div>
    </Panel>
  );
}
