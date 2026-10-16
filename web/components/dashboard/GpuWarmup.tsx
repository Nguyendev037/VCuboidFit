"use client";

import { createContext, useContext, useEffect, useRef, useState } from "react";
import type { ReactNode } from "react";
import { GpuWarmupController, type GpuStatus } from "./gpuWarmupState";

const GpuContext = createContext<GpuStatus>({ state: "starting", reason: null, since: null });
export const useGpuStatus = () => useContext(GpuContext);

export function GpuWarmup({ children }: { children: ReactNode }) {
  const online = process.env.NEXT_PUBLIC_VCF_SESSIONS === "1";
  const controller = useRef<GpuWarmupController | null>(null);
  const [snapshot, setSnapshot] = useState({ overlay: true, status: { state: "starting", reason: null, since: null } as GpuStatus });
  useEffect(() => {
    if (!online) return;
    controller.current ??= new GpuWarmupController(fetch, () => document.visibilityState === "visible");
    return controller.current.start(setSnapshot);
  }, [online]);
  return (
    <GpuContext.Provider value={snapshot.status}>
      {children}
      {online && snapshot.overlay && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-slate-950/50 p-4" role="status" aria-live="polite" data-testid="gpu-warm-overlay">
          <div className="max-w-md rounded-xl bg-white p-6 text-sm text-slate-800 shadow-xl">
            <p className="font-semibold">Đang chuẩn bị máy GPU…</p>
            <p className="mt-2">4 giây chỉ để gửi lệnh bật. GPU lần đầu dự kiến cần khoảng 10–15 phút, chưa đo. Bạn có thể dùng Tầng 0 ngay sau bước này.</p>
            <button type="button" onClick={() => controller.current?.skip()} className="mt-4 min-h-10 rounded-lg border border-slate-300 px-4 font-semibold">Bỏ qua</button>
          </div>
        </div>
      )}
    </GpuContext.Provider>
  );
}
