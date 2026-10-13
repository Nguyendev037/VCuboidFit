import { FolderOpen, RefreshCw, Trash2 } from "lucide-react";
import { DataError, EmptyState, LoadingState } from "@/components/ui/DataState";
import { ConfirmDialog } from "@/components/ui/ConfirmDialog";
import { formatDuration } from './dashboardState';
import type { DashboardState } from './useDashboard';

export function JobPicker(state: Pick<
  DashboardState,
  "confirmDelete"
  |"deleteTarget"
  |"historyError"
  |"historyNote"
  |"openRun"
  |"recentJobs"
  |"restoring"
  |"setDeleteTarget"
  |"uploading"
>) {
  const {
    confirmDelete,
    deleteTarget,
    historyError,
    historyNote,
    openRun,
    recentJobs,
    restoring,
    setDeleteTarget,
    uploading,
  }=state;
  return (
    <section aria-label="Lần chạy gần đây" className="border-b border-slate-200 pb-4">
      <div className="flex items-center justify-between gap-3 mb-2">
        <h2 className="text-sm font-semibold">Lần chạy gần đây</h2>
        {(recentJobs.data?.length??0)>0&&<button type="button" onClick={() => setDeleteTarget({ kind: "all" })} className="ml-auto px-2 py-1 text-xs text-rose-700 hover:bg-rose-50 rounded">Xoá tất cả</button>}
        <button type="button" title="Làm mới lịch sử" aria-label="Làm mới lịch sử" onClick={() => void recentJobs.refetch()} className="p-2 hover:bg-slate-200 rounded"><RefreshCw size={16} /></button>
      </div>
      {recentJobs.isPending&&<LoadingState />}
      {recentJobs.error&&<DataError error={recentJobs.error} onRetry={() => void recentJobs.refetch()} />}
      {recentJobs.data?.length===0&&<EmptyState message="Chưa có lần chạy. Nạp dữ liệu ở Bước 1 hoặc mở dữ liệu mẫu." />}
      <div role="list" className="max-h-48 overflow-auto divide-y divide-slate-200">
        {recentJobs.data?.map((item) => <div role="listitem" key={item.jobId} className="flex items-center justify-between gap-3 py-2 text-xs">
          <div className="min-w-0"><p className="font-medium break-all">{item.version||item.datasetId} · {item.frames} frame · {item.pipeline==="lidar"? "LiDAR":"Camera"}{item.createdAt&&item.finishedAt? ` · ${formatDuration(Math.max(0, (new Date(item.finishedAt).getTime()-new Date(item.createdAt).getTime())/1000))}`:""}</p><p className="text-slate-500 break-all">{item.jobId} · {item.state==="done"? "Hoàn tất":item.state==="running"? "Đang chạy":item.state==="queued"? "Đang chờ":item.state==="failed"? "Lỗi":"Đã huỷ"}{item.createdAt? ` · ${new Date(item.createdAt).toLocaleString("vi-VN")}`:""}</p></div>
          <div className="flex items-center shrink-0">
            <button type="button" disabled={restoring||uploading} onClick={() => void openRun(item)} className="flex items-center gap-1 px-2 py-2 text-blue-700 hover:bg-blue-50 rounded disabled:opacity-50"><FolderOpen size={16} />Mở</button>
            <button type="button" aria-label="Xoá lần chạy" title={item.state==="queued"||item.state==="running"? "Đang chạy":"Xoá lần chạy"} disabled={item.state==="queued"||item.state==="running"} onClick={() => setDeleteTarget({ kind: "one", jobId: item.jobId })} className="p-2 text-rose-700 hover:bg-rose-50 rounded disabled:opacity-40"><Trash2 size={16} /></button>
          </div>
        </div>)}
      </div>
      {(recentJobs.data?.length??0)>4&&<p className="mt-1 text-[11px] text-slate-600">Cuộn trong danh sách để xem đủ {recentJobs.data?.length} lần chạy</p>}
      {restoring&&<p role="status" className="text-xs text-slate-500 mt-2">Đang mở lần chạy…</p>}
      {historyError&&<p role="alert" className="text-xs text-rose-700 mt-2">{historyError}</p>}
      {historyNote&&<p role="status" className="text-xs text-slate-600 mt-2">{historyNote}</p>}
      <ConfirmDialog
        open={deleteTarget!==null}
        title={deleteTarget?.kind==="all"? "Xoá tất cả lần chạy?":"Xoá lần chạy này?"}
        message="Xoá kết quả chọn 5% và ảnh xem trước của lần chạy; dữ liệu đã tải lên vẫn giữ."
        confirmLabel="Xoá"
        onConfirm={() => void confirmDelete()}
        onCancel={() => setDeleteTarget(null)}
      />
    </section>
  );
}
