"use client";

import { CheckCircle2, CircleAlert, Clock, Cpu, Loader2, Sparkles } from "lucide-react";
import type { Tier0Info, Tier1Info } from "@/lib/api/types";
import { TIER1_LABEL, formatSeconds } from "@/lib/tierStatus";

export interface TierStatusProps {
  tier0?: Tier0Info | null;
  tier1?: Tier1Info | null;
  /** Đang gửi yêu cầu chạy Tầng 1. */
  runBusy?: boolean;
  runError?: string | null;
  onRunTier1?: () => void;
}

const BADGE: Record<string, string> = {
  ok: "border-emerald-200 bg-emerald-50 text-emerald-700",
  busy: "border-blue-200 bg-blue-50 text-blue-700",
  warn: "border-amber-200 bg-amber-50 text-amber-800",
  bad: "border-red-200 bg-red-50 text-red-700",
  idle: "border-slate-200 bg-slate-50 text-slate-600",
};

function Badge({ tone, children }: { tone: keyof typeof BADGE; children: React.ReactNode }) {
  return <span className={`shrink-0 rounded-full border px-2 py-0.5 text-[10px] font-semibold ${BADGE[tone]}`}>{children}</span>;
}

function Row({ label, value }: { label: string; value: React.ReactNode }) {
  return (
    <div className="flex items-baseline justify-between gap-2">
      <dt className="text-slate-500">{label}</dt>
      <dd className="text-right font-medium text-slate-800">{value}</dd>
    </div>
  );
}

function Tier0Card({ tier0 }: { tier0?: Tier0Info | null }) {
  const state = tier0?.state ?? "queued";
  const tone = state === "done" ? "ok" : state === "failed" ? "bad" : state === "running" ? "busy" : "idle";
  const label = state === "done" ? "Đã chạy" : state === "failed" ? "Lỗi" : state === "running" ? "Đang chạy" : "Đang chờ";
  const kept = tier0?.nKeep != null && tier0?.nTotal != null ? `${tier0.nKeep} / ${tier0.nTotal}` : "—";
  const dropped = tier0?.nKeep != null && tier0?.nTotal != null ? tier0.nTotal - tier0.nKeep : null;
  return (
    <section data-testid="tier0-card" className="flex flex-col gap-2 rounded-lg border border-slate-200 bg-white p-2.5">
      <header className="flex items-start justify-between gap-2">
        <span className="flex items-center gap-1.5 font-semibold text-slate-800">
          <Cpu className="h-3.5 w-3.5 text-slate-500" aria-hidden="true" />
          Tầng 0 · Cơ bản
        </span>
        <Badge tone={tone}>{label}</Badge>
      </header>
      <p className="text-[10px] leading-snug text-slate-500">
        Đo hình dạng point cloud của từng frame trên CPU, không cần model. Frame càng khác các frame giống nó nhất thì càng hiếm.
      </p>
      <dl className="flex flex-col gap-1">
        <Row label="Frame đủ điểm LiDAR" value={kept} />
        {dropped != null && dropped > 0 && <Row label="Bị loại (quá ít điểm)" value={dropped} />}
        <Row label="Thời gian chạy" value={formatSeconds(tier0?.durationSec) ?? "—"} />
        <Row label="Tiêu chí cung cấp" value="Hiếm trong dữ liệu" />
      </dl>
    </section>
  );
}

function Tier1Card({ tier1, runBusy, runError, onRunTier1 }: Omit<TierStatusProps, "tier0">) {
  const state = tier1?.state;
  const active = state === "queued" || state === "running";
  const tone = !state ? "idle" : state === "done" ? "ok" : active ? "busy" : state === "failed" ? "bad" : state === "skipped" ? "warn" : "idle";
  const canRun = !!tier1?.canRun && !active && state !== "done";
  return (
    <section data-testid="tier1-card" className="flex flex-col gap-2 rounded-lg border border-slate-200 bg-white p-2.5">
      <header className="flex items-start justify-between gap-2">
        <span className="flex items-center gap-1.5 font-semibold text-slate-800">
          <Sparkles className="h-3.5 w-3.5 text-violet-500" aria-hidden="true" />
          Tầng 1 · Nâng cao
        </span>
        <Badge tone={tone}>{state ? TIER1_LABEL[state] : "Chưa rõ"}</Badge>
      </header>
      <p className="text-[10px] leading-snug text-slate-500">
        Model PointPillars đã học (chạy GPU) cho thêm hai tiêu chí: Lạ với model và Model chưa chắc chắn.
      </p>
      {active && (
        <p role="status" className="flex items-center gap-1.5 text-blue-700">
          <Loader2 className="h-3.5 w-3.5 animate-spin" aria-hidden="true" />
          {state === "queued" ? "Đang chờ tới lượt chạy…" : "Đang chạy trên GPU, thường mất vài phút. Kết quả Tầng 0 vẫn dùng được."}
        </p>
      )}
      {state === "done" && (
        <p className="flex items-start gap-1.5 text-emerald-700">
          <CheckCircle2 className="mt-px h-3.5 w-3.5 shrink-0" aria-hidden="true" />
          {tier1?.novSource === "none"
            ? "Đã có Model chưa chắc chắn. Lạ với model chưa khả dụng cho dữ liệu này (thiếu frame seed)."
            : "Đã có đủ tín hiệu. Chọn “Nâng cao” ở trên để dùng."}
        </p>
      )}
      {tier1?.reason && (state === "skipped" || state === "failed") && (
        <p className="flex items-start gap-1.5 text-amber-800">
          <CircleAlert className="mt-px h-3.5 w-3.5 shrink-0" aria-hidden="true" />
          {tier1.reason}
        </p>
      )}
      {state === "ready" && (
        <p className="flex items-start gap-1.5 text-slate-700">
          <Clock className="mt-px h-3.5 w-3.5 shrink-0" aria-hidden="true" />
          Máy đã có model. Tầng 1 chạy cùng lúc khi phân tích.
        </p>
      )}
      {runError && <p role="alert" className="text-red-700">{runError}</p>}
      {canRun && onRunTier1 && (
        <button
          type="button"
          onClick={onRunTier1}
          disabled={runBusy}
          className="min-h-9 rounded-lg bg-violet-600 px-3 text-xs font-semibold text-white hover:bg-violet-700 disabled:opacity-50"
        >
          {state === "failed" ? "Chạy lại Tầng 1 trên máy này" : "Chạy Tầng 1 trên máy này"}
        </button>
      )}
      {!tier1?.canRun && state !== "done" && !active && (
        <p className="text-[10px] text-slate-500">Máy này chưa chạy được Tầng 1. Có thể dùng Colab bên dưới nếu đã bật cầu nối.</p>
      )}
    </section>
  );
}

/** Thẻ trạng thái hai tầng của một lần chạy LiDAR (plan 09 §8). */
export function TierStatus(props: TierStatusProps) {
  return (
    <div data-testid="tier-status" className="grid grid-cols-1 gap-2">
      <Tier0Card tier0={props.tier0} />
      <Tier1Card tier1={props.tier1} runBusy={props.runBusy} runError={props.runError} onRunTier1={props.onRunTier1} />
    </div>
  );
}
