import { cancelJob } from "@/lib/api/client";
import { isDatasetUsable } from "@/lib/datasetValidation";
import { DataError, LoadingState } from "@/components/ui/DataState";
import type { DashboardState } from './useDashboard';

export function RunStatus(state: Pick<
  DashboardState,
  "activePipeline"
  |"analysisSteps"
  |"dataset"
  |"job"
  |"jobId"
  |"runDemo"
  |"startJob"
>) {
  const {
    activePipeline,
    analysisSteps,
    dataset,
    job,
    jobId,
    runDemo,
    startJob,
  }=state;
  return (
    <div className="bg-white rounded-xl border border-[#E2E8F0] p-6 shadow-xs flex flex-col gap-4">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div className="flex items-center gap-3">
          <div className="w-7 h-7 rounded-full bg-slate-200 text-slate-700 font-bold text-xs flex items-center justify-center">
            2
          </div>
          <h2 className="font-bold text-base text-slate-900">Phân tích</h2>
        </div>
        <div className="flex w-full flex-wrap gap-2 sm:w-auto sm:ml-auto">
          <button
            type="button"
            onClick={() => void runDemo()}
            disabled={!!jobId}
            className="min-h-10 flex-1 px-3 py-2 bg-white hover:bg-blue-50 disabled:opacity-50 text-blue-800 border border-blue-200 font-medium text-xs rounded-lg transition-colors sm:flex-none focus-visible:outline focus-visible:outline-2 focus-visible:outline-blue-700"
          >
            Chạy thử dữ liệu mẫu
          </button>
          <button
            type="button"
            onClick={() => void startJob()}
            disabled={!isDatasetUsable(dataset)||!!jobId}
            className="min-h-10 flex-1 px-4 py-2 bg-blue-600 hover:bg-blue-700 disabled:bg-slate-200 disabled:text-slate-600 text-white font-medium text-xs rounded-lg shadow-xs transition-colors sm:flex-none focus-visible:outline focus-visible:outline-2 focus-visible:outline-blue-800"
          >
            Chạy phân tích
          </button>
        </div>
      </div>

      <p className="text-xs text-slate-600 leading-relaxed">
        {activePipeline==="lidar"
          ? "Đánh giá độ hiếm hình học và tín hiệu LiDAR, rồi gộp thành điểm S. Cần nạp dữ liệu ở Bước 1 trước."
          :"Đánh giá độ hiếm (Novelty), độ khó (Uncertainty) và mức khớp kịch bản (Query), rồi gộp thành điểm S. Cần nạp dữ liệu ở Bước 1 trước."}
      </p>

      {/* Stepper 5 bước: đường nối đi qua tâm các vòng tròn, nhãn nằm dưới và căn giữa */}
      <ol className={`grid ${activePipeline==="lidar"? "grid-cols-2":"grid-cols-5"} py-2`} aria-label="Tiến trình phân tích" aria-busy={job.isFetching||job.data?.state==="running"}>
        {analysisSteps.map((s, i) => {
          const st=job.data?.stages?.find((x) => x.name===s.stage)?.state??"queued";
          const finished=st==="done";
          const active=st==="running";
          const failed=st==="failed"||st==="cancelled";
          return (
            <li key={s.stage} className="relative flex flex-col items-center text-center px-1">
              {i<analysisSteps.length-1&&(
                <span
                  aria-hidden
                  className={`absolute top-3 left-1/2 h-0.5 w-full ${finished? "bg-blue-600":"bg-slate-200"}`}
                />
              )}
              <span
                className={`relative z-10 w-6 h-6 rounded-full border-2 text-[11px] font-bold flex items-center justify-center ${finished
                    ? "bg-blue-600 border-blue-600 text-white"
                    :active
                      ? "bg-white border-blue-600 text-blue-600 animate-pulse"
                      :failed
                        ? "bg-white border-rose-500 text-rose-600"
                        :"bg-white border-slate-300 text-slate-500"
                  }`}
              >
                {finished? "✓":i+1}
              </span>
              <span className="mt-1.5 text-xs font-semibold text-slate-800 leading-tight">{s.name}</span>
              <span className="text-[10px] leading-tight text-slate-600">{s.hint}</span>
              <span className={`mt-0.5 text-[10px] ${active? "text-blue-600":failed? "text-rose-600":"text-slate-400"}`}>
                {finished? "xong":active? "đang chạy":failed? "lỗi":"chờ"}
              </span>
            </li>
          );
        })}
      </ol>

      {job.isError&&<DataError error={job.error} onRetry={() => void job.refetch()} />}
      {jobId&&job.isPending&&<LoadingState />}

      {/* Trạng thái tiến trình */}
      <div className="pt-2 border-t border-slate-100 flex items-center justify-between text-xs text-slate-500">
        <p data-testid="job-state">
          {job.data
            ? `${job.data.state} · ${job.data.stage} · ${job.data.done}/${job.data.total}`
            :'Chưa chạy — bấm "Chạy phân tích" để bắt đầu.'}
        </p>
        {job.data?.state==="running"&&(
          <button
            onClick={() => void cancelJob(job.data!.jobId).then(() => job.refetch())}
            className="text-rose-600 hover:text-rose-800 font-medium"
          >
            Hủy
          </button>
        )}
      </div>
    </div>
  );
}

