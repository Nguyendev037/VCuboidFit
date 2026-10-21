import React from "react";
import Link from "next/link";
import type { SelectionResult } from "@/lib/api/types";
import { RARE_PANELS as T, visibleWarnings, warningLabel } from "@/lib/glossary";
import { ExportImages } from "@/components/review/ExportImages";
export function ResultActions({ result, jobId, budget }: { result: SelectionResult; jobId: string; budget: number }) {
  const gate = result.gateSummary;
  return <div className="flex flex-wrap items-center gap-3 rounded-xl border border-slate-200 p-3">
    {gate && <span className="rounded-full bg-slate-100 px-3 py-1 text-xs">{gate.valid} {T.valid} · {gate.suspect} {T.suspect} · {gate.outlier} {T.outlier}</span>}
    {visibleWarnings(result.warningCodes ?? []).map(code => <p key={code} role="status" className="text-xs text-amber-800">{warningLabel(code)}</p>)}
    <ExportImages jobId={jobId} sid={result.selectionId} budget={budget} />
    <Link className="text-xs text-blue-700 underline" href={`/review/context?job=${encodeURIComponent(jobId)}&sel=${encodeURIComponent(result.selectionId)}`}>{T.queue}</Link>
  </div>;
}