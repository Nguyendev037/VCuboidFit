"use client";

import { useEffect, useState } from "react";

import { uploadSelection } from "./uploadSelection";
import { getUploadLimits } from "@/lib/api/client";
import { UPLOAD_HELP } from "@/lib/glossary";
import { checkUploadLimits, checkProgressPct, formatEta, PHASE_LABELS } from "@/lib/upload";
import type { UploadLimitVerdict, UploadLimits } from "@/lib/upload";
import { isDatasetUsable, datasetValidationMessage } from "@/lib/datasetValidation";
import { Tooltip } from "@/components/ui/Tooltip";
import { formatBytes, pct } from './dashboardState';
import type { DashboardState } from './useDashboard';

/** Đường dẫn trong `UPLOAD_HELP.notice.tooltip` in bằng `<code>`; phần chữ giữ nguyên. */
const NOTICE_PATH_RE = /(data\/v1\.0-\*\/|data\/samples\/LIDAR_TOP\/…|data\/)/g;

function NoticeBody({ text }: { text: string }) {
  return (
    <>
      {text.split(NOTICE_PATH_RE).map((part, i) =>
        i % 2 === 1 ? <code key={i}>{part}</code> : <span key={i}>{part}</span>,
      )}
    </>
  );
}

export function UploadPanel(state: Pick<
  DashboardState,
  "abortRef"
  |"checkProgress"
  |"checking"
  |"collapsed"
  |"dataset"
  |"fileInputRef"
  |"filesRef"
  |"items"
  |"paused"
  |"setDataset"
  |"setItems"
  |"startUpload"
  |"toggleCollapsed"
  |"uploadIdRef"
  |"uploadSummary"
  |"uploading"
>) {
  const {
    abortRef,
    checkProgress,
    checking,
    collapsed,
    dataset,
    fileInputRef,
    filesRef,
    items,
    paused,
    setDataset,
    setItems,
    startUpload,
    toggleCollapsed,
    uploadIdRef,
    uploadSummary,
    uploading,
  }=state;

  const online = process.env.NEXT_PUBLIC_VCF_SESSIONS === "1";
  const [pendingFiles, setPendingFiles] = useState<File[]>([]);
  const [onlineWarning, setOnlineWarning] = useState(false);
  const beginUpload = (files: File[]) => {
    setPendingFiles([]);
    uploadIdRef.current = undefined;
    setItems([]);
    setDataset(null);
    void startUpload(files);
  };
  const selectFiles = (files: File[]) => {
    if (!files.length || uploading) return;
    setPendingFiles([]);
    const total = files.reduce((sum, file) => sum + file.size, 0);
    const verdict = checkUploadLimits(total, limits, formatBytes);
    setLimitNotice(verdict);
    const selection = uploadSelection(total, online);
    setOnlineWarning(selection.warning);
    if (verdict.blocked) return;
    if (selection.confirm) setPendingFiles(files);
    else beginUpload(files);
  };
  const [limits, setLimits] = useState<UploadLimits | null>(null);
  const [limitNotice, setLimitNotice] = useState<UploadLimitVerdict | null>(null);

  useEffect(() => {
    let alive = true;
    getUploadLimits()
      .then((l) => { if (alive) setLimits(l); })
      .catch(() => { if (alive) setLimits(null); }); // lỗi/non-200 ⇒ chữ dự phòng, KHÔNG chặn tải
    return () => { alive = false; };
  }, []);

  const limitLabel = limits
    ? UPLOAD_HELP.limit.label.replace("{max}", formatBytes(limits.maxUploadBytes))
    : UPLOAD_HELP.limitFallback.label;

  return (
    <div className="bg-white rounded-xl border border-[#E2E8F0] p-6 shadow-xs flex flex-col gap-4">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div className="flex items-center gap-3">
          <div className="w-7 h-7 rounded-full bg-blue-600 text-white font-bold text-xs flex items-center justify-center">
            1
          </div>
          <h2 className="font-bold text-base text-slate-900">Nạp dữ liệu</h2>
        </div>
        <span className="text-xs text-slate-400 font-medium">Bước 1 / 3</span>
      </div>

      <p className="text-xs text-slate-600 leading-relaxed">
        Tải lên một hoặc nhiều file nén (.zip, .rar, .7z) chứa dataset nuScenes.
      </p>

      {online && (
        <div className="rounded-lg border border-blue-200 bg-blue-50 p-3 text-xs leading-relaxed text-blue-950">
          {UPLOAD_HELP.notice.online.intro} <strong>{UPLOAD_HELP.notice.online.soft}</strong>
          {UPLOAD_HELP.notice.online.middle} <strong>{UPLOAD_HELP.notice.online.large}</strong>.{" "}
          <a className="underline" href="/huong-dan#chay-local">{UPLOAD_HELP.notice.online.localLink}</a>
        </div>
      )}
      {/* Dropzone */}
      <div
        onDragOver={(event) => event.preventDefault()}
        onDrop={(event) => {
          event.preventDefault();
          selectFiles(Array.from(event.dataTransfer.files));
        }}
        role="button"
        tabIndex={uploading? -1:0}
        aria-label="Chọn hoặc thả tệp dữ liệu"
        aria-disabled={uploading}
        onClick={() => !uploading&&fileInputRef.current?.click()}
        onKeyDown={(event) => {
          if(!uploading&&(event.key==="Enter"||event.key===" ")) {
            event.preventDefault();
            fileInputRef.current?.click();
          }
        }}
        className="border-2 border-dashed border-blue-200 hover:border-blue-400 bg-blue-50/20 hover:bg-blue-50/40 rounded-xl p-5 sm:p-8 flex flex-col items-center justify-center gap-3 text-center cursor-pointer transition-colors focus-visible:outline focus-visible:outline-2 focus-visible:outline-blue-700"
      >
        <div className="w-12 h-12 rounded-full bg-blue-100 text-blue-600 flex items-center justify-center">
          <svg className="w-6 h-6" fill="none" stroke="currentColor" viewBox="0 0 24 24" strokeWidth="2">
            <path strokeLinecap="round" strokeLinejoin="round" d="M7 16a4 4 0 01-.88-7.903A5 5 0 1115.9 6L16 6a5 5 0 011 9.9M15 13l-3-3m0 0l-3 3m3-3v12" />
          </svg>
        </div>
        <div>
          <p className="font-semibold text-sm text-slate-800">
            {UPLOAD_HELP.dropzone.label}
          </p>
          <p className="text-xs text-slate-500 mt-1 flex flex-wrap items-center justify-center gap-1.5">
            <span>{limitLabel}</span>
            <Tooltip label={limitLabel} content={UPLOAD_HELP.limit.tooltip} />
          </p>
        </div>
        <span className="mt-1 inline-flex min-h-10 items-center rounded-lg bg-blue-600 px-5 py-2 text-xs font-medium text-white shadow-xs">Chọn file</span>
        <input
          ref={fileInputRef}
          data-testid="file-input"
          type="file"
          multiple
          accept=".zip,.rar,.7z,.001,.002,.003,.json"
          className="hidden"
          disabled={uploading}
          onChange={(e) => {
            selectFiles(Array.from(e.target.files ?? []));
            e.target.value = "";
          }}
        />
      </div>

      {/* Kiểm tổng dung lượng trước khi gửi (SPEC-P02 U5) */}
      {limitNotice?.error&&(
        <p role="alert" data-testid="upload-limit-error" className="p-2.5 bg-rose-50 border border-rose-200 text-rose-800 rounded-lg text-xs font-medium">
          {limitNotice.error}
        </p>
      )}
      {limitNotice?.warning&&(
        <p data-testid="upload-limit-warning" className="p-2.5 bg-amber-50 border border-amber-200 text-amber-900 rounded-lg text-xs font-medium">
          {limitNotice.warning}
        </p>
      )}

      {onlineWarning && !pendingFiles.length && !limitNotice?.blocked && (
        <p className="rounded-lg border border-yellow-200 bg-yellow-50 p-3 text-xs text-yellow-900">{UPLOAD_HELP.notice.online.warning}</p>
      )}
      {pendingFiles.length > 0 && (
        <div role="alert" className="rounded-lg border border-orange-300 bg-orange-50 p-3 text-xs text-orange-950">
          <p>{UPLOAD_HELP.notice.online.confirmWarning}</p>
          <div className="mt-2 flex flex-wrap items-center gap-3">
            <button type="button" disabled={uploading} onClick={() => beginUpload(pendingFiles)} className="min-h-9 rounded-lg bg-orange-700 px-3 font-semibold text-white">{UPLOAD_HELP.notice.online.confirm}</button>
            <a href="/huong-dan#chay-local" className="underline">{UPLOAD_HELP.notice.online.localLink}</a>
          </div>
        </div>
      )}
      {/* Điều khiển upload khi đang tiến hành */}
      {uploading&&!checking&&(
        <div className="flex items-center gap-3">
          <button
            type="button"
            onClick={() => abortRef.current?.abort()}
            className="px-3 py-1.5 bg-amber-100 hover:bg-amber-200 text-amber-800 text-xs font-medium rounded-lg"
          >
            Tạm dừng
          </button>
        </div>
      )}
      {paused&&(
        <div className="flex items-center gap-3">
          <button
            type="button"
            onClick={() => void startUpload(filesRef.current)}
            className="px-3 py-1.5 bg-blue-600 hover:bg-blue-700 text-white text-xs font-medium rounded-lg"
          >
            Tiếp tục tải lên
          </button>
        </div>
      )}

      {/* Danh sách file upload */}
      {items.length>0&&(
        <div className="mt-2 flex flex-col gap-2">
          {items.length>=2&&(
            <div className="flex items-center justify-between gap-3 text-xs">
              <span className="font-semibold text-slate-700">Danh sách tệp</span>
              <button
                type="button"
                aria-expanded={!collapsed}
                onClick={toggleCollapsed}
                className="min-h-8 rounded-md border border-slate-300 bg-white px-3 font-semibold text-slate-700 hover:bg-slate-50"
              >
                {collapsed? "Mở rộng":"Rút gọn"}
              </button>
            </div>
          )}
          {items.length>=2&&collapsed? (
            <div data-testid="upload-summary" className="p-2.5 bg-slate-50 border border-slate-200 rounded-lg text-xs font-medium text-slate-700">
              {uploadSummary.count} tệp · {formatBytes(uploadSummary.totalBytes)} · {uploadSummary.pct}% đã tải
              {uploadSummary.failed>0&&<span className="text-rose-700"> · {uploadSummary.failed} tệp lỗi</span>}
            </div>
          ):(
            <ul className="space-y-2">
              {items.map((i) => (
                <li
                  key={i.name}
                  data-testid="upload-item"
                  className="p-2.5 bg-slate-50 border border-slate-200 rounded-lg text-xs flex flex-col gap-1.5"
                >
                  <div className="flex justify-between font-medium text-slate-700">
                    <span>{i.name}</span>
                    <span className="font-mono text-slate-500">
                      {i.received} / {i.total} B ({pct(i.total? i.received/i.total:0)})
                    </span>
                  </div>
                  <div className="w-full h-1.5 bg-slate-200 rounded-full overflow-hidden">
                    <div
                      className="h-full bg-blue-600 rounded-full transition-all duration-200"
                      style={{ width: `${pct(i.total? i.received/i.total:0)}` }}
                    />
                  </div>
                </li>
              ))}
            </ul>
          )}
        </div>
      )}

      {/* Thanh thời gian dự đoán xét tệp (SPEC-P05) */}
      {checking&&(
        <div data-testid="check-eta" className="p-2.5 bg-blue-50 border border-blue-200 rounded-lg text-xs text-blue-950 flex flex-col gap-1.5">
          <span className="font-medium">
            {checkProgress
              ? `Đang xét tệp đầu vào · ${PHASE_LABELS[checkProgress.phase]??checkProgress.phase} · còn khoảng ${formatEta(checkProgress.etaSec)}`
              :"Đang xét tệp đầu vào…"}
          </span>
          {checkProgress? (
            <progress aria-label="Tiến độ xét tệp" className="w-full h-2" max={100} value={checkProgressPct(checkProgress)} />
          ):(
            <progress aria-label="Tiến độ xét tệp" className="w-full h-2" />
          )}
        </div>
      )}

      {/* Hộp lưu ý cấu trúc data/ (SPEC-P02 U4): chữ lấy từ UPLOAD_HELP.notice */}
      <div className="p-3.5 bg-blue-50/80 border border-blue-200 text-blue-950 rounded-xl flex items-start gap-2.5 text-xs leading-relaxed">
        <span className="text-blue-600 font-bold text-sm leading-none mt-0.5">ℹ</span>
        <div data-testid="data-notice" className="min-w-0 space-y-2">
          <ul className="space-y-2">
            {UPLOAD_HELP.notice.checklist.map((item, index) => (
              <li key={index} className="break-words">
                <strong>{item.label}</strong>: <code>{item.path}</code>{" "}
                {item.files.length > 0 && <span>{item.files.join(", ")} ? </span>}{item.detail}
              </li>
            ))}
          </ul>
          <p>{UPLOAD_HELP.notice.missing}</p>
          <p><NoticeBody text={UPLOAD_HELP.notice.tooltip} /></p>
        </div>
      </div>

      {/* Báo cáo dataset nếu đã nạp xong */}
      {dataset&&(
        <div
          data-testid="dataset-report"
          role={isDatasetUsable(dataset)? "status":"alert"}
          className={`p-4 rounded-xl text-xs flex flex-col gap-2 ${isDatasetUsable(dataset)? "bg-emerald-50/50 border border-emerald-200":"bg-rose-50 border border-rose-300"}`}
        >
          <div className="flex items-center justify-between">
            <span className={`font-bold ${isDatasetUsable(dataset)? "text-emerald-900":"text-rose-900"}`}>Báo cáo Dataset {dataset.version}</span>
            <span className={`font-mono ${isDatasetUsable(dataset)? "text-emerald-700":"text-rose-700"}`}>
              {dataset.scenes} scene · {dataset.frames} frame
            </span>
          </div>
          <div className={`flex flex-wrap items-center gap-x-4 gap-y-1 ${isDatasetUsable(dataset)? "text-emerald-800":"text-rose-800"}`}>
            <span>LiDAR: {dataset.hasLidar? "✓ Có":"✗ Không"}</span>
            <span>Nhãn 3D: {dataset.hasAnnotations? "✓ Có":"✗ Không"}</span>
          </div>
          {!isDatasetUsable(dataset)&&(
            <p className="font-medium text-rose-800">{datasetValidationMessage(dataset)}</p>
          )}
        </div>
      )}
    </div>
  );
}
