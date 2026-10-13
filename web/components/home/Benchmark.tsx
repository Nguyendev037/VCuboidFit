import React from "react";
import { BENCH_METHODS, type DemoBench } from "@/lib/server/demoBench";

export function Benchmark({ bench, figureUrl }: { bench: DemoBench | null; figureUrl: string | null }) {
  if (!bench) return <p role="status" className="mt-3 text-vcf-muted">Chưa có kết quả T</p>;
  const mini = /mini/i.test(bench.label);
  const sourceLabel = mini && !/minh ho[ạa]/i.test(bench.label) ? `${bench.label} · minh hoạ` : bench.label;
  return <div className="mt-6 rounded-vcf-card border border-vcf-border bg-vcf-surface p-6">
    <p className="font-semibold text-vcf-accent-ink">Nguồn: {sourceLabel}</p>
    <p className="mt-2 break-words text-sm text-vcf-muted">Run: {bench.source.run_id} · Pool: {bench.pool} frame · {bench.scenes} scene · B = {bench.budget_B}</p>
    <p className="mt-2 text-sm text-vcf-muted">Capture B là số đo chính, A là số đo phụ. Capture: {bench.capture_primary}.</p>
    <div className="mt-5 overflow-x-auto">
      <table className="block w-full text-left text-sm tabular-nums sm:table">
        <caption className="sr-only">IY và khoảng tin cậy CI95 của M0–M3</caption>
        <thead className="sr-only bg-vcf-surface-muted text-vcf-muted sm:not-sr-only sm:table-header-group"><tr><th scope="col" className="p-3">Phương pháp</th><th scope="col" className="p-3">IY</th><th scope="col" className="p-3">CI95</th></tr></thead>
        <tbody className="block divide-y divide-vcf-border sm:table-row-group">{BENCH_METHODS.map(id => {
          const method = bench.methods[id];
          const measured = method?.status === "ok";
          return <tr key={id} className="block sm:table-row"><th scope="row" className="block p-3 font-semibold sm:table-cell">{id}{method ? ` · ${method.name}` : ""}</th><td className="block px-3 pb-3 sm:table-cell sm:p-3"><span aria-hidden="true" className="sm:hidden">IY: </span>{measured ? method.iy : "Chưa đo"}</td><td className="block break-words px-3 pb-3 sm:table-cell sm:p-3"><span aria-hidden="true" className="sm:hidden">CI95: </span>{measured ? `[${method.ci_lo}, ${method.ci_hi}]` : "—"}</td></tr>;
        })}</tbody>
      </table>
    </div>
    <p className="mt-5 text-sm tabular-nums">{bench.primary.pair}: ΔIY = {bench.primary.delta} · CI95 [{bench.primary.ci_lo}, {bench.primary.ci_hi}]</p>
    <p className="mt-2 break-words font-semibold">{bench.primary.conclusion}</p>
    {figureUrl && <figure className="mt-6">
      {/* eslint-disable-next-line @next/next/no-img-element */}
      <img src={figureUrl} alt={`IY theo ngân sách — ${sourceLabel}`} className="h-auto w-full rounded-vcf-control" />
      <figcaption className="mt-2 text-sm text-vcf-subtle">fig_iy_budget.png · {sourceLabel}</figcaption>
    </figure>}
  </div>;
}
