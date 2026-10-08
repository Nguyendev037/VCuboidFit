"use client";

import React, { useState, useMemo, useCallback, useEffect } from "react";
import Link from "next/link";
import { useRouter, usePathname, useSearchParams } from "next/navigation";
import { useQuery } from "@tanstack/react-query";
import {
  getAnalysis,
  listFrames
} from "@/lib/api/client";
import type { FrameSummary } from "@/lib/api/types";
import { LIDAR_TAG_LABELS } from "@/lib/constants";
import { FrameGrid } from "@/components/review/FrameGrid";
import { AnalysisPanel } from "@/components/review/AnalysisPanel";
import { FrameViewer } from "@/components/viewer/FrameViewer";

const pct = (x: number) => `${Math.round(x * 100)}%`;
const DEFAULT_BUDGET = 0.05;

/** Chip lọc tag cho pipeline LiDAR (tag nhóm GT do API sinh). */
export const LIDAR_FILTER_TAGS = [
  "Hiếm",
  "Khó",
  "Rare GT A",
  "Rare GT B",
  "Rare GT Bp",
  "Rare GT C",
  "rare (cell)",
];

/** Chip lọc tag cho pipeline camera (giữ nguyên hành vi cũ). */
export const CAMERA_FILTER_TAGS = ["Hiếm", "Khó", "Kịch bản", "Rare GT A", "Rare GT B", "Rare GT C"];

/**
 * Kiểm tra một frame có khớp với chip lọc tag đang chọn.
 * - LiDAR: chip "Hiếm" dùng `rRar`; chip "Rare GT X" khớp tag chính xác; riêng chip "rare (cell)" khớp tag đó.
 * - Camera: giữ nguyên hành vi cũ (`rNov` cho "Hiếm", khớp tag chứa hoặc `Rare <nhóm>`).
 */
export function matchesTagFilter(frame: FrameSummary, selectedTag: string, isLidar: boolean): boolean {
  const hasTag = (tag: string) => frame.tags.includes(tag);

  if (selectedTag === "duplicates") {
    return frame.tags.some((tag) => tag.startsWith("Trùng với #"));
  }

  if (selectedTag === "Hiếm") {
    if (isLidar) return hasTag("Hiếm") || (frame.rRar ?? 0) > 0.6;
    return hasTag("Hiếm") || frame.rNov > 0.6;
  }
  if (selectedTag === "Khó") return hasTag("Khó") || frame.rUnc > 0.6;
  if (isLidar && selectedTag === "rare (cell)") return hasTag("rare (cell)");
  if (!isLidar && selectedTag === "Kịch bản") return hasTag("Kịch bản") || frame.rQry > 0.6;

  if (selectedTag.startsWith("Rare GT")) {
    if (isLidar) return hasTag(selectedTag);
    if (frame.tags.some((t) => t.includes(selectedTag))) return true;
    const group = selectedTag.replace("Rare GT ", "");
    return hasTag(group) || hasTag(`Rare ${group}`);
  }

  return true;
}

export interface ReviewClientProps {
  jobId: string;
}

export default function ReviewClient({ jobId }: ReviewClientProps) {
  const router = useRouter();
  const pathname = usePathname();
  const searchParams = useSearchParams();

  const sel = searchParams.get("sel");
  const datasetId = searchParams.get("dataset");
  const budget = Number(searchParams.get("budget") ?? DEFAULT_BUDGET);
  const token = searchParams.get("frame");

  // Bộ lọc tìm kiếm và tags theo Figma 03
  const [searchQuery, setSearchQuery] = useState("");
  const [selectedTag, setSelectedTag] = useState<string | null>(null);
  const [sortBy, setSortBy] = useState<"rank" | "score">("rank");
  const [viewMode, setViewMode] = useState<"grid" | "list">("grid");

  // Tải danh sách frames
  const framesQuery = useQuery({
    queryKey: ["frames", jobId, sel, budget, sortBy],
    queryFn: () =>
      listFrames(jobId, sel!, {
        budget,
        sort: sortBy,
        page: 1,
        pageSize: 200,
      }),
    enabled: !!sel,
  });

  // Tải dữ liệu phân tích
  const analysisQuery = useQuery({
    queryKey: ["analysis", jobId, sel],
    queryFn: () => getAnalysis(jobId, sel!),
    enabled: !!sel,
  });

  const rawList = useMemo(() => framesQuery.data ?? [], [framesQuery.data]);
  const isLidar = useMemo(
    () => rawList.some((f) => f.bestCam === "LIDAR_TOP" || !!f.bevUrl || typeof f.rRar === "number"),
    [rawList],
  );

  // Lọc theo từ khoá tìm kiếm và tag được chọn
  const filteredList = useMemo(() => {
    return rawList.filter((f) => {
      if (searchQuery) {
        const q = searchQuery.toLowerCase();
        const matchesScene = f.sceneName.toLowerCase().includes(q);
        const matchesToken = f.sampleToken.toLowerCase().includes(q);
        const matchesReason = f.reason.toLowerCase().includes(q);
        if (!matchesScene && !matchesToken && !matchesReason) return false;
      }

      if (selectedTag && !matchesTagFilter(f, selectedTag, isLidar)) return false;

      return true;
    });
  }, [rawList, searchQuery, selectedTag, isLidar]);

  const activeIdx = useMemo(() => {
    if (!token) return -1;
    return filteredList.findIndex((f) => f.sampleToken === token);
  }, [filteredList, token]);

  // Điều hướng cập nhật URL query param
  const setFrame = useCallback(
    (next: string | null, mode: "push" | "replace") => {
      const p = new URLSearchParams(searchParams.toString());
      if (next) p.set("frame", next);
      else p.delete("frame");
      const url = p.size ? `${pathname}?${p}` : pathname;
      if (mode === "push") router.push(url, { scroll: false });
      else router.replace(url, { scroll: false });
    },
    [pathname, router, searchParams],
  );

  // Xử lý phím tắt ←/→ chuyển frame trong danh sách lọc; Esc đóng
  useEffect(() => {
    if (!token) return;
    function onKey(e: KeyboardEvent) {
      const target = e.target as HTMLElement | null;
      if (target && ["INPUT", "TEXTAREA", "SELECT"].includes(target.tagName)) return;
      if (e.altKey || e.ctrlKey || e.metaKey) return;

      if (e.key === "Escape") {
        setFrame(null, "replace");
        e.preventDefault();
      } else if (e.key === "ArrowRight") {
        if (activeIdx >= 0 && activeIdx < filteredList.length - 1) {
          setFrame(filteredList[activeIdx + 1].sampleToken, "replace");
        }
        e.preventDefault();
      } else if (e.key === "ArrowLeft") {
        if (activeIdx > 0) {
          setFrame(filteredList[activeIdx - 1].sampleToken, "replace");
        }
        e.preventDefault();
      }
    }

    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [token, activeIdx, filteredList, setFrame]);

  if (!sel) {
    return (
      <main className="min-h-screen bg-[#F7F8FA] p-8 flex flex-col items-center justify-center font-sans">
        <div className="bg-white p-6 rounded-xl border border-slate-200 shadow-sm text-center max-w-md">
          <p role="alert" className="text-sm font-semibold text-rose-600 mb-2">
            Thiếu tham số <code>sel</code> trong địa chỉ URL.
          </p>
          <p className="text-xs text-slate-500 mb-4">
            Vui lòng thực hiện phân tích từ trang chủ để xem Deep Review.
          </p>
          <Link
            href={`/?job=${encodeURIComponent(jobId)}${datasetId ? `&dataset=${encodeURIComponent(datasetId)}` : ""}${sel ? `&sel=${encodeURIComponent(sel)}` : ""}`}
            className="px-4 py-2 bg-blue-600 text-white text-xs font-semibold rounded-lg hover:bg-blue-700 transition-colors inline-block"
          >
            ← Quay lại trang chủ
          </Link>
        </div>
      </main>
    );
  }

  const analysisData = analysisQuery.data;

  return (
    <div className="min-h-screen bg-[#F7F8FA] text-[#0F172A] flex flex-col font-sans">
      {/* 1. Top Header theo Figma (Screens 03) */}
      <header className="w-full bg-white border-b border-[#E2E8F0] px-4 sm:px-8 py-3.5 flex flex-wrap items-center justify-between gap-3 shadow-xs sticky top-0 z-30">
        <div className="flex items-center gap-6">
          <Link href={`/?job=${encodeURIComponent(jobId)}${datasetId ? `&dataset=${encodeURIComponent(datasetId)}` : ""}${sel ? `&sel=${encodeURIComponent(sel)}` : ""}`} className="flex items-center gap-2.5 font-bold text-lg text-slate-900 tracking-tight">
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
            <span className="text-xs font-semibold text-slate-800">nuScenes v1.0-mini</span>
          </div>
        </div>

        <div className="flex items-center gap-4">
          <span className="text-xs text-slate-500 font-mono">Job {jobId}</span>
          <span className="px-3 py-1 text-xs font-semibold rounded-full bg-emerald-50 text-emerald-700 border border-emerald-200 flex items-center gap-1.5">
            <span className="w-1.5 h-1.5 rounded-full bg-emerald-500" />
            Hoàn tất
          </span>
        </div>
      </header>

      {/* 2. Action Bar theo Figma 03 (Screens 03 Action Row) */}
      <div className="bg-white border-b border-[#E2E8F0] px-4 sm:px-8 py-3 flex flex-wrap items-center justify-between gap-4">
        <div className="flex flex-wrap items-center gap-2 sm:gap-3">
          <Link
            href={`/?job=${encodeURIComponent(jobId)}${datasetId ? `&dataset=${encodeURIComponent(datasetId)}` : ""}${sel ? `&sel=${encodeURIComponent(sel)}` : ""}`}
            className="px-3 py-1.5 text-xs font-semibold text-slate-600 hover:text-slate-900 bg-slate-50 hover:bg-slate-100 rounded-lg border border-slate-200 flex items-center gap-1.5 transition-colors"
          >
            ← Quay lại
          </Link>
          <span className="px-2.5 py-1 text-xs font-medium rounded-full bg-blue-50 text-blue-700 border border-blue-200">
            Ngân sách {pct(budget)} · {rawList.length} frame
          </span>
          <span className="px-2.5 py-1 text-xs font-medium rounded-full bg-slate-100 text-slate-700 border border-slate-200 capitalize">
            ID lựa chọn: {sel}
          </span>
        </div>

        <div className="flex items-center gap-2 flex-wrap">
          {/* Ô tìm kiếm scene */}
          <div className="relative">
            <svg
              className="w-3.5 h-3.5 text-slate-400 absolute left-2.5 top-1/2 -translate-y-1/2"
              fill="none"
              stroke="currentColor"
              viewBox="0 0 24 24"
              strokeWidth="2"
            >
              <path strokeLinecap="round" strokeLinejoin="round" d="M21 21l-6-6m2-5a7 7 0 11-14 0 7 7 0 0114 0z" />
            </svg>
            <input
              type="text"
              placeholder="Tìm theo scene..."
              value={searchQuery}
              onChange={(e) => setSearchQuery(e.target.value)}
              aria-label="Tìm frame theo scene"
              className="text-xs pl-8 pr-3 py-1.5 border border-slate-200 rounded-lg bg-slate-50 focus:bg-white focus:outline-none focus:ring-1 focus:ring-blue-600 w-44"
            />
          </div>

          {/* Filter chips theo Figma */}
          {(isLidar ? LIDAR_FILTER_TAGS : CAMERA_FILTER_TAGS).map((tag) => {
            const isActive = selectedTag === tag;
            const label = isLidar ? LIDAR_TAG_LABELS[tag] ?? tag : tag;
            return (
              <button
                key={tag}
                type="button"
                onClick={() => setSelectedTag(isActive ? null : tag)}
                className={`px-2.5 py-1 rounded-full text-xs font-medium border transition-colors ${
                  isActive
                    ? "bg-blue-600 text-white border-blue-600"
                    : "bg-slate-50 hover:bg-slate-100 text-slate-600 border-slate-200"
                }`}
              >
                {label}
              </button>
            );
          })}

          {/* Sắp xếp */}
          <select
            value={sortBy}
            onChange={(e) => setSortBy(e.target.value as "rank" | "score")}
            aria-label="Sắp xếp frame"
            className="text-xs border border-slate-200 rounded-lg px-2 py-1.5 text-slate-700 bg-white"
          >
            <option value="rank">Sắp xếp: Rank</option>
            <option value="score">Sắp xếp: Score S</option>
          </select>

          {/* View toggle */}
          <div className="flex items-center border border-slate-200 rounded-lg p-0.5 bg-slate-50">
            <button
              type="button"
              onClick={() => setViewMode("grid")}
              title="Lưới"
              aria-label="Xem dạng lưới"
              aria-pressed={viewMode === "grid"}
              className={`p-1 rounded ${viewMode === "grid" ? "bg-white shadow-xs text-blue-600" : "text-slate-400"}`}
            >
              <svg className="w-3.5 h-3.5" fill="none" stroke="currentColor" viewBox="0 0 24 24" strokeWidth="2">
                <rect x="3" y="3" width="7" height="7" />
                <rect x="14" y="3" width="7" height="7" />
                <rect x="3" y="14" width="7" height="7" />
                <rect x="14" y="14" width="7" height="7" />
              </svg>
            </button>
            <button
              type="button"
              onClick={() => setViewMode("list")}
              title="Danh sách"
              aria-label="Xem dạng danh sách"
              aria-pressed={viewMode === "list"}
              className={`p-1 rounded ${viewMode === "list" ? "bg-white shadow-xs text-blue-600" : "text-slate-400"}`}
            >
              <svg className="w-3.5 h-3.5" fill="none" stroke="currentColor" viewBox="0 0 24 24" strokeWidth="2">
                <line x1="8" y1="6" x2="21" y2="6" />
                <line x1="8" y1="12" x2="21" y2="12" />
                <line x1="8" y1="18" x2="21" y2="18" />
                <line x1="3" y1="6" x2="3.01" y2="6" />
                <line x1="3" y1="12" x2="3.01" y2="12" />
                <line x1="3" y1="18" x2="3.01" y2="18" />
              </svg>
            </button>
          </div>
        </div>
      </div>

      {/* Hiển thị lỗi nếu có */}
      {/* 3. Bố cục chính 2 cột: Cột trái (Lưới frames) & Cột phải (Analysis Panel) */}
      <main className="max-w-[1440px] mx-auto p-4 sm:p-6 w-full grid grid-cols-1 lg:grid-cols-12 gap-6 flex-1 items-start">
        {/* ============ CỘT TRÁI (LƯỚI FRAMES - 8 CỘT) ============ */}
        <section className="min-w-0 lg:col-span-9 flex flex-col gap-4">
          <div className="flex flex-wrap items-baseline justify-between gap-2">
            <h2 className="font-bold text-sm text-slate-800">
              Danh sách Frame ({filteredList.length} / {rawList.length})
            </h2>
            <span className="text-xs text-slate-400">
              Bấm vào thẻ để mở Frame Viewer 3D
            </span>
          </div>

          {framesQuery.isPending ? (
            <div role="status" aria-live="polite" className="grid grid-cols-1 sm:grid-cols-2 xl:grid-cols-3 gap-3">
              {Array.from({ length: 6 }, (_, index) => (
                <div key={index} aria-hidden="true" className="aspect-video rounded-xl border border-slate-200 bg-white animate-pulse" />
              ))}
              <span className="sr-only">Đang tải danh sách frame</span>
            </div>
          ) : framesQuery.isError ? (
            <div role="alert" className="flex flex-wrap items-center justify-center gap-3 rounded-xl border border-rose-200 bg-rose-50 p-5 text-center text-sm text-rose-800">
              <span>Không tải được danh sách frame.</span>
              <button type="button" onClick={() => void framesQuery.refetch()} className="min-h-9 rounded-md border border-rose-300 bg-white px-3 text-xs font-semibold hover:bg-rose-100 focus-visible:outline focus-visible:outline-2 focus-visible:outline-rose-700">Thử lại</button>
            </div>
          ) : filteredList.length === 0 ? (
            <div className="rounded-xl border border-slate-200 bg-white p-6 text-center">
              <p className="text-sm font-semibold text-slate-800">Không có frame phù hợp</p>
              <p className="mt-1 text-xs text-slate-500">Thử xóa từ khóa hoặc bộ lọc để xem lại danh sách.</p>
              {(searchQuery || selectedTag) && (
                <button
                  type="button"
                  onClick={() => { setSearchQuery(""); setSelectedTag(null); }}
                  className="mt-3 rounded-md border border-slate-300 px-3 py-2 text-xs font-semibold text-slate-700 hover:bg-slate-50 focus-visible:outline focus-visible:outline-2 focus-visible:outline-blue-600"
                >
                  Xóa bộ lọc
                </button>
              )}
            </div>
          ) : (
            <FrameGrid
              frames={filteredList}
              selectedToken={token ?? undefined}
              onSelectFrame={(f: FrameSummary) => setFrame(f.sampleToken, "push")}
              onOpenViewer={(f: FrameSummary) => setFrame(f.sampleToken, "push")}
              viewMode={viewMode}
              pipeline={isLidar ? "lidar" : "camera"}
            />
          )}
        </section>

        {/* ============ CỘT PHẢI (BẢNG PHÂN TÍCH - 4 CỘT) ============ */}
        <aside className="min-w-0 lg:col-span-3 sticky top-20 flex flex-col gap-4">
          {analysisData ? (
            <AnalysisPanel
              analysis={analysisData}
              selectedFilter={selectedTag ?? undefined}
              onFilterChange={(tagKey) => {
                setSelectedTag(selectedTag === tagKey ? null : tagKey);
              }}
              pipeline={isLidar ? "lidar" : "camera"}
            />
          ) : analysisQuery.isPending ? (
            <div role="status" aria-live="polite" className="p-6 bg-white rounded-xl border border-slate-200 text-center text-xs text-slate-600">
              <span className="inline-flex items-center gap-2"><span aria-hidden="true" className="h-4 w-4 animate-spin rounded-full border-2 border-blue-600 border-t-transparent" />Đang tải phân tích...</span>
            </div>
          ) : analysisQuery.isError ? (
            <div role="alert" className="p-6 bg-rose-50 rounded-xl border border-rose-200 text-center text-xs font-medium text-rose-800">
              <p>Không tải được dữ liệu phân tích.</p>
              <button type="button" onClick={() => void analysisQuery.refetch()} className="mt-3 min-h-9 rounded-md border border-rose-300 bg-white px-3 text-xs font-semibold hover:bg-rose-100 focus-visible:outline focus-visible:outline-2 focus-visible:outline-rose-700">Thử lại</button>
            </div>
          ) : (
            <div role="status" className="p-6 bg-white rounded-xl border border-slate-200 text-center text-xs text-slate-600">
              Chưa có dữ liệu phân tích cho lựa chọn này.
            </div>
          )}
        </aside>
      </main>

      {/* 4. Overlay Frame Viewer toàn màn hình khi có ?frame=<token> */}
      {token && (
        <FrameViewer
          jobId={jobId}
          token={token}
          sid={sel}
          onPrev={
            activeIdx > 0
              ? () => setFrame(filteredList[activeIdx - 1].sampleToken, "replace")
              : undefined
          }
          onNext={
            activeIdx >= 0 && activeIdx < filteredList.length - 1
              ? () => setFrame(filteredList[activeIdx + 1].sampleToken, "replace")
              : undefined
          }
          onClose={() => setFrame(null, "replace")}
        />
      )}
    </div>
  );
}
