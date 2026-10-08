"use client";

import React, { useState, useRef, useCallback } from "react";
import type { CamDetail } from "@/lib/api/types";
import { getCategoryColor } from "./lidarDecoder";

export interface CameraImageProps {
  camDetail: CamDetail;
  showBoxes?: boolean;
  showLidarOverlay?: boolean;
  hideCameraScore?: boolean;
  isFocus?: boolean;
  onClick?: () => void;
  className?: string;
}

// Chuyển đổi tên camera chuẩn sang nhãn ngắn gọn, dễ đọc
export function getCamFriendlyName(cam: string): string {
  switch (cam) {
    case "CAM_FRONT_LEFT":
      return "Front Left";
    case "CAM_FRONT":
      return "Front";
    case "CAM_FRONT_RIGHT":
      return "Front Right";
    case "CAM_BACK_LEFT":
      return "Back Left";
    case "CAM_BACK":
      return "Back";
    case "CAM_BACK_RIGHT":
      return "Back Right";
    default:
      return cam;
  }
}

export function getCamCompactName(cam: string): string {
  switch (cam) {
    case "CAM_FRONT_LEFT": return "Front L";
    case "CAM_FRONT_RIGHT": return "Front R";
    case "CAM_BACK_LEFT": return "Back L";
    case "CAM_BACK_RIGHT": return "Back R";
    default: return getCamFriendlyName(cam);
  }
}

export function CameraImage({
  camDetail,
  showBoxes = true,
  showLidarOverlay = false,
  hideCameraScore = false,
  isFocus = false,
  onClick,
  className = "",
}: CameraImageProps) {
  const [zoom, setZoom] = useState(1);
  const [pan, setPan] = useState({ x: 0, y: 0 });
  const [isDragging, setIsDragging] = useState(false);
  const dragStartRef = useRef({ x: 0, y: 0 });

  const handleWheel = useCallback(
    (e: React.WheelEvent) => {
      if (!isFocus) return;
      e.preventDefault();
      const zoomFactor = e.deltaY < 0 ? 1.15 : 0.87;
      setZoom((z) => Math.min(5, Math.max(1, z * zoomFactor)));
    },
    [isFocus]
  );

  const handleMouseDown = useCallback(
    (e: React.MouseEvent) => {
      if (!isFocus || zoom <= 1) return;
      setIsDragging(true);
      dragStartRef.current = { x: e.clientX - pan.x, y: e.clientY - pan.y };
    },
    [isFocus, zoom, pan]
  );

  const handleMouseMove = useCallback(
    (e: React.MouseEvent) => {
      if (!isDragging || !isFocus) return;
      setPan({
        x: e.clientX - dragStartRef.current.x,
        y: e.clientY - dragStartRef.current.y,
      });
    },
    [isDragging, isFocus]
  );

  const handleMouseUp = useCallback(() => {
    setIsDragging(false);
  }, []);

  const resetZoom = useCallback(() => {
    setZoom(1);
    setPan({ x: 0, y: 0 });
  }, []);

  // Tính các cạnh SVG cho từng box 2D từ 16 số corners
  const renderBoxes = () => {
    if (!showBoxes || !camDetail.boxes) return null;

    return camDetail.boxes.map((b, idx) => {
      if (b.corners.length < 16) return null;
      const pts: [number, number][] = [];
      for (let i = 0; i < 8; i++) {
        pts.push([b.corners[i * 2], b.corners[i * 2 + 1]]);
      }

      // 12 cạnh + 2 đường chéo mặt trước (0-2 và 1-3)
      const edges: [number, number][] = [
        [0, 1], [1, 2], [2, 3], [3, 0], // Mặt trước
        [4, 5], [5, 6], [6, 7], [7, 4], // Mặt sau
        [0, 4], [1, 5], [2, 6], [3, 7], // Nối trước - sau
        [0, 2], [1, 3],                 // Chéo chữ X mặt trước
      ];

      const strokeColor = getCategoryColor(b.category);

      // Điểm góc trên bên trái để đặt nhãn tên category
      const minX = Math.min(...pts.map((p) => p[0]));
      const minY = Math.min(...pts.map((p) => p[1]));

      return (
        <g key={idx} className="transition-opacity">
          {edges.map(([pA, pB], eIdx) => (
            <line
              key={eIdx}
              x1={pts[pA][0]}
              y1={pts[pA][1]}
              x2={pts[pB][0]}
              y2={pts[pB][1]}
              stroke={strokeColor}
              strokeWidth={eIdx >= 12 ? 1.5 : 2}
              strokeDasharray={eIdx >= 12 ? "4 3" : undefined}
              opacity={0.9}
            />
          ))}

          {/* Nhãn loại đối tượng */}
          <rect
            x={minX}
            y={Math.max(0, minY - 18)}
            width={b.category.length * 7 + 10}
            height={16}
            fill="rgba(15, 23, 42, 0.85)"
            rx={3}
          />
          <text
            x={minX + 5}
            y={Math.max(12, minY - 6)}
            fill={strokeColor}
            fontSize={10}
            fontWeight="bold"
            fontFamily="monospace"
          >
            {b.category.split(".").pop()}
          </text>
        </g>
      );
    });
  };

  return (
    <div
      className={`relative group overflow-hidden bg-black/90 rounded-xl select-none ${
        onClick ? "cursor-pointer hover:ring-2 hover:ring-blue-500/50" : ""
      } ${className}`}
      onClick={onClick}
      onWheel={handleWheel}
      onMouseDown={handleMouseDown}
      onMouseMove={handleMouseMove}
      onMouseUp={handleMouseUp}
      onMouseLeave={handleMouseUp}
      data-testid={`camera-${camDetail.cam}`}
    >
      {/* Vùng ảnh và SVG vẽ box */}
      <div
        className="w-full h-full relative flex items-center justify-center transition-transform duration-75"
        style={{
          transform: isFocus
            ? `translate(${pan.x}px, ${pan.y}px) scale(${zoom})`
            : undefined,
          cursor: isFocus && zoom > 1 ? (isDragging ? "grabbing" : "grab") : undefined,
        }}
      >
        {/* eslint-disable-next-line @next/next/no-img-element */}
        <img
          data-testid="cam-image"
          src={camDetail.imageUrl}
          alt={camDetail.cam}
          className="w-full h-full object-contain pointer-events-none"
          loading="lazy"
        />

        {/* Lớp SVG vẽ box */}
        <svg
          viewBox={`0 0 ${camDetail.width} ${camDetail.height}`}
          className="absolute inset-0 w-full h-full pointer-events-none"
          preserveAspectRatio="xMidYMid meet"
        >
          {renderBoxes()}
        </svg>

        {/* Thông báo giả lập lớp LiDAR chiếu lên ảnh (khi bật P) */}
        {showLidarOverlay && (
          <div className="absolute inset-0 bg-blue-500/10 pointer-events-none flex items-center justify-center">
            <span className="text-[11px] text-blue-300 bg-black/60 px-2 py-0.5 rounded">
              LiDAR overlay (P)
            </span>
          </div>
        )}
      </div>

      {/* Header thông tin camera */}
      <div className="absolute top-1 left-1 z-10 flex min-w-0 max-w-[calc(100%-3rem)] items-center gap-1 bg-black/75 backdrop-blur-md px-1 py-0.5 rounded-md text-[10px] text-white border border-white/10 sm:top-2 sm:left-2 sm:gap-1.5 sm:px-2 sm:py-1 sm:text-xs">
        <span className="min-w-0 truncate font-semibold text-slate-200">
          <span className="sm:hidden">{getCamCompactName(camDetail.cam)}</span>
          <span className="hidden sm:inline">{getCamFriendlyName(camDetail.cam)}</span>
        </span>
        <span
          aria-label={camDetail.qOk ? "Đạt" : "Kém"}
          className={`shrink-0 text-[9px] px-1 py-0.2 rounded font-mono sm:text-[10px] ${
            camDetail.qOk ? "bg-emerald-500/20 text-emerald-400" : "bg-rose-500/20 text-rose-400"
          }`}
        >
          <span className="sm:hidden" aria-hidden="true">{camDetail.qOk ? "✓" : "!"}</span>
          <span className="hidden sm:inline">{camDetail.qOk ? "✓ Đạt" : "✗ Kém"}</span>
        </span>
      </div>

      {/* Điểm của camera */}
      {!hideCameraScore && <div aria-label={`Điểm camera ${camDetail.score.s.toFixed(2)}`} className="absolute top-1 right-1 z-10 flex items-center gap-1 bg-black/75 backdrop-blur-md px-1 py-0.5 rounded-md text-[9px] text-white/80 border border-white/10 font-mono sm:top-2 sm:right-2 sm:px-2 sm:py-1 sm:text-[11px]">
        <span>S: {camDetail.score.s.toFixed(2)}</span>
      </div>}

      {/* Nút điều khiển Zoom khi ở chế độ Focus */}
      {isFocus && (
        <div className="absolute bottom-3 right-3 z-20 flex items-center gap-1 bg-black/80 backdrop-blur-md px-2 py-1 rounded-lg border border-white/10 text-xs text-white">
          <button
            type="button"
            onClick={(e) => {
              e.stopPropagation();
              setZoom((z) => Math.max(1, z - 0.25));
            }}
            aria-label="Thu nhỏ ảnh"
            className="px-1.5 py-0.5 hover:bg-white/20 rounded"
          >
            -
          </button>
          <span className="font-mono text-[11px] px-1">{Math.round(zoom * 100)}%</span>
          <button
            type="button"
            onClick={(e) => {
              e.stopPropagation();
              setZoom((z) => Math.min(5, z + 0.25));
            }}
            aria-label="Phóng to ảnh"
            className="px-1.5 py-0.5 hover:bg-white/20 rounded"
          >
            +
          </button>
          {zoom > 1 && (
            <button
              type="button"
              onClick={(e) => {
                e.stopPropagation();
                resetZoom();
              }}
              aria-label="Đặt lại thu phóng"
              className="ml-1 text-[10px] text-blue-400 hover:text-blue-300"
            >
              Đặt lại
            </button>
          )}
        </div>
      )}
    </div>
  );
}
export default CameraImage;
