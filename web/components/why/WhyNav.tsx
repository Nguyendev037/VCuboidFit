import React from "react";
import Link from "next/link";
import { whyCopy as copy } from "./copy";

function Sunburst({ className = "h-5 w-5 text-sky-600" }: { className?: string }) {
  return (
    <svg className={className} viewBox="0 0 24 24" fill="currentColor" aria-hidden="true">
      <path d="M12 1.5l1.6 5.2 4.2-3.3-1.2 5.3 5.3-1.2-3.3 4.2 5.2 1.6-5.2 1.6 3.3 4.2-5.3-1.2 1.2 5.3-4.2-3.3L12 22.5l-1.6-5.2-4.2 3.3 1.2-5.3-5.3 1.2 3.3-4.2L.2 12l5.2-1.6-3.3-4.2 5.3 1.2-1.2-5.3 4.2 3.3z" />
    </svg>
  );
}

export function WhyNav() {
  return (
    <nav aria-label={copy.home} className="mx-auto flex w-full max-w-6xl items-center justify-between px-4 py-4 sm:px-6">
      <Link href="/" className="flex items-center gap-2 text-base font-semibold tracking-tight text-slate-900 hover:text-sky-700 transition">
        <Sunburst />
        <span>VCuboidFIT · {copy.home}</span>
      </Link>
      <div className="flex items-center gap-3">
        <Link
          href="/"
          className="hidden sm:inline-flex min-h-10 items-center px-4 py-2 text-sm font-medium text-slate-700 hover:text-slate-900 transition"
        >
          {copy.home}
        </Link>
        <Link
          href="/dashboard"
          className="inline-flex min-h-10 items-center rounded-full bg-slate-900 px-5 py-2 text-sm font-semibold text-white shadow-sm hover:bg-slate-700 transition active:scale-[0.98]"
        >
          Dashboard
        </Link>
      </div>
    </nav>
  );
}
