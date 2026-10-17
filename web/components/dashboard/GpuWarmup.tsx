"use client";

import { createContext, useContext, useEffect, useRef, useState } from "react";
import type { ReactNode } from "react";
import { Loader2 } from "lucide-react";
import { GpuWarmupController, type GpuStatus } from "./gpuWarmupState";

const GpuContext = createContext<GpuStatus>({ state: "starting", reason: null, since: null });
export const useGpuStatus = () => useContext(GpuContext);

export function GpuWarmup({ children }: { children: ReactNode }) {
  const online = process.env.NEXT_PUBLIC_VCF_SESSIONS === "1";
  const controller = useRef<GpuWarmupController | null>(null);
  const [snapshot, setSnapshot] = useState({ overlay: true, status: { state: "starting", reason: null, since: null } as GpuStatus });
  useEffect(() => {
    if (!online) return;
    // Wrap fetch: an unbound window.fetch called as a method throws "Illegal invocation".
    controller.current ??= new GpuWarmupController((input, init) => fetch(input, init), () => document.visibilityState === "visible");
    return controller.current.start(setSnapshot);
  }, [online]);
  return (
    <GpuContext.Provider value={snapshot.status}>
      {children}
      {online && snapshot.overlay && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-slate-950/50 p-4" role="status" aria-live="polite" data-testid="gpu-warm-overlay">
          <div className="flex w-full max-w-sm flex-col items-center gap-3 rounded-xl bg-white px-6 py-7 text-center shadow-xl">
            <Loader2 className="h-8 w-8 animate-spin text-blue-600" aria-hidden="true" />
            <p className="text-sm font-semibold text-slate-900">Đang khởi động model, vui lòng đợi ít phút…</p>
            <p className="text-xs leading-relaxed text-slate-500">Trong lúc chờ, bạn vẫn có thể tải dữ liệu và chạy phân tích cơ bản.</p>
            <button type="button" onClick={() => controller.current?.skip()} className="mt-1 min-h-9 rounded-lg border border-slate-300 px-4 text-xs font-semibold text-slate-700 hover:bg-slate-50">Tiếp tục dùng</button>
          </div>
        </div>
      )}
    </GpuContext.Provider>
  );
}
