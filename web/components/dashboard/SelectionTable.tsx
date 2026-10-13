import Link from "next/link";
import { recallRows, stageLabel } from "@/lib/constants";
import { ExportImages } from "@/components/review/ExportImages";
import { warningLabel } from "@/lib/glossary";
import { DataError, LoadingState } from "@/components/ui/DataState";
import { METRICS, RARITY_COMPARISON, SETTINGS, gtTagLabel, reasonText } from "@/lib/glossary";
import { Tooltip } from "@/components/ui/Tooltip";
import { PRESET_LABELS, formatBytes, formatDuration, pct } from './dashboardState';
import type { DashboardState } from './useDashboard';
import { ExportPanel } from './ExportPanel';

export function SelectionTable(state: Pick<
  DashboardState,
  "activePipeline"
  |"advancedParams"
  |"budget"
  |"dataset"
  |"debounced"
  |"handleStartNew"
  |"items"
  |"job"
  |"jobId"
  |"m"
  |"preset"
  |"result"
  |"selection"
>) {
  const {
    activePipeline,
    advancedParams,
    budget,
    dataset,
    debounced,
    handleStartNew,
    items,
    job,
    jobId,
    m,
    preset,
    result,
    selection,
  }=state;
  return (
    <>
      {/* Tóm tắt Bước 1 & Bước 2 */}
      <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
        <div className="bg-white rounded-xl border border-[#E2E8F0] p-4 shadow-xs flex items-center justify-between">
          <div className="flex items-center gap-3">
            <div className="w-6 h-6 rounded-full bg-blue-600 text-white flex items-center justify-center text-xs">
              ✓
            </div>
            <div>
              <h3 className="font-bold text-xs text-slate-900">Bước 1 · Nạp dữ liệu</h3>
              <p className="text-[11px] text-slate-500 mt-0.5">
                {dataset?.scenes??0} scene · {dataset?.frames??0} frame · {Object.values(dataset?.imagesByCam??{}).filter((count) => count>0).length} camera · LiDAR {dataset?.hasLidar? "✓":"—"} · Nhãn {dataset?.hasAnnotations? "✓":"—"} · {dataset?.warnings.length??0} cảnh báo
              </p>
            </div>
          </div>
          <span className="px-2.5 py-0.5 rounded-full border border-emerald-500 text-emerald-700 text-[11px] font-mono font-medium">
            {items.length>0
              ? `${items.length} file · ${formatBytes(items.reduce((sum, item) => sum+item.total, 0))}`
              :dataset?.version??"Dữ liệu mẫu"}
          </span>
        </div>

        <div className="bg-white rounded-xl border border-[#E2E8F0] p-4 shadow-xs flex items-center justify-between">
          <div className="flex items-center gap-3">
            <div className="w-6 h-6 rounded-full bg-blue-600 text-white flex items-center justify-center text-xs">
              ✓
            </div>
            <div>
              <h3 className="font-bold text-xs text-slate-900">Bước 2 · Phân tích</h3>
              <p className="text-[11px] text-slate-500 mt-0.5 font-mono">
                {(job.data?.stages??[])
                  .filter((stage) => stage.state==="done")
                  .map((stage) => `${stageLabel(stage.name, activePipeline)} ${formatDuration(stage.durationSec??0)}`)
                  .join(" · ")||"Chưa có số liệu thời gian"}
              </p>
            </div>
          </div>
          <span className="px-2.5 py-0.5 rounded-full border border-emerald-500 text-emerald-700 text-[11px] font-mono font-medium">
            {formatDuration((job.data?.stages??[])
              .filter((stage) => stage.state==="done")
              .reduce((total, stage) => total+(stage.durationSec??0), 0))}
          </span>
        </div>
      </div>

      {/* Thẻ Kết quả chính */}
      <div className="bg-white rounded-xl border border-[#E2E8F0] p-6 shadow-xs flex flex-col gap-6">
        <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4">
          <div className="flex items-center gap-3">
            <div className="w-7 h-7 rounded-full bg-blue-600 text-white font-bold text-xs flex items-center justify-center">
              3
            </div>
            <div className="flex items-center gap-2">
              <h2 className="font-bold text-base text-slate-900">Kết quả</h2>
              <span className="px-2.5 py-0.5 rounded-full bg-blue-50 text-blue-700 text-xs font-medium border border-blue-200">
                {PRESET_LABELS[preset]?.title||preset} · ngân sách {pct(budget)}
              </span>
              {advancedParams&&(
                <span className="px-2 py-0.5 rounded-full bg-slate-100 text-slate-700 text-[11px] font-semibold border border-slate-200">
                  Tuỳ chỉnh
                </span>
              )}
            </div>
          </div>

          <ExportPanel {...{ dataset, debounced, handleStartNew, jobId, result }} />
        </div>

        {result&&<section className="space-y-3 text-sm"><div className="grid grid-cols-2 gap-3 sm:grid-cols-4">{[
          ["Ứng viên hiếm (dự đoán)", result.tagSummary? `R1: ${result.tagSummary.R1} · R2: ${result.tagSummary.R2} · R3: ${result.tagSummary.R3}`:"Chưa có"],
          ["Tương tác (dự đoán)", result.tagSummary?.I??"Chưa có"],
          ["Bối cảnh (dự đoán)", result.contextSummary? `Đêm: ${result.contextSummary.night} · Chói: ${result.contextSummary.glare} · Mưa: ${result.contextSummary.rain}`:"Chưa có"],
          ["Cần xem lại", result.contextSummary?.review??"Chưa có"],
        ].map(([label, value]) => <div key={label} className="rounded-xl border bg-slate-50 p-3"><p>{label}</p><strong>{value}</strong></div>)}</div>
          {result.gateSummary&&<p>Gate toàn pool: hợp lệ {result.gateSummary.valid} · đáng ngờ {result.gateSummary.suspect} · ngoại lệ {result.gateSummary.outlier}</p>}
          {result.warningCodes?.map(code => <p key={code} role="status" className="text-amber-800">{warningLabel(code)}</p>)}
          <ExportImages jobId={jobId!} sid={result.selectionId} budget={debounced.budget} />
          <Link className="text-blue-700 underline" href={`/review/context?job=${encodeURIComponent(jobId!)}&sel=${encodeURIComponent(result.selectionId)}`}>Hàng đợi duyệt bối cảnh</Link></section>}
        {/* 4 Thẻ số theo Figma 02 */}
        <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
          <div className="p-4 bg-slate-50/70 rounded-xl border border-slate-200 flex flex-col">
            <div className="flex items-start gap-1">
              <span className="text-xs text-slate-700 font-medium leading-tight line-clamp-2">Đã chọn</span>
              <Tooltip label={SETTINGS.budget.label} content={SETTINGS.budget.tooltip} />
            </div>
            <p className="text-2xl font-bold font-mono text-slate-900 mt-1" data-testid="metric-selected">
              {result? `${result.budgetB} / ${result.poolSize}`:"Đang đo"}
            </p>
            <span className="text-[11px] text-slate-400 mt-1 block">
              {result? `${((result.budgetB/result.poolSize)*100).toFixed(1).replace(".", ",")} % của pool`:"Đang đo"}
            </span>
          </div>

          <div className="p-4 bg-slate-50/70 rounded-xl border border-slate-200 flex flex-col">
            <div className="flex items-start gap-1">
              <span className="text-xs text-slate-700 font-medium leading-tight line-clamp-2">{METRICS.recall.label}</span>
              <Tooltip label={METRICS.recall.label} content={METRICS.recall.tooltip} />
            </div>
            <p className="text-2xl font-bold font-mono text-emerald-600 mt-1" data-testid="metric-recall">
              {m? pct(m.hybrid.recall):"Chưa có đánh giá"}
            </p>
            <span className="text-[11px] text-slate-400 mt-1 block">
              {m?.random? `Random ${pct(m.random.mean.recall)} ± ${pct(m.random.std.recall)}`:"Chưa có đối chứng"}
            </span>
            <span className="mt-1 flex items-start gap-1 text-[10px] leading-snug text-slate-500">
              {dataset?.hasAnnotations? RARITY_COMPARISON.tooltip:RARITY_COMPARISON.noLabels}
              <Tooltip label={RARITY_COMPARISON.label} content={dataset?.hasAnnotations? RARITY_COMPARISON.tooltip:RARITY_COMPARISON.noLabels} />
            </span>
          </div>

          <div className="p-4 bg-slate-50/70 rounded-xl border border-slate-200 flex flex-col">
            <div className="flex items-start gap-1">
              <span className="text-xs text-slate-700 font-medium leading-tight line-clamp-2">{activePipeline==="lidar"? METRICS.nRecall.label:METRICS.uplift.label}</span>
              <Tooltip label={activePipeline==="lidar"? METRICS.nRecall.label:METRICS.uplift.label} content={activePipeline==="lidar"? METRICS.nRecall.tooltip:METRICS.uplift.tooltip} />
            </div>
            <p className="text-2xl font-bold font-mono text-emerald-600 mt-1" data-testid="metric-uplift">
              {m? (activePipeline==="lidar"? pct(m.hybrid.nRecall??m.hybrid.recall):`${m.hybrid.uplift.toFixed(1)}×`):"Chưa có đánh giá"}
            </p>
            <span className="text-[11px] text-slate-400 mt-1 block">{activePipeline==="lidar"? "chuẩn hoá theo nhóm":"so với random"}</span>
          </div>

          <div className="p-4 bg-slate-50/70 rounded-xl border border-slate-200 flex flex-col">
            <div className="flex items-start gap-1">
              <span className="text-xs text-slate-700 font-medium leading-tight line-clamp-2">{activePipeline==="lidar"? METRICS.sceneRecall.label:METRICS.redundancy.label}</span>
              <Tooltip label={activePipeline==="lidar"? METRICS.sceneRecall.label:METRICS.redundancy.label} content={activePipeline==="lidar"? METRICS.sceneRecall.tooltip:METRICS.redundancy.tooltip} />
            </div>
            <p className="text-2xl font-bold font-mono text-slate-900 mt-1" data-testid="metric-redundancy">
              {m? (activePipeline==="lidar"? pct(m.hybrid.sceneRecall??m.hybrid.coverage):m.hybrid.redundancy.toFixed(2).replace(".", ",")):"Chưa có đánh giá"}
            </p>
            <span className="text-[11px] text-slate-400 mt-1 block">{activePipeline==="lidar"? `${m?.hybrid.nBoxes??0} box`:"thấp hơn là tốt"}</span>
          </div>
        </div>

        {/* Biểu đồ Recall theo Method (Figma 02) */}
        <div className="p-4 bg-slate-50/50 rounded-xl border border-slate-200 flex flex-col gap-3">
          {selection.isPending&&<LoadingState />}
          {selection.isError&&<DataError error={selection.error} onRetry={() => void selection.refetch()} />}
          <div className="flex flex-wrap items-center justify-between gap-2 text-xs font-semibold text-slate-800">
            <span className="inline-flex items-center gap-1">Tỉ lệ bắt frame hiếm theo cách chọn <Tooltip label={METRICS.recall.label} content={METRICS.recall.tooltip} /></span>
            <span className="text-slate-400 font-normal">Random trung bình 5 % ± 2</span>
          </div>
          <div className="space-y-2 text-xs">
            {recallRows(activePipeline, m).map((row) => (
              <div key={row.name} className="flex items-center gap-3">
                <span className="w-32 text-slate-600 truncate font-medium text-[11px]">{row.name}</span>
                <div className="flex-1 h-3 bg-slate-200/80 rounded-full overflow-hidden">
                  <div
                    className={`h-full rounded-full transition-all duration-300 ${row.isPrimary? "bg-blue-600":"bg-slate-400"
                      }`}
                    style={{ width: `${Math.round(row.val*100)}%` }}
                  />
                </div>
                <span className="w-10 text-right font-mono text-slate-700 text-[11px] font-semibold">
                  {Math.round(row.val*100)} %
                </span>
              </div>
            ))}
          </div>
        </div>

        {/* Lưới 12 Thumbnail theo Figma 02 */}
        <div>
          <h3 className="text-xs font-bold text-slate-800 uppercase tracking-wider mb-3">
            {Math.min(12, result?.preview.length??0)} Frame tiêu biểu đã chọn
          </h3>
          {result&&result.preview.length===0? (
            <p role="status" className="rounded-lg border border-slate-200 bg-slate-50 p-4 text-center text-sm text-slate-700">Chưa có frame xem trước cho lựa chọn này.</p>
          ):<div className="grid grid-cols-2 sm:grid-cols-3 md:grid-cols-4 lg:grid-cols-6 gap-3">
            {(result?.preview??[]).slice(0, 12).map((f) => (
              <Link
                key={f.sampleToken}
                href={`/review/${jobId}?sel=${result?.selectionId}&budget=${debounced.budget}&frame=${f.sampleToken}&dataset=${dataset?.datasetId??""}`}
                data-testid="thumb"
                className="group bg-white border border-slate-200 hover:border-blue-500 rounded-xl overflow-hidden shadow-xs hover:shadow-md transition-all flex flex-col"
              >
                <div className="aspect-video w-full bg-slate-100 relative overflow-hidden">
                  {/* eslint-disable-next-line @next/next/no-img-element */}
                  <img
                    src={f.thumbUrl}
                    alt={`#${f.rank} ${f.sceneName}`}
                    className="w-full h-full object-cover group-hover:scale-105 transition-transform duration-200"
                  />
                  <span className="absolute top-1.5 left-1.5 bg-black/75 backdrop-blur-sm text-white font-mono text-[10px] font-bold px-1.5 py-0.5 rounded">
                    #{f.rank}
                  </span>
                </div>
                <div className="p-2 flex flex-col gap-1 justify-between flex-1">
                  <p className="text-[11px] font-medium text-slate-800 line-clamp-1">
                    {reasonText(f.reason)}
                  </p>
                  <div className="flex items-center gap-1 flex-wrap">
                    {(activePipeline==="lidar"? f.tags??[]:["Hiếm", ...((f.tags?.includes("Khó")||(typeof f.rUnc==="number"&&f.rUnc>=0.8))? ["Khó"]:[])]).map((tag) => (
                      <span key={tag} className="inline-flex items-center gap-1 text-[9px] px-1.5 py-0.5 bg-blue-50 text-blue-700 rounded font-medium">
                        {activePipeline==="lidar"? gtTagLabel(tag):tag}
                      </span>
                    ))}
                  </div>
                </div>
              </Link>
            ))}
          </div>}
        </div>
      </div>
    </>
  );
}
