import React from "react";
import Link from "next/link";
import { ArrowRight } from "lucide-react";
import { whyCopy as copy } from "./copy";

export function WhyHero() {
  return (
    <header className="relative w-full overflow-hidden bg-[#f4f7fb] text-slate-900">
      {/* Nền phong cảnh nuScenes dùng CSS background-image để bảo toàn kiểm thử figure */}
      <div
        className="absolute inset-0 bg-cover bg-center opacity-20"
        style={{ backgroundImage: "url('/hero-nuscenes.jpg')" }}
        aria-hidden="true"
      />
      <div className="absolute inset-0 bg-gradient-to-b from-white/70 via-white/50 to-[#f4f7fb]" aria-hidden="true" />

      <div className="relative z-10 mx-auto flex max-w-5xl flex-col items-center justify-center px-4 py-16 text-center sm:px-6 sm:py-24">
        <p className="font-data text-xs font-semibold uppercase tracking-[0.16em] text-sky-700">
          {copy.eyebrow}
        </p>

        <h1 className="mt-5 font-[family-name:var(--font-landing-serif)] text-4xl sm:text-6xl lg:text-[70px] font-normal leading-[1.12] tracking-tight text-slate-900">
          {copy.title}
        </h1>

        <p className="mt-6 max-w-2xl text-lg sm:text-xl font-medium leading-relaxed text-slate-700">
          {copy.subtitle}
        </p>

        {/* Đúng 2 nút hành động theo yêu cầu thiết kế */}
        <div className="mt-8 flex flex-col items-stretch gap-4 sm:flex-row sm:items-center">
          <Link
            href="/dashboard"
            className="inline-flex min-h-12 items-center justify-center gap-2 rounded-full bg-slate-900 px-7 text-base font-semibold text-white shadow-md transition hover:bg-slate-800 active:scale-[0.98]"
          >
            {copy.demo}
            <ArrowRight className="h-4 w-4" aria-hidden="true" />
          </Link>
          <a
            href="#bang-chung"
            className="inline-flex min-h-12 items-center justify-center gap-2 rounded-full bg-white/95 px-6 text-base font-semibold text-slate-800 ring-1 ring-slate-300 shadow-sm transition hover:bg-white active:scale-[0.98]"
          >
            {copy.evidenceTitle}
          </a>
        </div>
      </div>
    </header>
  );
}
