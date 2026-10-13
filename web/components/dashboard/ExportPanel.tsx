import Link from "next/link";
import { RotateCcw } from "lucide-react";
import { exportUrl } from "@/lib/api/client";
import type { DashboardState } from './useDashboard';

export function ExportPanel(state: Pick<
  DashboardState,
  "dataset"
  |"debounced"
  |"handleStartNew"
  |"jobId"
  |"result"
>) {
  const {
    dataset,
    debounced,
    handleStartNew,
    jobId,
    result,
  }=state;
  return (
    <div className="flex items-center gap-2.5">
      <button type="button" onClick={handleStartNew} className="inline-flex min-h-9 items-center gap-1.5 rounded-md border border-slate-300 bg-white px-3 text-xs font-semibold text-slate-700 hover:bg-slate-50">
        <RotateCcw className="h-3.5 w-3.5" aria-hidden="true" />
        Nhập dữ liệu mới
      </button>
      {result&&(
        <a
          href={exportUrl(jobId!, result.selectionId, debounced.budget)}
          className="px-4 py-2 text-xs font-semibold rounded-lg border border-slate-300 bg-white hover:bg-slate-50 text-slate-700 shadow-xs transition-colors flex items-center gap-1.5"
        >
          <svg className="w-3.5 h-3.5" fill="none" stroke="currentColor" viewBox="0 0 24 24" strokeWidth="2">
            <path strokeLinecap="round" strokeLinejoin="round" d="M4 16v1a3 3 0 003 3h10a3 3 0 003-3v-1m-4-4l-4 4m0 0l-4-4m4 4V4" />
          </svg>
          Xuất CSV
        </a>
      )}
      {result&&(
        <Link
          href={`/review/${jobId}?sel=${result.selectionId}&budget=${debounced.budget}&dataset=${dataset?.datasetId??""}`}
          className="px-4 py-2 text-xs font-semibold rounded-lg bg-blue-600 hover:bg-blue-700 text-white shadow-xs transition-colors flex items-center gap-1.5"
        >
          Deep Review
          <svg className="w-3.5 h-3.5" fill="none" stroke="currentColor" viewBox="0 0 24 24" strokeWidth="2">
            <path strokeLinecap="round" strokeLinejoin="round" d="M14 5l7 7m0 0l-7 7m7-7H3" />
          </svg>
        </Link>
      )}
    </div>
  );
}
