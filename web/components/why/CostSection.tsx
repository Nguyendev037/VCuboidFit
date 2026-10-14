import React from "react";
import { Cpu, FileBox, Archive } from "lucide-react";
import { EmptyState } from "@/components/ui/DataState";
import type { DemoBench } from "@/lib/server/demoBench";
import { whyCopy as copy } from "./copy";

export function CostSection({ bench }: { bench: DemoBench | null }) {
  if (!bench) {
    return (
      <section aria-labelledby="cost-title" className="hud-card p-6 sm:p-8">
        <div className="flex flex-col items-center gap-2 text-center mb-6">
          <p className="font-data text-xs font-semibold uppercase tracking-[0.14em] text-sky-700">Tối ưu hoá</p>
          <h2 id="cost-title" className="font-[family-name:var(--font-landing-serif)] text-3xl leading-tight text-slate-900 sm:text-4xl lg:text-5xl">{copy.costTitle}</h2>
        </div>
        <EmptyState message={copy.missing} />
      </section>
    );
  }

  const ratio = bench.pool > 0 ? (bench.budget_B / bench.pool) * 100 : 0;
  const percentage = bench.pool > 0 ? ratio.toFixed(1) : "—";

  return (
    <section aria-labelledby="cost-title" className="hud-card p-6 sm:p-10">
      <div className="flex flex-col items-center gap-2 text-center mb-8">
        <p className="font-data text-xs font-semibold uppercase tracking-[0.14em] text-sky-700">Tối ưu hoá công sức</p>
        <h2 id="cost-title" className="font-[family-name:var(--font-landing-serif)] text-3xl leading-tight text-slate-900 sm:text-4xl lg:text-5xl">{copy.costTitle}</h2>
      </div>

      {/* Dòng tóm tắt số liệu đọc trực tiếp từ JSON */}
      <div className="mb-8 rounded-xl border border-sky-200/80 bg-sky-50/60 p-5 text-center">
        <p className="text-xl sm:text-2xl font-semibold tabular-nums text-slate-900">
          {copy.annotate} {bench.budget_B} {copy.instead} {bench.pool} {copy.frames} · {percentage} % {copy.budget}
        </p>
      </div>

      {/* Hình minh hoạ so sánh trực quan dạng thanh và ô */}
      <div className="grid grid-cols-1 gap-6 md:grid-cols-2">
        {/* Ô 1: Toàn bộ pool dữ liệu */}
        <div className="flex flex-col justify-between rounded-xl border border-slate-200 bg-slate-50/70 p-6">
          <div>
            <div className="flex items-center justify-between text-xs font-medium uppercase tracking-wider text-slate-500 mb-2">
              <span>{copy.poolLabel}</span>
              <span className="font-data font-semibold text-slate-700">100%</span>
            </div>
            <p className="text-3xl font-display font-semibold text-slate-900 tabular-nums">
              {bench.pool} <span className="text-base font-normal text-slate-600">{copy.frames}</span>
            </p>
            <p className="mt-2 text-base text-slate-600 leading-7">
              Chi phí và thời gian nếu gán nhãn thủ công toàn bộ dữ liệu không qua chọn lọc.
            </p>
          </div>
          <div className="mt-5 h-3 w-full rounded-full bg-slate-300" aria-hidden="true" />
        </div>

        {/* Ô 2: Ngân sách VCuboidFIT chọn lọc */}
        <div className="flex flex-col justify-between rounded-xl border border-sky-300 bg-gradient-to-b from-sky-50/80 to-white p-6 shadow-sm">
          <div>
            <div className="flex items-center justify-between text-xs font-semibold uppercase tracking-wider text-sky-800 mb-2">
              <span>{copy.budgetLabel}</span>
              <span className="font-data rounded bg-sky-600 px-2 py-0.5 text-xs text-white">{percentage}%</span>
            </div>
            <p className="text-3xl font-display font-semibold text-sky-950 tabular-nums">
              {bench.budget_B} <span className="text-base font-normal text-slate-700">{copy.frames}</span>
            </p>
            <p className="mt-2 text-base text-slate-700 leading-7">
              Ưu tiên lô frame trong ngân sách, giữ lý do chọn để người gán nhãn kiểm tra. Hiệu quả được đánh giá riêng bằng benchmark.
            </p>
          </div>
          <div className="mt-5 h-3 w-full rounded-full bg-slate-200 overflow-hidden" aria-hidden="true">
            <div
              className="h-full rounded-full bg-sky-600 transition-all duration-500"
              style={{ width: `${Math.max(ratio, 6)}%` }}
            />
          </div>
        </div>
      </div>

      {/* 3 ô tính năng chi phí */}
      <div className="mt-8 grid grid-cols-1 gap-4 sm:grid-cols-3">
        <div className="flex items-start gap-3.5 rounded-xl border border-slate-200/80 bg-white p-5">
          <span className="flex h-10 w-10 shrink-0 items-center justify-center rounded-lg bg-blue-50 text-blue-700 ring-1 ring-blue-500/20">
            <Cpu className="h-5 w-5" aria-hidden="true" />
          </span>
          <div>
            <h3 className="font-semibold text-xl leading-snug text-slate-900">{copy.costFeatureCpuTitle}</h3>
            <p className="mt-1 text-base text-slate-600 leading-7">{copy.costFeatureCpuText}</p>
          </div>
        </div>

        <div className="flex items-start gap-3.5 rounded-xl border border-slate-200/80 bg-white p-5">
          <span className="flex h-10 w-10 shrink-0 items-center justify-center rounded-lg bg-blue-50 text-blue-700 ring-1 ring-blue-500/20">
            <FileBox className="h-5 w-5" aria-hidden="true" />
          </span>
          <div>
            <h3 className="font-semibold text-xl leading-snug text-slate-900">{copy.costFeatureFileTitle}</h3>
            <p className="mt-1 text-base text-slate-600 leading-7">{copy.costFeatureFileText}</p>
          </div>
        </div>

        <div className="flex items-start gap-3.5 rounded-xl border border-slate-200/80 bg-white p-5">
          <span className="flex h-10 w-10 shrink-0 items-center justify-center rounded-lg bg-blue-50 text-blue-700 ring-1 ring-blue-500/20">
            <Archive className="h-5 w-5" aria-hidden="true" />
          </span>
          <div>
            <h3 className="font-semibold text-xl leading-snug text-slate-900">{copy.costFeatureZipTitle}</h3>
            <p className="mt-1 text-base text-slate-600 leading-7">{copy.costFeatureZipText}</p>
          </div>
        </div>
      </div>

      <p className="mt-6 text-center text-sm leading-6 text-slate-600 max-w-3xl mx-auto leading-relaxed">
        {copy.cost}
      </p>
    </section>
  );
}
