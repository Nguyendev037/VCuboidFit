"use client";

import React, { useRef, useState, useEffect, useCallback, useMemo } from "react";
import { useVirtualizer } from "@tanstack/react-virtual";
import type { FrameSummary, Cam } from "@/lib/api/types";
import { CAMS } from "@/lib/api/types";
import { Badge } from "@/components/ui/badge";

export interface FrameGridProps {
  frames: FrameSummary[];
  selectedToken?: string;
  onSelectFrame?: (frame: FrameSummary) => void;
  onOpenViewer?: (frame: FrameSummary) => void;
  viewMode?: "grid" | "list";
  pipeline?: "camera" | "lidar";
  className?: string;
}

export function FrameGrid({
  frames,
  selectedToken,
  onSelectFrame,
  onOpenViewer,
  viewMode = "grid",
  pipeline = "camera",
  className = "",
}: FrameGridProps) {
  // Quản lý index được chọn để hỗ trợ bàn phím
  const selectedIndex = useMemo(() => {
    if (!selectedToken) return 0;
    const idx = frames.findIndex((f) => f.sampleToken === selectedToken);
    return idx >= 0 ? idx : 0;
  }, [frames, selectedToken]);

  const [activeIdx, setActiveIdx] = useState(selectedIndex);

  useEffect(() => {
    setActiveIdx(selectedIndex);
  }, [selectedIndex]);

  // Điều hướng bằng bàn phím (←, →, ↑, ↓, Enter)
  const handleKeyDown = useCallback(
    (e: React.KeyboardEvent) => {
      if (frames.length === 0) return;

      const cols = 4; // Số cột giả định cho phím mũi tên
      let nextIdx = activeIdx;

      if (e.key === "ArrowRight") {
        e.preventDefault();
        nextIdx = Math.min(frames.length - 1, activeIdx + 1);
      } else if (e.key === "ArrowLeft") {
        e.preventDefault();
        nextIdx = Math.max(0, activeIdx - 1);
      } else if (e.key === "ArrowDown") {
        e.preventDefault();
        nextIdx = Math.min(frames.length - 1, activeIdx + cols);
      } else if (e.key === "ArrowUp") {
        e.preventDefault();
        nextIdx = Math.max(0, activeIdx - cols);
      } else if (e.key === "Enter") {
        e.preventDefault();
        const selected = frames[activeIdx];
        if (selected) {
          onOpenViewer?.(selected);
        }
        return;
      } else {
        return;
      }

      if (nextIdx !== activeIdx) {
        setActiveIdx(nextIdx);
        onSelectFrame?.(frames[nextIdx]);
      }
    },
    [frames, activeIdx, onSelectFrame, onOpenViewer]
  );

  // Ảo hóa khi số lượng frame > 200
  const isVirtualized = frames.length > 200;
  const parentRef = useRef<HTMLDivElement>(null);

  // Chia frames thành các hàng (mỗi hàng 3 hoặc 4 cột)
  const itemsPerRow = 3;
  const rowCount = Math.ceil(frames.length / itemsPerRow);

  const rowVirtualizer = useVirtualizer({
    count: isVirtualized ? rowCount : 0,
    getScrollElement: () => parentRef.current,
    estimateSize: () => 290, // Chiều cao ước tính mỗi hàng thẻ
    overscan: 3,
  });

  const renderCard = (frame: FrameSummary, idx: number) => {
    const isSelected =
      frame.sampleToken === selectedToken || idx === activeIdx;

    return (
      <div
        key={frame.sampleToken}
        role="button"
        tabIndex={0}
        aria-label={`Mở frame hạng ${frame.rank}, ${frame.sceneName}, frame ${frame.frameIdx}`}
        aria-pressed={isSelected}
        onClick={() => {
          setActiveIdx(idx);
          onSelectFrame?.(frame);
          onOpenViewer?.(frame);
        }}
        onKeyDown={(event) => {
          if (event.key === "Enter" || event.key === " ") {
            event.preventDefault();
            onOpenViewer?.(frame);
          }
        }}
        onDoubleClick={() => onOpenViewer?.(frame)}
        className={`group relative flex flex-col rounded-xl border bg-card text-card-foreground overflow-hidden cursor-pointer transition-all duration-150 select-none ${
          isSelected
            ? "ring-2 ring-blue-600 border-blue-600 shadow-md scale-[1.01]"
            : "border-border hover:border-slate-300 hover:shadow-sm"
        }`}
        data-testid="frame-cell"
      >
        {/* Thumbnail 16:9 */}
        <div className="relative aspect-video w-full bg-slate-100 overflow-hidden">
          {/* eslint-disable-next-line @next/next/no-img-element */}
          <img
            src={frame.thumbUrl}
            alt={frame.sceneName}
            className="w-full h-full object-cover group-hover:scale-103 transition-transform duration-200"
            loading="lazy"
          />

          {/* Huy hiệu Rank góc trên bên trái */}
          <div className="absolute top-2 left-2 flex items-center gap-1">
            <span className="bg-slate-900/80 backdrop-blur-md text-white font-mono text-xs font-bold px-2 py-0.5 rounded-md shadow">
              #{frame.rank}
            </span>
          </div>

          {/* Điểm S góc trên bên phải */}
          <div className="absolute top-2 right-2">
            <span className="bg-emerald-600/90 backdrop-blur-md text-white font-mono text-xs font-bold px-2 py-0.5 rounded-md shadow">
              S: {frame.S.toFixed(2)}
            </span>
          </div>

          {/* Chỉ báo 6 camera ở góc dưới bên phải */}
          <div className="absolute bottom-2 right-2 flex items-center gap-1 bg-black/60 backdrop-blur-sm px-1.5 py-0.5 rounded-md">
            {CAMS.map((camName) => {
              const hasCam = frame.camsAvailable.includes(camName as Cam);
              return (
                <span
                  key={camName}
                  title={camName}
                  className={`w-1.5 h-1.5 rounded-full ${
                    hasCam ? "bg-emerald-400" : "bg-white/20"
                  }`}
                />
              );
            })}
          </div>
        </div>

        {/* Thông tin mô tả bên dưới */}
        <div className="p-3 flex flex-col gap-1.5 flex-1 justify-between bg-white">
          <div>
            <div className="flex items-center justify-between text-xs text-muted-foreground mb-1">
              <span className="font-semibold text-slate-700">{frame.sceneName}</span>
              <span className="font-mono text-[11px]">Frame {frame.frameIdx}</span>
            </div>

            <p className="text-xs text-slate-600 line-clamp-2 leading-relaxed">
              {frame.reason}
            </p>
          </div>

          <div className="flex items-center justify-between pt-1 border-t border-slate-100 mt-1">
            <div className="flex items-center gap-1 flex-wrap">
              {frame.tags.map((tag) => (
                <Badge key={tag} variant="secondary" className="text-[10px] py-0 px-1.5">
                  {tag}
                </Badge>
              ))}
            </div>
            <span className="text-[10px] text-slate-400 font-mono">
              {frame.bestCam.replace("CAM_", "")}
            </span>
          </div>
        </div>
      </div>
    );
  };

  if (viewMode === "list") {
    const isLidar = pipeline === "lidar";
    return (
      <div
        className={`w-full overflow-x-auto rounded-xl border border-border bg-card outline-none ${className}`}
        tabIndex={0}
        onKeyDown={handleKeyDown}
      >
        <table className="w-full text-xs text-left border-collapse">
          <thead>
            <tr className="border-b border-border bg-slate-50 text-slate-500 font-medium">
              <th className="p-3 w-16">Rank</th>
              <th className="p-3">Scene</th>
              <th className="p-3 w-16">Frame</th>
              <th className="p-3 w-16">S</th>
              <th className="p-3 w-16">{isLidar ? "Hiếm" : "rNov"}</th>
              <th className="p-3 w-20">{isLidar ? "Lạ với model" : "rUnc"}</th>
              <th className="p-3 w-20">{isLidar ? "Không chắc" : "rQry"}</th>
              <th className="p-3">Lý do chọn</th>
              <th className="p-3">Tag</th>
            </tr>
          </thead>
          <tbody>
            {frames.map((f, idx) => {
              const isSelected = f.sampleToken === selectedToken || idx === activeIdx;
              return (
                <tr
                  key={f.sampleToken}
                  onClick={() => {
                    setActiveIdx(idx);
                    onSelectFrame?.(f);
                  }}
                  onDoubleClick={() => onOpenViewer?.(f)}
                  className={`border-b border-border/50 cursor-pointer transition-colors ${
                    isSelected
                      ? "bg-blue-50 font-medium text-blue-900"
                      : "hover:bg-slate-50 text-slate-700"
                  }`}
                >
                  <td className="p-3 font-mono font-bold text-slate-900">#{f.rank}</td>
                  <td className="p-3">{f.sceneName}</td>
                  <td className="p-3 font-mono">{f.frameIdx}</td>
                  <td className="p-3 font-mono text-emerald-600 font-bold">{f.S.toFixed(2)}</td>
                  <td className="p-3 font-mono text-slate-500">{(isLidar ? f.rRar ?? f.rNov : f.rNov).toFixed(2)}</td>
                  <td className="p-3 font-mono text-slate-500">{(isLidar ? f.rNov : f.rUnc).toFixed(2)}</td>
                  {!isLidar && <td className="p-3 font-mono text-slate-500">{f.rQry.toFixed(2)}</td>}
                  {isLidar && <td className="p-3 font-mono text-slate-500">{f.rUnc.toFixed(2)}</td>}
                  <td className="p-3 truncate max-w-xs">{f.reason}</td>
                  <td className="p-3">
                    {f.tags.map((t) => (
                      <span
                        key={t}
                        className="inline-block bg-slate-100 text-slate-700 text-[10px] px-1.5 py-0.5 rounded mr-1"
                      >
                        {t}
                      </span>
                    ))}
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>
    );
  }

  // Chế độ Grid thông thường hoặc ảo hóa
  return (
    <div
      ref={parentRef}
      className={`w-full outline-none focus:ring-1 focus:ring-blue-500/30 rounded-xl overflow-y-auto ${className}`}
      tabIndex={0}
      onKeyDown={handleKeyDown}
      data-testid="frame-grid"
    >
      {isVirtualized ? (
        <div
          style={{
            height: `${rowVirtualizer.getTotalSize()}px`,
            width: "100%",
            position: "relative",
          }}
        >
          {rowVirtualizer.getVirtualItems().map((virtualRow) => {
            const startIdx = virtualRow.index * itemsPerRow;
            const rowFrames = frames.slice(startIdx, startIdx + itemsPerRow);

            return (
              <div
                key={virtualRow.key}
                style={{
                  position: "absolute",
                  top: 0,
                  left: 0,
                  width: "100%",
                  transform: `translateY(${virtualRow.start}px)`,
                }}
                className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4 pb-4"
              >
                {rowFrames.map((frame, colIdx) =>
                  renderCard(frame, startIdx + colIdx)
                )}
              </div>
            );
          })}
        </div>
      ) : (
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
          {frames.map((frame, idx) => renderCard(frame, idx))}
        </div>
      )}
    </div>
  );
}
export default FrameGrid;
