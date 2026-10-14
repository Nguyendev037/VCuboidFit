import React from "react";
import { Compass } from "lucide-react";
import { EmptyState } from "@/components/ui/DataState";
import { whyCopy as copy } from "./copy";

export function BottleneckSection({
  benchExists,
  m2,
}: {
  benchExists: boolean;
  m2: { n_reachable: number; n_targets: number } | null;
}) {
  return (
    <section aria-labelledby="bottleneck-title" className="hud-card p-6 sm:p-10">
      <div className="flex flex-col items-center gap-2 text-center mb-8">
        <p className="font-data text-xs font-semibold uppercase tracking-[0.14em] text-sky-700">Định hướng nâng cấp</p>
        <h2 id="bottleneck-title" className="font-[family-name:var(--font-landing-serif)] text-3xl leading-tight text-slate-900 sm:text-4xl lg:text-5xl">{copy.bottleneckTitle}</h2>
      </div>

      {m2 ? (
        <div className="space-y-6">
          <div className="rounded-xl border border-slate-200 bg-slate-50/80 p-6">
            <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4">
              <div>
                <span className="text-xs font-semibold uppercase tracking-wider text-slate-500">Khả năng tiếp cận ứng viên</span>
                <p className="mt-1 text-2xl sm:text-3xl font-display font-semibold tabular-nums text-slate-900">
                  {copy.reachLabel}: {m2.n_reachable}/{m2.n_targets}
                </p>
              </div>
              <div className="font-data text-xs font-semibold px-3 py-1.5 rounded-full bg-slate-200 text-slate-800 self-start sm:self-center">
                {((m2.n_reachable / m2.n_targets) * 100).toFixed(0)} % mục tiêu có ứng viên
              </div>
            </div>

            <div className="mt-4 h-2.5 w-full rounded-full bg-slate-200 overflow-hidden" aria-hidden="true">
              <div
                className="h-full rounded-full bg-sky-600 transition-all duration-500"
                style={{ width: `${Math.min(100, Math.max(5, (m2.n_reachable / m2.n_targets) * 100))}%` }}
              />
            </div>
          </div>

          <div className="flex items-start gap-4 rounded-xl border border-sky-200 bg-sky-50/60 p-6">
            <span className="flex h-10 w-10 shrink-0 items-center justify-center rounded-lg bg-sky-600 text-white">
              <Compass className="h-5 w-5" aria-hidden="true" />
            </span>
            <div>
              <div className="flex items-center gap-2">
                <span className="font-mono text-xs font-bold text-sky-700 bg-sky-100 px-2 py-0.5 rounded">
                  {copy.bottleneckBadge}
                </span>
                <h3 className="font-semibold text-xl leading-snug text-slate-900">Lộ trình Tầng 1: PointPillars</h3>
              </div>
              <p className="mt-2 text-base text-slate-700 leading-7 max-w-3xl">
                {copy.bottleneck}
              </p>
            </div>
          </div>
        </div>
      ) : (
        <EmptyState message={benchExists ? copy.unavailable : copy.missing} />
      )}
    </section>
  );
}
