"use client";

import type { TierStatusProps } from "@/components/TierStatus";
import { TIER1_LABEL } from "@/lib/tierStatus";
import { useGpuStatus } from "./GpuWarmup";

export function OnlineTierStatus({ tier0, tier1 }: TierStatusProps) {
  const gpu = useGpuStatus();
  const label = gpu.state === "ready" ? "GPU sẵn sàng"
    : gpu.state === "starting" ? "GPU đang khởi động (~10–15 phút)"
    : gpu.state === "idle" ? "GPU tắt"
    : gpu.state === "disabled" ? "Bản này không có GPU tự động"
    : `Không bật được GPU: ${gpu.reason ?? "không rõ lý do"}`;
  return (
    <div className="grid gap-2 text-xs" data-testid="tier-status">
      <section className="rounded-lg border border-slate-200 p-3" data-testid="tier0-card">
        <h3 className="font-semibold">Tầng 0 · Cơ bản</h3>
        <p className="mt-1">{tier0?.state === "done" ? "Đã chạy" : tier0?.state === "running" ? "Đang chạy" : tier0?.state === "failed" ? "Lỗi" : "Đang chờ"} · CPU, không cần GPU</p>
        {tier0?.nKeep != null && <p>{tier0.nKeep} / {tier0.nTotal ?? "—"} frame</p>}
      </section>
      <section className="rounded-lg border border-slate-200 p-3" data-testid="tier1-card">
        <h3 className="font-semibold">Tầng 1 · Nâng cao</h3>
        <p role="status" aria-live="polite" className="mt-1">{label}</p>
        {tier1?.state && tier1.state !== "skipped" && <p className="mt-1">Lần chạy: {TIER1_LABEL[tier1.state]}</p>}
        {gpu.state === "error" && gpu.reason === "no-offer" && <p className="mt-1">Chạy Tầng 0 hoặc thử lại sau.</p>}
      </section>
    </div>
  );
}
