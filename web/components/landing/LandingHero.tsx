"use client";

import Link from "next/link";
import type { CSSProperties } from "react";
import { ArrowRight, Bike, PersonStanding, ShieldAlert, Zap } from "lucide-react";
import { TOPIC_TITLE } from "@/lib/topic";

const SANS = "font-[family-name:var(--font-landing-sans)]";
const SERIF = "font-[family-name:var(--font-landing-serif)]";

function Sunburst({ className = "h-6 w-6" }: { className?: string }) {
  return (
    <svg className={className} viewBox="0 0 24 24" fill="currentColor" aria-hidden="true">
      <path d="M12 1.5l1.6 5.2 4.2-3.3-1.2 5.3 5.3-1.2-3.3 4.2 5.2 1.6-5.2 1.6 3.3 4.2-5.3-1.2 1.2 5.3-4.2-3.3L12 22.5l-1.6-5.2-4.2 3.3 1.2-5.3-5.3 1.2 3.3-4.2L.2 12l5.2-1.6-3.3-4.2 5.3 1.2-1.2-5.3 4.2 3.3z" />
    </svg>
  );
}

/** Header tối giản nằm trên ảnh nền: chỉ có logo và một nút vào Dashboard. */
export function LandingNav() {
  return (
    <nav className="absolute inset-x-0 top-0 z-50 flex items-center justify-between bg-transparent px-6 py-4" aria-label="Điều hướng chính">
      <Link href="/" className="flex min-h-10 items-center gap-2 text-slate-900" aria-label="VCuboidFIT — trang giới thiệu">
        <Sunburst />
        <span className={`landing-enter ${SANS} text-base font-semibold tracking-tight`}>VCuboidFIT</span>
      </Link>
      <Link
        href="/dashboard"
        className={`landing-enter ${SANS} inline-flex min-h-10 items-center rounded-full bg-slate-900 px-5 py-2.5 text-sm font-semibold text-white shadow-sm transition active:scale-[0.97] hover:bg-slate-700`}
      >
        Dashboard
      </Link>
    </nav>
  );
}

export function LandingHero() {
  return (
    <section className="relative min-h-screen w-full overflow-hidden bg-[#f4f7fb] text-slate-900" aria-labelledby="hero-title">
      {/* Ảnh nền: cảnh phố có hộp 3D (nuScenes). Lớp phủ giữ ảnh còn nhìn rõ nhưng chữ vẫn đọc được. */}
      {/* eslint-disable-next-line @next/next/no-img-element */}
      <img src="/hero-nuscenes.jpg" alt="" aria-hidden="true" className="absolute inset-0 h-full w-full object-cover" />
      <div className="absolute inset-0 bg-white/10" aria-hidden="true" />
      <div className="absolute inset-0 bg-[radial-gradient(ellipse_62%_52%_at_50%_46%,rgba(255,255,255,0.62),transparent_100%)]" aria-hidden="true" />
      <div className="absolute inset-0 bg-gradient-to-b from-white/35 via-transparent via-75% to-[#f4f7fb]" aria-hidden="true" />

      <LandingNav />

      <div className="relative z-10 mx-auto flex min-h-screen max-w-5xl flex-col items-center justify-center space-y-10 px-6 py-24 text-center">
        <p
          style={{ "--d": "0s", "--duration": "0.6s" } as CSSProperties}
          className={`landing-enter ${SERIF} text-3xl leading-[1.1] text-slate-800 [text-shadow:0_1px_14px_rgba(255,255,255,0.85)] sm:text-5xl lg:text-[48px]`}
        >
          Từ dữ liệu LiDAR chưa gán nhãn đến
        </p>

        <h1
          id="hero-title"
          style={{ "--d": "0.2s", "--duration": "0.6s" } as CSSProperties}
          className={`landing-enter ${SANS} bg-gradient-to-b from-slate-900 via-slate-900 to-sky-700 bg-clip-text text-6xl font-semibold leading-[0.9] tracking-tighter text-transparent sm:text-8xl lg:text-[136px]`}
        >
          Frame hiếm
          <span className="sr-only"> — {TOPIC_TITLE}</span>
        </h1>

        <p
          style={{ "--d": "0.4s", "--duration": "0.6s" } as CSSProperties}
          className={`landing-enter ${SANS} max-w-3xl text-lg font-medium leading-[1.65] text-slate-900 [text-shadow:0_0_14px_rgba(255,255,255,0.95),0_1px_3px_rgba(255,255,255,0.8)] sm:text-[20px]`}
        >
          {TOPIC_TITLE}.
        </p>

        <div
          style={{ "--d": "0.6s", "--duration": "0.5s" } as CSSProperties}
          className="landing-enter flex flex-col items-center gap-6 sm:flex-row"
        >
          <Link
            href="/dashboard"
            className={`landing-enter ${SANS} group inline-flex items-center rounded-full bg-slate-900 py-2 pl-6 pr-2 shadow-md transition duration-300 hover:scale-105 hover:shadow-[0_8px_24px_rgba(15,23,42,0.25)] active:scale-100`}
          >
            <span className="text-lg font-medium text-white">Mở Dashboard</span>
            <span className="ml-4 flex h-10 w-10 items-center justify-center rounded-full bg-sky-600 transition-colors group-hover:bg-sky-500">
              <ArrowRight className="h-5 w-5 text-white" aria-hidden="true" />
            </span>
          </Link>

          <a
            href="#mo-phong"
            className={`landing-enter ${SANS} group inline-flex min-h-11 items-center gap-2 rounded-lg bg-white/75 px-4 py-2 text-slate-800 shadow-sm ring-1 ring-slate-300/60 backdrop-blur-sm transition-colors hover:bg-white hover:text-slate-900`}
          >
            Xem mô phỏng 3D
            <ArrowRight className="h-4 w-4 transition-transform group-hover:translate-x-1" aria-hidden="true" />
          </a>
        </div>

        <ul
          style={{ "--d": "0.9s", "--duration": "0.6s" } as CSSProperties}
          className={`landing-enter ${SANS} flex flex-wrap justify-center gap-2`}
          aria-label="Nhóm đối tượng VRU"
        >
          {[
            [PersonStanding, "Người đi bộ"],
            [Bike, "Xe đạp"],
            [Zap, "Xe máy"],
            [ShieldAlert, "Phanh khẩn cấp AEB"],
          ].map(([Icon, label]) => {
            const I = Icon as typeof Bike;
            return (
              <li key={label as string} className="inline-flex items-center gap-2 rounded-full bg-white/80 px-3 py-1.5 text-xs text-slate-700 ring-1 ring-slate-300/70 backdrop-blur-sm">
                <I className="h-4 w-4 text-sky-700" aria-hidden="true" />
                {label as string}
              </li>
            );
          })}
        </ul>
      </div>
    </section>
  );
}
