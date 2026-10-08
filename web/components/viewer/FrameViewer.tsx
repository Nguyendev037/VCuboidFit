"use client";

import React, { useEffect, useState, useMemo, useSyncExternalStore } from "react";
import type { Cam, FrameDetail } from "@/lib/api/types";
import { getFrame } from "@/lib/api/client";
import { LidarScene } from "./LidarScene";
import { CameraImage, getCamFriendlyName } from "./CameraImage";
import {
  groupCamerasByPosition,
  handleViewerKeyDown,
  type ViewerActions,
} from "./viewerUtils";

export interface FrameViewerProps {
  jobId: string;
  token: string;
  sid?: string;
  onPrev?: () => void;
  onNext?: () => void;
  onClose: () => void;
}

const subscribeToSampleMode = (callback: () => void) => {
  window.addEventListener("storage", callback);
  return () => window.removeEventListener("storage", callback);
};
const getSampleModeSnapshot = () => window.sessionStorage.getItem("vcf-demo") === "1";
const getSampleModeServerSnapshot = () => false;

export function FrameViewer({
  jobId,
  token,
  sid,
  onPrev,
  onNext,
  onClose,
}: FrameViewerProps) {
  const [frame, setFrame] = useState<FrameDetail | null>(null);
  const isSampleMode = useSyncExternalStore(
    subscribeToSampleMode,
    getSampleModeSnapshot,
    getSampleModeServerSnapshot,
  );
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [retryVersion, setRetryVersion] = useState(0);

  // Chế độ xem: surround (3 cam trước - LiDAR - 3 cam sau) hoặc focus
  const [mode, setMode] = useState<"surround" | "focus">("surround");
  const [focusTarget, setFocusTarget] = useState<Cam | "lidar" | "bev">("CAM_FRONT");

  // Các cờ hiển thị
  const [showBoxes, setShowBoxes] = useState(true);
  const [showLidarOverlay, setShowLidarOverlay] = useState(false);
  const [showInfoPanel, setShowInfoPanel] = useState(true);
  const [reset3dTrigger, setReset3dTrigger] = useState(0);

  // Tải dữ liệu frame hiện tại
  useEffect(() => {
    let isMounted = true;
    queueMicrotask(() => {
      if (isMounted) {
        setLoading(true);
        setError(null);
      }
    });

    getFrame(jobId, token, sid)
      .then((data) => {
        if (!isMounted) return;
        setFrame(data);
        setLoading(false);
      })
      .catch((err) => {
        if (!isMounted) return;
        setError(err instanceof Error ? err.message : "Lỗi tải thông tin frame");
        setLoading(false);
      });

    return () => {
      isMounted = false;
    };
  }, [jobId, token, sid, retryVersion]);

  // Bộ hành động cho phím tắt
  const actions: ViewerActions = useMemo(
    () => ({
      onPrev,
      onNext,
      onClose,
      setMode,
      setFocusTarget,
      toggleBoxes: () => setShowBoxes((b) => !b),
      toggleLidarOverlay: () => setShowLidarOverlay((p) => !p),
      toggleInfoPanel: () => setShowInfoPanel((i) => !i),
      reset3dView: () => setReset3dTrigger((t) => t + 1),
    }),
    [onPrev, onNext, onClose]
  );

  // Lắng nghe sự kiện bàn phím toàn cục
  useEffect(() => {
    const handleKeyDown = (e: KeyboardEvent) => {
      // Bỏ qua nếu người dùng đang nhập trong input
      if (
        e.target instanceof HTMLInputElement ||
        e.target instanceof HTMLTextAreaElement
      ) {
        return;
      }
      handleViewerKeyDown(e, actions);
    };

    window.addEventListener("keydown", handleKeyDown);
    return () => window.removeEventListener("keydown", handleKeyDown);
  }, [actions]);

  // Phân nhóm camera trước và sau
  const cameraGroups = useMemo(() => {
    return groupCamerasByPosition(frame?.cams);
  }, [frame?.cams]);

  const focusedCamDetail = useMemo(() => {
    if (focusTarget === "lidar" || focusTarget === "bev" || !frame) return null;
    return frame.cams.find((c) => c.cam === focusTarget) || null;
  }, [frame, focusTarget]);
  const isLidarFrame = !!frame && (frame.bestCam === "LIDAR_TOP" || !!frame.bevUrl || typeof frame.rRar === "number");

  return (
    <div
      className="fixed inset-0 z-50 bg-[#0B0F17] text-slate-100 flex flex-col font-sans select-none overflow-hidden"
      data-testid="frame-overlay"
    >
      {/* 1. Header điều khiển */}
      <header className="min-h-12 border-b border-white/10 px-2 sm:px-4 py-2 flex flex-wrap items-center justify-between gap-2 bg-black/40 backdrop-blur-sm z-30 shrink-0">
        <div className="flex min-w-0 flex-1 items-center gap-2 sm:gap-3">
          <span className="font-bold text-sm tracking-tight text-white flex items-center gap-1.5">
            <span className="w-2 h-2 rounded-full bg-blue-500" />
            VCuboidFIT Frame Viewer
          </span>
          {isSampleMode && <span className="rounded-full border border-amber-400/40 bg-amber-400/10 px-2 py-0.5 text-[10px] font-semibold text-amber-300">Dữ liệu mẫu</span>}
          {frame && (
            <div className="hidden sm:flex min-w-0 items-center gap-2 text-xs text-slate-400 border-l border-white/10 pl-3">
              <span className="bg-blue-600/30 text-blue-400 px-2 py-0.5 rounded font-mono font-semibold">
                #{frame.rank}
              </span>
              <span className="text-slate-300 font-medium">{frame.sceneName}</span>
              <span className="font-mono text-slate-500">[{frame.frameIdx}]</span>
            </div>
          )}
        </div>

        {/* Chuyển đổi chế độ Surround / Focus */}
        <div className="flex shrink-0 items-center gap-1 bg-white/5 p-0.5 rounded-lg border border-white/10 text-[11px] sm:text-xs">
          <button
            type="button"
            onClick={() => setMode("surround")}
            aria-pressed={mode === "surround"}
            className={`px-2.5 py-1 rounded transition-colors ${
              mode === "surround"
                ? "bg-blue-600 text-white font-semibold shadow"
                : "text-slate-400 hover:text-white"
            }`}
          >
            Surround (0)
          </button>
          <button
            type="button"
            onClick={() => {
              setMode("focus");
              if ((focusTarget === "lidar" && !frame?.lidar) || (focusTarget === "bev" && !frame?.bevUrl)) {
                setFocusTarget("CAM_FRONT");
              }
            }}
            aria-pressed={mode === "focus"}
            className={`px-2.5 py-1 rounded transition-colors ${
              mode === "focus"
                ? "bg-blue-600 text-white font-semibold shadow"
                : "text-slate-400 hover:text-white"
            }`}
          >
            Focus (1-6)
          </button>
        </div>

        {/* Nút tác vụ */}
        <div className="flex flex-wrap items-center justify-end gap-1.5">
          {onPrev && (
            <button
              type="button"
              onClick={onPrev}
              title="Frame trước (←)"
              aria-label="Frame trước"
              className="min-h-9 min-w-9 rounded-lg bg-white/5 hover:bg-white/15 text-slate-300 hover:text-white transition-colors focus-visible:outline focus-visible:outline-2 focus-visible:outline-blue-400"
            >
              ←
            </button>
          )}
          {onNext && (
            <button
              type="button"
              onClick={onNext}
              title="Frame kế tiếp (→)"
              aria-label="Frame kế tiếp"
              className="min-h-9 min-w-9 rounded-lg bg-white/5 hover:bg-white/15 text-slate-300 hover:text-white transition-colors focus-visible:outline focus-visible:outline-2 focus-visible:outline-blue-400"
            >
              →
            </button>
          )}
          <button
            type="button"
            onClick={() => setShowBoxes((b) => !b)}
            aria-pressed={showBoxes}
            className={`px-2 py-1 rounded-lg text-xs font-medium border transition-colors ${
              showBoxes
                ? "bg-blue-500/20 text-blue-300 border-blue-500/40"
                : "bg-white/5 text-slate-400 border-white/10 hover:text-white"
            }`}
          >
            Hộp 3D (B)
          </button>
          <button
            type="button"
            onClick={() => setShowInfoPanel((i) => !i)}
            aria-pressed={showInfoPanel}
            className={`px-2 py-1 rounded-lg text-xs font-medium border transition-colors ${
              showInfoPanel
                ? "bg-white/20 text-white border-white/30"
                : "bg-white/5 text-slate-400 border-white/10 hover:text-white"
            }`}
          >
            Thông tin (I)
          </button>
          <button
            type="button"
            onClick={onClose}
            aria-label="Đóng Frame Viewer"
            className="px-2.5 py-1 rounded-lg text-xs bg-rose-500/20 text-rose-300 hover:bg-rose-500/30 border border-rose-500/30 font-medium transition-colors"
          >
            Đóng (Esc)
          </button>
        </div>
      </header>

      {/* 2. Nội dung chính */}
      <div className="flex-1 min-h-0 flex flex-col md:flex-row overflow-y-auto md:overflow-hidden relative">
        {/* Khu vực hiển thị camera & LiDAR */}
        <main className="flex-1 min-h-[55vh] md:min-h-0 flex flex-col p-2 gap-2 overflow-hidden relative">
          {loading ? (
            <div role="status" aria-live="polite" className="flex-1 flex flex-col items-center justify-center text-slate-300 gap-3">
              <div aria-hidden="true" className="w-8 h-8 border-2 border-blue-500 border-t-transparent rounded-full animate-spin" />
              <p className="text-sm">Đang nạp dữ liệu frame {token}...</p>
            </div>
          ) : error ? (
            <div role="alert" className="flex-1 flex flex-col items-center justify-center text-rose-300 gap-2 px-4 text-center">
              <p className="text-sm font-semibold">Không tải được frame: {error}</p>
              <button
                type="button"
                onClick={() => setRetryVersion((version) => version + 1)}
                className="mt-2 px-3 py-2 bg-blue-600 hover:bg-blue-500 rounded text-xs text-white focus-visible:outline focus-visible:outline-2 focus-visible:outline-white"
              >
                Thử lại
              </button>
              <button
                type="button"
                onClick={onClose}
                className="px-3 py-2 bg-white/10 hover:bg-white/20 rounded text-xs text-white focus-visible:outline focus-visible:outline-2 focus-visible:outline-white"
              >
                Quay lại
              </button>
            </div>
          ) : !frame ? null : mode === "surround" ? (
            // ================== BỐ CỤC SURROUND ==================
            <div className="flex-1 flex flex-col gap-2 min-h-0">
              {/* Hàng 1: 3 camera trước (CAM_FRONT_LEFT, CAM_FRONT, CAM_FRONT_RIGHT) */}
              {cameraGroups.front.length > 0 && (
                <div
                  className="grid gap-2 h-[24%] md:h-[28%]"
                  style={{
                    gridTemplateColumns: `repeat(${cameraGroups.front.length}, minmax(0, 1fr))`,
                  }}
                >
                  {cameraGroups.front.map((cam) => (
                    <CameraImage
                      key={cam.cam}
                      camDetail={cam}
                      showBoxes={showBoxes}
                      showLidarOverlay={showLidarOverlay}
                      onClick={() => {
                        setMode("focus");
                        setFocusTarget(cam.cam);
                      }}
                    />
                  ))}
                </div>
              )}

              {/* Hàng 2: LiDAR 3D Scene ở giữa */}
              <div className="flex-1 min-h-[180px]">
                <LidarScene
                  lidarUrl={frame.lidar?.url}
                  boxes3d={frame.boxes3d}
                  camPoses={frame.camPoses}
                  showBoxes={showBoxes}
                  resetTrigger={reset3dTrigger}
                  onSelectCam={(cam) => {
                    setMode("focus");
                    setFocusTarget(cam);
                  }}
                />
              </div>

              {/* Hàng 3: 3 camera sau (CAM_BACK_LEFT, CAM_BACK, CAM_BACK_RIGHT) */}
              {cameraGroups.back.length > 0 && (
                <div
                  className="grid gap-2 h-[24%] md:h-[28%]"
                  style={{
                    gridTemplateColumns: `repeat(${cameraGroups.back.length}, minmax(0, 1fr))`,
                  }}
                >
                  {cameraGroups.back.map((cam) => (
                    <CameraImage
                      key={cam.cam}
                      camDetail={cam}
                      showBoxes={showBoxes}
                      showLidarOverlay={showLidarOverlay}
                      onClick={() => {
                        setMode("focus");
                        setFocusTarget(cam.cam);
                      }}
                    />
                  ))}
                </div>
              )}
            </div>
          ) : (
            // ================== BỐ CỤC FOCUS ==================
            <div className="flex-1 flex flex-col gap-2 min-h-0">
              {/* Khung Focus chính */}
              <div className="flex-1 relative rounded-xl overflow-hidden min-h-0">
                {focusTarget === "lidar" ? (
                  <LidarScene
                    lidarUrl={frame.lidar?.url}
                    boxes3d={frame.boxes3d}
                    camPoses={frame.camPoses}
                    showBoxes={showBoxes}
                    resetTrigger={reset3dTrigger}
                    onSelectCam={(cam) => setFocusTarget(cam)}
                  />
                ) : focusTarget === "bev" && frame.bevUrl ? (
                  <div className="relative h-full w-full bg-black">
                    {/* eslint-disable-next-line @next/next/no-img-element */}
                    <img src={frame.bevUrl} alt="BEV LiDAR" className="h-full w-full object-contain" />
                    <span className="absolute left-3 top-3 rounded bg-black/70 px-2 py-1 text-xs font-semibold text-slate-100">
                      BEV
                    </span>
                  </div>
                ) : focusedCamDetail ? (
                  <CameraImage
                    camDetail={focusedCamDetail}
                    showBoxes={showBoxes}
                    showLidarOverlay={showLidarOverlay}
                    isFocus
                  />
                ) : (
                  <div className="w-full h-full flex items-center justify-center text-slate-400">
                    Camera không khả dụng
                  </div>
                )}
              </div>

              {/* Dải thumbnail chuyển đổi nguồn */}
              <div className="h-16 shrink-0 flex items-center gap-2 overflow-x-auto bg-black/50 p-2 rounded-xl border border-white/10">
                {/* Nút LiDAR */}
                <button
                  type="button"
                  onClick={() => setFocusTarget("lidar")}
                  className={`h-full px-3 rounded-lg flex items-center gap-2 border text-xs transition-colors shrink-0 ${
                    focusTarget === "lidar"
                      ? "bg-blue-600/30 border-blue-500 text-white font-semibold"
                      : "bg-white/5 border-white/10 text-slate-400 hover:text-white"
                  }`}
                >
                  <span className="w-2 h-2 rounded-full bg-cyan-400" />
                  LiDAR 3D (7/L)
                </button>

                {frame.bevUrl && (
                  <button
                    type="button"
                    onClick={() => setFocusTarget("bev")}
                    aria-pressed={focusTarget === "bev"}
                    className={`h-full px-3 rounded-lg flex items-center gap-2 border text-xs transition-colors shrink-0 ${
                      focusTarget === "bev"
                        ? "bg-blue-600/30 border-blue-500 text-white font-semibold"
                        : "bg-white/5 border-white/10 text-slate-400 hover:text-white"
                    }`}
                  >
                    <span className="w-2 h-2 rounded-full bg-emerald-400" />
                    BEV
                  </button>
                )}

                {/* Các camera có sẵn */}
                {frame.cams.map((cam, idx) => {
                  const isActive = focusTarget === cam.cam;
                  return (
                    <button
                      key={cam.cam}
                      type="button"
                      onClick={() => setFocusTarget(cam.cam)}
                      className={`h-full w-24 relative rounded-lg overflow-hidden border transition-all shrink-0 ${
                        isActive
                          ? "ring-2 ring-blue-500 border-transparent shadow-lg scale-102"
                          : "border-white/10 opacity-70 hover:opacity-100"
                      }`}
                    >
                      {/* eslint-disable-next-line @next/next/no-img-element */}
                      <img
                        src={cam.imageUrl}
                        alt={cam.cam}
                        className="w-full h-full object-cover"
                      />
                      <span className="absolute bottom-1 left-1 right-1 bg-black/75 backdrop-blur-sm text-[9px] text-center font-mono rounded truncate px-1 text-slate-200">
                        {idx + 1}: {getCamFriendlyName(cam.cam)}
                      </span>
                    </button>
                  );
                })}
              </div>
            </div>
          )}
        </main>

        {/* 3. Panel thông tin chi tiết bên phải (thu gọn được) */}
        {showInfoPanel && frame && (
          <aside className="w-full md:w-80 md:border-l border-t md:border-t-0 border-white/10 bg-black/60 backdrop-blur-md p-4 flex flex-col gap-4 overflow-y-auto z-20 shrink-0 max-h-[42vh] md:max-h-none">
            <div>
              <div className="flex items-center justify-between">
                <h3 className="text-xs uppercase tracking-wider text-slate-400 font-semibold">
                  Chỉ số tổng hợp
                </h3>
                <span className="text-xs font-mono text-blue-400">
                  {frame.tags.join(" · ")}
                </span>
              </div>
              <div className="mt-2 p-3 bg-white/5 rounded-xl border border-white/10">
                <div className="flex items-baseline justify-between">
                  <span className="text-xs text-slate-400">Điểm tổng S:</span>
                  <span className="text-xl font-bold font-mono text-emerald-400">
                    {frame.S.toFixed(2)}
                  </span>
                </div>
                {/* Thanh tiến độ rRar/rNov, rUnc, rQry */}
                <div className="mt-3 space-y-2 text-xs">
                  <div>
                    <div className="flex justify-between text-[11px] text-slate-300">
                      <span>{isLidarFrame ? "Hiếm:" : "Độ hiếm:"}</span>
                      <span className="font-mono">{(isLidarFrame ? frame.rRar ?? frame.rNov : frame.rNov).toFixed(2)}</span>
                    </div>
                    <div className="w-full h-1.5 bg-white/10 rounded-full mt-1 overflow-hidden">
                      <div
                        className="h-full bg-cyan-400 rounded-full"
                        style={{ width: `${Math.round((isLidarFrame ? frame.rRar ?? frame.rNov : frame.rNov) * 100)}%` }}
                      />
                    </div>
                  </div>
                  {isLidarFrame && (
                    <div>
                      <div className="flex justify-between text-[11px] text-slate-300">
                        <span>Lạ với model:</span>
                        <span className="font-mono">{frame.rNov.toFixed(2)}</span>
                      </div>
                      <div className="w-full h-1.5 bg-white/10 rounded-full mt-1 overflow-hidden">
                        <div className="h-full bg-blue-300 rounded-full" style={{ width: `${Math.round(frame.rNov * 100)}%` }} />
                      </div>
                    </div>
                  )}
                  <div>
                    <div className="flex justify-between text-[11px] text-slate-300">
                      <span>{isLidarFrame ? "Không chắc:" : "Độ khó:"}</span>
                      <span className="font-mono">{frame.rUnc.toFixed(2)}</span>
                    </div>
                    <div className="w-full h-1.5 bg-white/10 rounded-full mt-1 overflow-hidden">
                      <div
                        className="h-full bg-amber-400 rounded-full"
                        style={{ width: `${Math.round(frame.rUnc * 100)}%` }}
                      />
                    </div>
                  </div>
                  {!isLidarFrame && <div>
                    <div className="flex justify-between text-[11px] text-slate-300">
                      <span>Khớp kịch bản:</span>
                      <span className="font-mono">{frame.rQry.toFixed(2)}</span>
                    </div>
                    <div className="w-full h-1.5 bg-white/10 rounded-full mt-1 overflow-hidden">
                      <div
                        className="h-full bg-purple-400 rounded-full"
                        style={{ width: `${Math.round(frame.rQry * 100)}%` }}
                      />
                    </div>
                  </div>}
                </div>
              </div>
            </div>

            {/* Lý do chọn */}
            <div>
              <h4 className="text-xs uppercase tracking-wider text-slate-400 font-semibold mb-1">
                Lý do chọn
              </h4>
              <p className="text-xs text-slate-200 bg-white/5 p-2.5 rounded-lg border border-white/10 leading-relaxed">
                {frame.reason}
              </p>
              {!isLidarFrame && frame.qryBest && (
                <div className="mt-2 text-[11px] text-slate-400">
                  Khớp truy vấn:{" "}
                  <span className="text-blue-300 font-medium">&ldquo;{frame.qryBest}&rdquo;</span>
                </div>
              )}
            </div>

            {/* Chi tiết từng camera */}
            <div>
              <h4 className="text-xs uppercase tracking-wider text-slate-400 font-semibold mb-2">
                Chất lượng Camera ({frame.cams.length}/6)
              </h4>
              <div className="space-y-1.5">
                {frame.cams.map((c) => (
                  <div
                    key={c.cam}
                    className="flex items-center justify-between p-2 bg-white/5 rounded-lg text-xs border border-white/5"
                  >
                    <div className="flex items-center gap-1.5">
                      <span
                        className={`w-1.5 h-1.5 rounded-full ${
                          c.qOk ? "bg-emerald-400" : "bg-rose-400"
                        }`}
                      />
                      <span className="font-medium text-slate-200">
                        {getCamFriendlyName(c.cam)}
                      </span>
                    </div>
                    <div className="flex items-center gap-2 font-mono text-[11px] text-slate-400">
                      <span>{c.boxes.length} box</span>
                      <span className="text-slate-200">S:{c.score.s.toFixed(2)}</span>
                    </div>
                  </div>
                ))}
              </div>
            </div>

            {/* Thông tin LiDAR */}
            <div>
              <h4 className="text-xs uppercase tracking-wider text-slate-400 font-semibold mb-1">
                LiDAR & 3D Boxes
              </h4>
              <div className="p-2.5 bg-white/5 rounded-lg border border-white/10 text-xs space-y-1">
                <p data-testid="lidar-info" className="flex justify-between font-mono text-slate-200">
                  {frame.lidar
                    ? `LiDAR: ${frame.lidar.numPoints} điểm (${frame.lidar.format})`
                    : "Không có LiDAR"}
                </p>
                <div className="flex justify-between">
                  <span className="text-slate-400">Số 3D Boxes:</span>
                  <span className="font-mono text-slate-200">
                    {frame.boxes3d ? frame.boxes3d.length : 0}
                  </span>
                </div>
              </div>
            </div>
          </aside>
        )}
      </div>

      {/* 4. Thanh gợi ý phím tắt đáy màn hình */}
      <footer aria-label="Phím tắt Frame Viewer" className="hidden md:flex h-8 overflow-x-auto border-t border-white/10 px-4 items-center justify-between bg-black/70 backdrop-blur-sm text-[11px] text-slate-300 shrink-0 z-30 font-mono">
        <div className="flex min-w-max items-center gap-3 whitespace-nowrap">
          <span>←/→ Chuyển frame</span>
          <span>·</span>
          <span>Esc Đóng</span>
          <span>·</span>
          <span>0 Surround</span>
          <span>·</span>
          <span>1–6 Focus Cam</span>
          <span>·</span>
          <span>7/L LiDAR</span>
          <span>·</span>
          <span>B Hộp 3D</span>
          <span>·</span>
          <span>I Thông tin</span>
          <span>·</span>
          <span>R Đặt lại 3D</span>
        </div>
        {isSampleMode && <div className="hidden md:block text-slate-400">VCuboidFIT Demo UI</div>}
      </footer>
    </div>
  );
}
export default FrameViewer;
