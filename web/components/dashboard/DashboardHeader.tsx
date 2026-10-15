 "use client";
import Link from "next/link";
import { RotateCcw } from "lucide-react";
import type { DashboardState } from './useDashboard';

export function DashboardHeader(state: Pick<
  DashboardState,
  "dataset"
  |"demo"
  |"done"
  |"handleStartNew"
  |"items"
  |"job"
  |"jobId"
  |"t1Background"
>) {
  const {
    dataset,
    demo,
    done,
    handleStartNew,
    items,
    job,
    jobId,
    t1Background,
  }=state;
  async function endSession() {
    if (!window.confirm("Xoá toàn bộ dữ liệu đã tải và kết quả của phiên này?")) return;
    const res = await fetch("/api/sessions/current", { method: "DELETE" });
    if (res.ok) window.location.assign("/dashboard");
  }
  return (
    <header className="w-full bg-white border-b border-[#E2E8F0] px-4 sm:px-8 py-3.5 flex flex-wrap items-center justify-between gap-3 shadow-xs sticky top-0 z-40">
      <div className="flex items-center gap-6">
        <Link href="/" className="flex items-center gap-2.5 font-bold text-lg text-slate-900 tracking-tight">
          {/* Cube Logo */}
          <div className="w-7 h-7 rounded-lg bg-blue-600 flex items-center justify-center text-white shadow-xs">
            <svg className="w-4 h-4" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5">
              <path d="M21 16V8a2 2 0 0 0-1-1.73l-7-4a2 2 0 0 0-2 0l-7 4A2 2 0 0 0 3 8v8a2 2 0 0 0 1 1.73l7 4a2 2 0 0 0 2 0l7-4A2 2 0 0 0 21 16z" />
              <polyline points="3.27 6.96 12 12.01 20.73 6.96" />
              <line x1="12" y1="22.08" x2="12" y2="12" />
            </svg>
          </div>
          <span>VCuboidFIT</span>
        </Link>

        <div className="hidden sm:flex flex-col border-l border-slate-200 pl-4">
          <span className="text-[10px] text-slate-400 uppercase tracking-wider font-semibold">Dataset</span>
          <span className="text-xs font-semibold text-slate-800">
            {dataset? dataset.version:"Chưa có dataset"}
          </span>
        </div>
      </div>

      <div className="flex flex-wrap items-center justify-end gap-2 sm:gap-4">
        <Link href="/huong-dan" className="text-xs font-medium text-slate-600 hover:text-blue-700">Hướng dẫn</Link>
        {process.env.NEXT_PUBLIC_VCF_SESSIONS === "1" && (
          <button type="button" onClick={() => void endSession()} className="text-xs font-semibold text-rose-700 hover:text-rose-900">
            Kết thúc phiên
          </button>
        )}
        {(jobId||dataset||items.length>0)&&(
          <button type="button" onClick={handleStartNew} className="inline-flex min-h-9 items-center gap-1.5 rounded-md border border-slate-300 bg-white px-3 text-xs font-semibold text-slate-700 hover:bg-slate-50">
            <RotateCcw className="h-3.5 w-3.5" aria-hidden="true" />
            Nhập dữ liệu mới
          </button>
        )}
        {demo&&(
          <span className="px-2.5 py-0.5 text-[11px] font-semibold rounded-full bg-amber-50 text-amber-700 border border-amber-200">
            Dữ liệu mẫu
          </span>
        )}
        <span className="text-xs text-slate-500 font-mono">
          {jobId? `Job ${jobId}`:"Chưa có job"}
        </span>
        <span role="status" aria-live="polite">
          {t1Background? (
            <span className="px-3 py-1 text-xs font-semibold rounded-full bg-violet-50 text-violet-700 border border-violet-200 flex items-center gap-1.5 animate-pulse">
              <span className="w-1.5 h-1.5 rounded-full bg-violet-500" />
              Tầng 1 đang chạy
            </span>
          ):done? (
            <span className="px-3 py-1 text-xs font-semibold rounded-full bg-emerald-50 text-emerald-700 border border-emerald-200 flex items-center gap-1.5">
              <span className="w-1.5 h-1.5 rounded-full bg-emerald-500" />
              Hoàn tất
            </span>
          ):job.data?.state==="running"? (
            <span className="px-3 py-1 text-xs font-semibold rounded-full bg-blue-50 text-blue-700 border border-blue-200 flex items-center gap-1.5 animate-pulse">
              <span className="w-1.5 h-1.5 rounded-full bg-blue-500" />
              Đang phân tích
            </span>
          ):(
            <span className="px-3 py-1 text-xs font-medium rounded-full bg-slate-100 text-slate-600 border border-slate-200">
              Chờ dữ liệu
            </span>
          )}
        </span>
      </div>
    </header>
  );
}
