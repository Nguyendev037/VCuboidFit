import React from "react";
import Link from "next/link";
import { ArrowRight } from "lucide-react";
import { whyCopy as copy } from "./copy";

export function WhyCta() {
  return (
    <section aria-labelledby="cta-title" className="mx-auto w-full max-w-6xl">
      <div className="relative overflow-hidden rounded-2xl bg-gradient-to-br from-slate-900 via-slate-800 to-sky-900 px-6 py-14 text-center text-white shadow-xl sm:px-14 sm:py-16">
        <div aria-hidden className="pointer-events-none absolute -left-24 -top-24 h-72 w-72 rounded-full bg-sky-500/25 blur-3xl" />
        <div aria-hidden className="pointer-events-none absolute -bottom-24 -right-16 h-72 w-72 rounded-full bg-emerald-400/20 blur-3xl" />

        <div className="relative mx-auto flex max-w-2xl flex-col items-center gap-5">
          <p className="font-data text-xs font-medium uppercase tracking-[0.14em] text-sky-300">
            Hành động tiếp theo
          </p>
          <h2 id="cta-title" className="font-display text-balance text-3xl font-semibold leading-tight sm:text-4xl">
            {copy.ctaTitle}
          </h2>
          <p className="text-balance text-base leading-7 text-slate-300">
            {copy.ctaSubtitle}
          </p>
          <div className="mt-2 flex flex-col items-stretch gap-3 sm:flex-row sm:items-center">
            <Link
              href="/dashboard"
              className="inline-flex min-h-12 items-center justify-center gap-2 rounded-full bg-white px-8 text-base font-semibold text-slate-900 transition hover:bg-sky-50 active:scale-[0.98]"
            >
              {copy.demo}
              <ArrowRight className="h-4 w-4" aria-hidden="true" />
            </Link>
            <Link
              href="/huong-dan"
              className="inline-flex min-h-12 items-center justify-center rounded-full px-8 text-base font-medium text-white ring-1 ring-white/35 transition hover:bg-white/10 active:scale-[0.98]"
            >
              {copy.guide}
            </Link>
          </div>
        </div>
      </div>
    </section>
  );
}
