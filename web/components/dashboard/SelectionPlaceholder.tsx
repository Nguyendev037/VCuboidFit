import { METRICS } from "@/lib/glossary";
import type { DashboardState } from './useDashboard';

export function SelectionPlaceholder(state: Pick<
  DashboardState,
  "activePipeline"
>) {
  const {
    activePipeline,
  }=state;
  return (
    <div className="bg-white rounded-xl border border-[#E2E8F0] p-6 shadow-xs flex flex-col gap-4 opacity-70">
      <div className="flex items-center gap-3">
        <div className="w-7 h-7 rounded-full bg-slate-200 text-slate-700 font-bold text-xs flex items-center justify-center">
          3
        </div>
        <h2 className="font-bold text-base text-slate-900">Kết quả</h2>
      </div>
      <p className="text-xs text-slate-500">
        Sau khi phân tích: 4 thẻ số, biểu đồ 6 method, lưới 12 frame đầu và nút Deep Review.
      </p>
      <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
        {[
          "Đã chọn",
          METRICS.recall.label,
          activePipeline==="lidar"? METRICS.nRecall.label:METRICS.uplift.label,
          activePipeline==="lidar"? METRICS.sceneRecall.label:METRICS.redundancy.label
        ].map((label) => (
          <div key={label} className="p-4 bg-slate-50 rounded-xl border border-slate-200 text-center flex flex-col items-center justify-center">
            <span className="text-xs text-slate-500 font-medium leading-tight line-clamp-2">{label}</span>
            <p className="text-xl font-bold text-slate-400 mt-1">—</p>
          </div>
        ))}
      </div>
    </div>
  );
}
