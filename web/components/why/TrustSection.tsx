import React from "react";
import { ShieldCheck, FileCheck, Lock, EyeOff } from "lucide-react";
import { whyCopy as copy } from "./copy";

export function TrustSection({
  provenance,
}: {
  provenance: { prereg: string | null; report: string | null } | null;
}) {
  const preregHash = provenance?.prereg?.slice(0, 12) || copy.unavailable;
  const reportHash = provenance?.report || copy.unavailable;

  return (
    <section aria-labelledby="trust-title" className="hud-card p-6 sm:p-10">
      <div className="flex flex-col items-center gap-2 text-center mb-8">
        <p className="font-data text-xs font-semibold uppercase tracking-[0.14em] text-sky-700">Minh bạch độc lập</p>
        <h2 id="trust-title" className="font-[family-name:var(--font-landing-serif)] text-3xl leading-tight text-slate-900 sm:text-4xl lg:text-5xl">{copy.trustTitle}</h2>
      </div>

      <p className="mx-auto max-w-3xl text-center text-lg leading-8 text-slate-700 mb-8">
        {copy.trust}
      </p>

      {/* 4 lớp kiểm chứng minh bạch */}
      <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
        {/* Lớp 1: Đăng ký trước */}
        <div className="flex flex-col justify-between rounded-xl border border-slate-200 bg-white p-5 shadow-sm">
          <div className="flex items-start gap-3.5">
            <span className="flex h-10 w-10 shrink-0 items-center justify-center rounded-lg bg-sky-50 text-sky-700 ring-1 ring-sky-500/20">
              <ShieldCheck className="h-5 w-5" aria-hidden="true" />
            </span>
            <div>
              <h3 className="font-semibold text-xl leading-snug text-slate-900">{copy.trustPreregTitle}</h3>
              <p className="mt-1 text-base text-slate-600 leading-7">
                Kế hoạch thử nghiệm đăng ký trước pitch-v2; tập dữ liệu T chỉ mở đúng một lần duy nhất.
              </p>
            </div>
          </div>
          <div className="mt-4 pt-3 border-t border-slate-100">
            <span className="text-[11px] font-medium text-slate-500 uppercase tracking-wider">{copy.prereg}: </span>
            <span className="font-mono text-xs font-semibold text-slate-800">{preregHash}</span>
          </div>
        </div>

        {/* Lớp 2: Báo cáo đối chiếu */}
        <div className="flex flex-col justify-between rounded-xl border border-slate-200 bg-white p-5 shadow-sm">
          <div className="flex items-start gap-3.5">
            <span className="flex h-10 w-10 shrink-0 items-center justify-center rounded-lg bg-sky-50 text-sky-700 ring-1 ring-sky-500/20">
              <FileCheck className="h-5 w-5" aria-hidden="true" />
            </span>
            <div>
              <h3 className="font-semibold text-xl leading-snug text-slate-900">{copy.trustReportTitle}</h3>
              <p className="mt-1 text-base text-slate-600 leading-7">
                Mã băm báo cáo kết quả kiểm chứng được lưu trữ độc lập để đối chiếu tính toàn vẹn.
              </p>
            </div>
          </div>
          <div className="mt-4 pt-3 border-t border-slate-100">
            <span className="text-[11px] font-medium text-slate-500 uppercase tracking-wider">{copy.report}: </span>
            <span className="font-mono text-xs font-semibold text-slate-800 break-all">{reportHash}</span>
          </div>
        </div>

        {/* Lớp 3: Ranh giới nhãn */}
        <div className="flex flex-col justify-between rounded-xl border border-slate-200 bg-white p-5 shadow-sm">
          <div className="flex items-start gap-3.5">
            <span className="flex h-10 w-10 shrink-0 items-center justify-center rounded-lg bg-emerald-50 text-emerald-700 ring-1 ring-emerald-500/20">
              <Lock className="h-5 w-5" aria-hidden="true" />
            </span>
            <div>
              <h3 className="font-semibold text-xl leading-snug text-slate-900">{copy.trustLeakageTitle}</h3>
              <p className="mt-1 text-base text-slate-600 leading-7">{copy.trustLeakageText}</p>
            </div>
          </div>
        </div>

        {/* Lớp 4: Không VLM */}
        <div className="flex flex-col justify-between rounded-xl border border-slate-200 bg-white p-5 shadow-sm">
          <div className="flex items-start gap-3.5">
            <span className="flex h-10 w-10 shrink-0 items-center justify-center rounded-lg bg-emerald-50 text-emerald-700 ring-1 ring-emerald-500/20">
              <EyeOff className="h-5 w-5" aria-hidden="true" />
            </span>
            <div>
              <h3 className="font-semibold text-xl leading-snug text-slate-900">{copy.trustVlmTitle}</h3>
              <p className="mt-1 text-base text-slate-600 leading-7">{copy.trustVlmText}</p>
            </div>
          </div>
        </div>
      </div>

      <dl className="sr-only">
        <div><dt>{copy.prereg}</dt><dd>{preregHash}</dd></div>
        <div><dt>{copy.report}</dt><dd>{reportHash}</dd></div>
      </dl>
    </section>
  );
}
