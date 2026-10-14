import React from "react";
import { Moon, CloudRain } from "lucide-react";
import { whyCopy as copy } from "./copy";

export function CameraSection() {
  return (
    <section aria-labelledby="camera-title" className="hud-card p-6 sm:p-10">
      <div className="flex flex-col items-center gap-2 text-center mb-8">
        <p className="font-data text-xs font-semibold uppercase tracking-[0.14em] text-sky-700">Giới hạn đánh giá</p>
        <h2 id="camera-title" className="font-[family-name:var(--font-landing-serif)] text-3xl leading-tight text-slate-900 sm:text-4xl lg:text-5xl">{copy.cameraTitle}</h2>
      </div>

      <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 max-w-2xl mx-auto mb-6">
        <div className="flex items-center gap-4 rounded-xl border border-slate-200 bg-slate-50/80 p-5">
          <span className="flex h-12 w-12 shrink-0 items-center justify-center rounded-xl bg-blue-50 text-blue-700 ring-1 ring-blue-500/20">
            <Moon className="h-6 w-6" aria-hidden="true" />
          </span>
          <div>
            <div className="text-xs font-medium text-slate-500 uppercase tracking-wider">{copy.cameraNightLabel}</div>
            <div className="text-3xl font-display font-semibold text-slate-900 tabular-nums">{copy.cameraNightVal}</div>
          </div>
        </div>

        <div className="flex items-center gap-4 rounded-xl border border-slate-200 bg-slate-50/80 p-5">
          <span className="flex h-12 w-12 shrink-0 items-center justify-center rounded-xl bg-blue-50 text-blue-700 ring-1 ring-blue-500/20">
            <CloudRain className="h-6 w-6" aria-hidden="true" />
          </span>
          <div>
            <div className="text-xs font-medium text-slate-500 uppercase tracking-wider">{copy.cameraRainLabel}</div>
            <div className="text-3xl font-display font-semibold text-slate-900 tabular-nums">{copy.cameraRainVal}</div>
          </div>
        </div>
      </div>

      <div className="mx-auto max-w-3xl rounded-xl border border-slate-200/80 bg-white p-5 text-center">
        <p className="text-lg leading-8 text-slate-600">
          {copy.camera}
        </p>
      </div>
    </section>
  );
}
