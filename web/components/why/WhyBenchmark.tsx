import React from "react";
import { BENCH_METHODS, type DemoBench } from "@/lib/server/demoBench";
import { EmptyState } from "@/components/ui/DataState";
import { whyCopy as copy } from "./copy";

/** Run công bố trong pitch; ghi chú phạm vi chỉ đúng cho run này. */
const PITCH_RUN_ID = "20261013-192329-49de1480";

export function WhyBenchmark({
  bench,
  figureUrl,
  examples = false,
}: {
  bench: DemoBench | null;
  figureUrl: string | null;
  examples?: boolean;
}) {
  if (!bench) {
    return (
      <section id="bang-chung" aria-labelledby="evidence-title" className="hud-card p-6 sm:p-8">
        <div className="flex flex-col items-center gap-2 text-center mb-6">
          <p className="font-data text-xs font-semibold uppercase tracking-[0.14em] text-sky-700">Dữ liệu thực nghiệm</p>
          <h2 id="evidence-title" className="font-[family-name:var(--font-landing-serif)] text-3xl leading-tight text-slate-900 sm:text-4xl lg:text-5xl">{copy.evidenceTitle}</h2>
        </div>
        <EmptyState message={copy.missing} />
      </section>
    );
  }

  const isShown = bench.primary.conclusion === "shown";
  const mini = /mini/i.test(bench.label);
  const sourceLabel = mini && !/minh ho[ạa]/i.test(bench.label) ? `${bench.label} · minh hoạ` : bench.label;
  const hasNy = BENCH_METHODS.some((id) => typeof bench.methods[id]?.ny === "number");

  return (
    <section id="bang-chung" aria-labelledby="evidence-title" className="hud-card p-6 sm:p-10">
      <div className="flex flex-col items-center gap-2 text-center mb-8">
        <p className="font-data text-xs font-semibold uppercase tracking-[0.14em] text-sky-700">Dữ liệu thực nghiệm</p>
        <h2 id="evidence-title" className="font-[family-name:var(--font-landing-serif)] text-3xl leading-tight text-slate-900 sm:text-4xl lg:text-5xl">{copy.evidenceTitle}</h2>
      </div>

      {/* Khối kết luận so sánh chính với nhãn trạng thái và khoảng tin cậy */}
      <div className="space-y-3">
        <p className={`rounded-vcf-control p-4 font-semibold ${isShown ? "bg-vcf-good-soft text-vcf-good" : "bg-vcf-warn-soft text-vcf-warn"}`}>
          {isShown ? copy.variants.shown : copy.variants.unproven}
        </p>

        <div className="flex flex-wrap items-center justify-between gap-3 rounded-xl border border-slate-200 bg-slate-50/80 px-5 py-3">
          <span className="font-mono text-base font-semibold text-slate-900 tabular-nums break-words">
            {bench.primary.pair}: ΔIY = {bench.primary.delta.toFixed(3)} · CI95 [{bench.primary.ci_lo.toFixed(3)}, {bench.primary.ci_hi.toFixed(3)}]
          </span>
          <span className={`inline-flex items-center px-3 py-1 rounded-full text-xs font-bold font-mono tracking-wider ${isShown ? "bg-emerald-100 text-emerald-800" : "bg-amber-100 text-amber-900"}`}>
            {isShown ? "KẾT LUẬN: ĐÃ CÓ BẰNG CHỨNG" : "KẾT LUẬN: CHƯA CHỨNG MINH (NOT SHOWN)"}
          </span>
        </div>
        <p className="sr-only">{bench.primary.conclusion}</p>
      </div>

      {/* Bảng số benchmark dạng thẻ có CI */}
      <div className="mt-8">
        <h3 className="sr-only">Các phương pháp đánh giá (M0–M3)</h3>
        <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-4">
          {BENCH_METHODS.map((id) => {
            const method = bench.methods[id];
            const measured = method?.status === "ok";
            return (
              <div
                key={id}
                className="flex flex-col justify-between rounded-xl border border-slate-200 bg-white p-5 shadow-sm transition hover:border-slate-300"
              >
                <div>
                  <div className="flex items-center justify-between mb-2">
                    <span className="font-mono text-xs font-bold text-sky-700 bg-sky-50 px-2 py-0.5 rounded">
                      {id}
                    </span>
                    <span className={`text-[11px] font-medium px-2 py-0.5 rounded ${measured ? "bg-slate-100 text-slate-700" : "bg-amber-50 text-amber-800"}`}>
                      {measured ? "Đã đo" : "Chưa đo"}
                    </span>
                  </div>
                  <h4 className="font-semibold text-xl leading-snug text-slate-900">{copy.methodLabels[id]}</h4>
                  <p className="mt-1 font-mono text-xs text-slate-500">{id}{method ? ` · ${method.name}` : ""}</p>
                </div>

                <div className="mt-4 pt-3 border-t border-slate-100">
                  <div className="text-xs text-slate-500 font-medium">Chỉ số IY</div>
                  <div className="text-2xl font-display font-semibold text-slate-900 tabular-nums">
                    {measured ? method.iy.toFixed(3) : "Chưa đo"}
                  </div>
                  <div className="mt-1 font-mono text-xs text-slate-600 tabular-nums">
                    CI95: {measured ? `[${method.ci_lo.toFixed(3)}, ${method.ci_hi.toFixed(3)}]` : "—"}
                  </div>
                  {measured && typeof method.ny === "number" && (
                    <div className="mt-1 font-mono text-xs text-slate-600 tabular-nums">NY: {method.ny.toFixed(3)}</div>
                  )}
                </div>
              </div>
            );
          })}
        </div>
      </div>

      {/* Bảng dữ liệu chuẩn cho truy cập và đối chiếu toàn vẹn */}
      <div className="mt-6 overflow-x-auto rounded-xl border border-slate-200 bg-white">
        <table className="w-full text-left text-base tabular-nums">
          <caption className="sr-only">IY và khoảng tin cậy CI95 của M0–M3</caption>
          <thead className="border-b border-slate-200 bg-slate-50 text-slate-600">
            <tr>
              <th scope="col" className="p-3">Phương pháp</th>
              <th scope="col" className="p-3">IY</th>
              <th scope="col" className="p-3">CI95</th>
              {hasNy && <th scope="col" className="p-3">NY</th>}
            </tr>
          </thead>
          <tbody className="divide-y divide-slate-100">
            {BENCH_METHODS.map((id) => {
              const method = bench.methods[id];
              const measured = method?.status === "ok";
              return (
                <tr key={id} className="hover:bg-slate-50/50">
                  <th scope="row" className="p-3 font-semibold text-slate-800">
                    {copy.methodLabels[id]}
                    <span className="block font-mono text-xs font-normal text-slate-500">{id}{method ? ` · ${method.name}` : ""}</span>
                  </th>
                  <td className="p-3 text-slate-900">
                    {measured ? method.iy.toFixed(3) : "Chưa đo"}
                  </td>
                  <td className="p-3 text-slate-600 font-mono">
                    {measured ? `[${method.ci_lo.toFixed(3)}, ${method.ci_hi.toFixed(3)}]` : "—"}
                  </td>
                  {hasNy && (
                    <td className="p-3 text-slate-900">
                      {measured && typeof method.ny === "number" ? method.ny.toFixed(3) : "—"}
                    </td>
                  )}
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>

      {/* Chú thích một dòng đo được theo yêu cầu */}
      <p className="mt-4 text-sm leading-6 text-slate-600 break-words">
        Nguồn: {sourceLabel} · Run: {bench.source.run_id} · Pool: {bench.pool} frame · {bench.scenes} scene · B = {bench.budget_B} · Capture: {bench.capture_primary}.
      </p>
      {bench.source.run_id === PITCH_RUN_ID && (
        <p className="mt-2 text-sm leading-6 text-slate-600">{copy.pitchRunNote}</p>
      )}

      <div className="mt-6 rounded-xl border border-sky-200 bg-sky-50/60 p-5">
        <h3 className="text-base font-semibold text-slate-900">{copy.howToRead.title}</h3>
        <dl className="mt-3 grid gap-3 sm:grid-cols-2">
          {copy.howToRead.items.map((item) => (
            <div key={item.term}>
              <dt className="font-mono text-sm font-bold text-sky-800">{item.term}</dt>
              <dd className="mt-0.5 text-sm leading-6 text-slate-700">{item.text}</dd>
            </div>
          ))}
        </dl>
      </div>

      {/* Hình minh hoạ thực nghiệm nếu có */}
      {figureUrl && (
        <figure className="mt-8 rounded-xl border border-slate-200 bg-slate-50/50 p-4">
          {/* eslint-disable-next-line @next/next/no-img-element */}
          <img
            src={figureUrl}
            alt={`IY theo ngân sách — ${sourceLabel}`}
            className="h-auto w-full rounded-lg"
          />
          <figcaption className="mt-2 text-center text-sm leading-6 text-slate-600">
            fig_iy_budget.png · {sourceLabel}
          </figcaption>
        </figure>
      )}

      {examples && (
        <figure className="mt-6 rounded-xl border border-slate-200 bg-slate-50/50 p-4">
          {/* eslint-disable-next-line @next/next/no-img-element */}
          <img
            src="/demo/fig_examples.png"
            alt={copy.examples}
            className="h-auto w-full rounded-lg"
          />
          <figcaption className="mt-2 text-center text-sm leading-6 text-slate-600">
            {copy.examples} · {bench.label}
          </figcaption>
        </figure>
      )}
    </section>
  );
}
