import React from "react";
import type { RareAnalysis } from "@/lib/api/types";
import { kpiRows } from "@/lib/rareAnalysis";

export function KpiStrip({ analysis }: { analysis: RareAnalysis }) {
  return (
    <div className="grid grid-cols-2 gap-3 lg:grid-cols-4">
      {kpiRows(analysis).map(r => (
        <div
          key={r.label}
          aria-label={`${r.label}: ${r.value}${r.detail ? `, ${r.detail}` : ""}`}
          className="rounded-xl border border-slate-200 bg-white p-4 shadow-sm"
        >
          <p className="text-xs text-slate-600">{r.label}</p>
          <strong className="mt-1 block text-2xl font-bold tabular-nums text-slate-900">
            {r.value}
          </strong>
          {r.detail && <p className="mt-0.5 text-[11px] text-slate-500">{r.detail}</p>}
        </div>
      ))}
    </div>
  );
}