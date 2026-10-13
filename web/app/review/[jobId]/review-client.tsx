"use client";
import { DataError } from "@/components/ui/DataState";

import React, { useState, useMemo, useCallback, useEffect } from "react";
import Link from "next/link";
import { useRouter, usePathname, useSearchParams } from "next/navigation";
import { useQuery } from "@tanstack/react-query";
import {
  getAnalysis,
  exportUrl,
  getSelection,
  listFrames
} from "@/lib/api/client";
import type { FrameSummary } from "@/lib/api/types";
import { ExportImages } from "@/components/review/ExportImages";
import { PRED_TAG_LABELS } from "@/lib/glossary";
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
  if (selectedTag in PRED_TAG_LABELS) return selectedTag === "R" ? frame.tags.some(t=>["R1","R2","R3"].includes(t)) : hasTag(selectedTag);

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
  const [gate, setGate] = useState("all");
  const [page, setPage] = useState(1);
  const [sortBy, setSortBy] = useState<"rank" | "score">("rank");
  const [viewMode, setViewMode] = useState<"grid" | "list">("grid");

  // Tải danh sách frames
  const framesQuery = useQuery({
    queryKey: ["frames", jobId, sel, budget, sortBy, page, selectedTag],
    queryFn: () =>
      listFrames(jobId, sel!, {
        budget,
        sort: sortBy,
        page,
        tag: selectedTag && selectedTag in PRED_TAG_LABELS ? selectedTag : undefined,
        pageSize: 200,
      }),
    enabled: !!sel,
  });

  const selectionQuery = useQuery({queryKey:["selection",jobId,sel],queryFn:()=>getSelection(jobId,sel!),enabled:!!sel});
  const isRare = selectionQuery.data?.engineVersion === "rare_v24";
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
  const showLidarModelMetrics = useMemo(
    () => rawList.some((f) => f.rNov !== 0 || f.rUnc !== 0),
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

      if (isRare && gate !== "all" && gate !== "valid") return false;
      if (selectedTag && !matchesTagFilter(f, selectedTag, isLidar)) return false;

      return true;
    });
  }, [rawList, searchQuery, selectedTag, isLidar, gate, isRare]);

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
      <main className="min-h-screen bg-vcf-bg p-8 flex flex-col items-center justify-center font-sans">
        <div className="bg-vcf-surface p-6 rounded-vcf-card border border-vcf-border shadow-sm text-center max-w-md">
          <p role="alert" className="text-sm font-semibold text-vcf-danger mb-2">
            Thiếu tham số <code>sel</code> trong địa chỉ URL.
          </p>
          <p className="text-xs text-vcf-subtle mb-4">
            Vui lòng thực hiện phân tích từ trang chủ để xem Deep Review.
          </p>
          <Link
            href={`/dashboard?job=${encodeURIComponent(jobId)}${datasetId ? `&dataset=${encodeURIComponent(datasetId)}` : ""}${sel ? `&sel=${encodeURIComponent(sel)}` : ""}`}
            className="px-4 py-2 bg-vcf-accent text-vcf-on-accent text-xs font-semibold rounded-vcf-control hover:bg-vcf-accent-ink transition-colors inline-block"
          >
            ← Quay lại trang chủ
          </Link>
        </div>
      </main>
    );
  }

  const analysisData = analysisQuery.data;

  return (
    <div className="min-h-screen bg-vcf-bg text-vcf-text flex flex-col font-sans">
      {/* 1. Top Header theo Figma (Screens 03) */}
      <header className="w-full bg-vcf-surface border-b border-vcf-border px-4 sm:px-8 py-3.5 flex flex-wrap items-center justify-between gap-3 shadow-xs sticky top-0 z-30">
        <div className="flex items-center gap-6">
          <Link href={`/dashboard?job=${encodeURIComponent(jobId)}${datasetId ? `&dataset=${encodeURIComponent(datasetId)}` : ""}${sel ? `&sel=${encodeURIComponent(sel)}` : ""}`} className="flex items-center gap-2.5 font-bold text-lg text-vcf-text tracking-tight">
            <div className="w-7 h-7 rounded-vcf-control bg-vcf-accent flex items-center justify-center text-vcf-on-accent shadow-xs">
              <svg className="w-4 h-4" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5">
                <path d="M21 16V8a2 2 0 0 0-1-1.73l-7-4a2 2 0 0 0-2 0l-7 4A2 2 0 0 0 3 8v8a2 2 0 0 0 1 1.73l7 4a2 2 0 0 0 2 0l7-4A2 2 0 0 0 21 16z" />
                <polyline points="3.27 6.96 12 12.01 20.73 6.96" />
                <line x1="12" y1="22.08" x2="12" y2="12" />
              </svg>
            </div>
            <span>VCuboidFIT</span>
          </Link>

          <div className="hidden sm:flex flex-col border-l border-vcf-border pl-4">
            <span className="text-vcf-caption text-vcf-subtle uppercase tracking-wider font-semibold">Dataset</span>
            <span className="text-xs font-semibold text-vcf-text">nuScenes v1.0-mini</span>
          </div>
        </div>

        <div className="flex items-center gap-4">
          <span className="text-xs text-vcf-subtle font-mono">Job {jobId}</span>
          <span className="px-3 py-1 text-xs font-semibold rounded-vcf-pill bg-vcf-good-soft text-vcf-good border border-vcf-good-soft flex items-center gap-1.5">
            <span className="w-1.5 h-1.5 rounded-vcf-pill bg-vcf-good" />
            Hoàn tất
          </span>
        </div>
      </header>

      {/* 2. Action Bar theo Figma 03 (Screens 03 Action Row) */}
      <div className="bg-vcf-surface border-b border-vcf-border px-4 sm:px-8 py-3 flex flex-wrap items-center justify-between gap-4">
        <div className="flex flex-wrap items-center gap-2 sm:gap-3">
          <Link
            href={`/dashboard?job=${encodeURIComponent(jobId)}${datasetId ? `&dataset=${encodeURIComponent(datasetId)}` : ""}${sel ? `&sel=${encodeURIComponent(sel)}` : ""}`}
            className="px-3 py-1.5 text-xs font-semibold text-vcf-muted hover:text-vcf-text bg-vcf-bg hover:bg-vcf-surface-muted rounded-vcf-control border border-vcf-border flex items-center gap-1.5 transition-colors"
          >
            ← Quay lại
          </Link>
          <span className="px-2.5 py-1 text-xs font-medium rounded-vcf-pill bg-vcf-accent-soft text-vcf-accent-ink border border-vcf-accent-soft">
            Ngân sách {pct(budget)} · {rawList.length} frame
          </span>
          <span className="px-2.5 py-1 text-xs font-medium rounded-vcf-pill bg-vcf-surface-muted text-vcf-muted border border-vcf-border capitalize">
            ID lựa chọn: {sel}
          </span>
        </div>

        <div className="flex items-center gap-2 flex-wrap">
          {/* Ô tìm kiếm scene */}
          <div className="relative">
            <svg
              className="w-3.5 h-3.5 text-vcf-subtle absolute left-2.5 top-1/2 -translate-y-1/2"
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
              className="text-xs pl-8 pr-3 py-1.5 border border-vcf-border rounded-vcf-control bg-vcf-bg focus:bg-vcf-surface focus:outline-none focus:ring-1 focus:ring-vcf-accent w-44"
            />
          </div>

          {/* Filter chips theo Figma */}
          {(isRare ? Object.keys(PRED_TAG_LABELS) : isLidar ? LIDAR_FILTER_TAGS : CAMERA_FILTER_TAGS).map((tag) => {
            const isActive = selectedTag === tag;
            const label = isRare ? `${PRED_TAG_LABELS[tag]} (dự đoán)` : isLidar ? LIDAR_TAG_LABELS[tag] ?? tag : tag;
            return (
              <button
                key={tag}
                type="button"
                onClick={() => { setSelectedTag(isActive ? null : tag); setPage(1); }}
                className={`px-2.5 py-1 rounded-vcf-pill text-xs font-medium border transition-colors ${
                  isActive
                    ? "bg-vcf-accent text-vcf-on-accent border-vcf-accent"
                    : "bg-vcf-bg hover:bg-vcf-surface-muted text-vcf-muted border-vcf-border"
                }`}
              >
                {label}
              </button>
            );
          })}

          {isRare && <label className="text-xs">Gate <select aria-label="Lọc gate" value={gate} onChange={e=>setGate(e.target.value)}><option value="all">Tất cả</option><option value="valid">Hợp lệ</option><option value="suspect">Đáng ngờ</option><option value="outlier">Ngoại lệ</option></select></label>}
          {/* Sắp xếp */}
          <select
            value={sortBy}
            onChange={(e) => setSortBy(e.target.value as "rank" | "score")}
            aria-label="Sắp xếp frame"
            className="text-xs border border-vcf-border rounded-vcf-control px-2 py-1.5 text-vcf-muted bg-vcf-surface"
          >
            <option value="rank">Sắp xếp: Rank</option>
            <option value="score">Sắp xếp: Score S</option>
          </select>

          {/* View toggle */}
          <div className="flex items-center border border-vcf-border rounded-vcf-control p-0.5 bg-vcf-bg">
            <button
              type="button"
              onClick={() => setViewMode("grid")}
              title="Lưới"
              aria-label="Xem dạng lưới"
              aria-pressed={viewMode === "grid"}
              className={`p-1 rounded-vcf-small ${viewMode === "grid" ? "bg-vcf-surface shadow-xs text-vcf-accent" : "text-vcf-subtle"}`}
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
              className={`p-1 rounded-vcf-small ${viewMode === "list" ? "bg-vcf-surface shadow-xs text-vcf-accent" : "text-vcf-subtle"}`}
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

      <div className="flex flex-wrap items-center gap-3 px-4 py-3 sm:px-8"><a className="text-xs text-vcf-accent-ink underline" href={exportUrl(jobId,sel,budget)}>Xuất CSV</a><ExportImages jobId={jobId} sid={sel} budget={budget}/><Link className="text-xs text-vcf-accent-ink underline" href={`/review/context?job=${encodeURIComponent(jobId)}&sel=${encodeURIComponent(sel)}`}>Hàng đợi duyệt bối cảnh</Link></div>
      {isRare && <p className="px-8 text-xs text-vcf-subtle">Lô đã chọn chỉ chứa gate hợp lệ; ứng viên đáng ngờ và ngoại lệ không được trộn vào lô.</p>}
      {/* Hiển thị lỗi nếu có */}
      {/* 3. Bố cục chính 2 cột: Cột trái (Lưới frames) & Cột phải (Analysis Panel) */}
      <main className="max-w-[1440px] mx-auto p-4 sm:p-6 w-full grid grid-cols-1 lg:grid-cols-12 gap-6 flex-1 items-start">
        {/* ============ CỘT TRÁI (LƯỚI FRAMES - 8 CỘT) ============ */}
        <section className="min-w-0 lg:col-span-9 flex flex-col gap-4">
          <div className="flex flex-wrap items-baseline justify-between gap-2">
            <h2 className="font-bold text-sm text-vcf-text">
              Danh sách Frame ({filteredList.length} / {rawList.length})
            </h2>
            <span className="text-xs text-vcf-subtle">
              Bấm vào thẻ để mở Frame Viewer 3D
            </span>
          </div>

          {framesQuery.isPending ? (
            <div role="status" aria-live="polite" className="grid grid-cols-1 sm:grid-cols-2 xl:grid-cols-3 gap-3">
              {Array.from({ length: 6 }, (_, index) => (
                <div key={index} aria-hidden="true" className="aspect-video rounded-vcf-card border border-vcf-border bg-vcf-surface animate-pulse" />
              ))}
              <span className="sr-only">Đang tải danh sách frame</span>
            </div>
          ) : framesQuery.isError ? (
            <DataError error={framesQuery.error} onRetry={() => void framesQuery.refetch()} />
          ) : filteredList.length === 0 ? (
            <div className="rounded-vcf-card border border-vcf-border bg-vcf-surface p-6 text-center">
              <p className="text-sm font-semibold text-vcf-text">Không có frame phù hợp</p>
              <p className="mt-1 text-xs text-vcf-subtle">Thử xóa từ khóa hoặc bộ lọc để xem lại danh sách.</p>
              <Link href="/dashboard" className="mt-3 inline-block text-vcf-accent-ink underline">Về dashboard chọn lô khác</Link>
              {(searchQuery || selectedTag) && (
                <button
                  type="button"
                  onClick={() => { setSearchQuery(""); setSelectedTag(null); }}
                  className="mt-3 rounded-vcf-compact border border-vcf-border-strong px-3 py-2 text-xs font-semibold text-vcf-muted hover:bg-vcf-bg focus-visible:outline focus-visible:outline-2 focus-visible:outline-vcf-accent"
                >
                  Xóa bộ lọc
                </button>
              )}
            </div>
          ) : (
            <FrameGrid
              predictionTags={isRare}
              frames={filteredList}
              selectedToken={token ?? undefined}
              onSelectFrame={(f: FrameSummary) => setFrame(f.sampleToken, "push")}
              onOpenViewer={(f: FrameSummary) => setFrame(f.sampleToken, "push")}
              viewMode={viewMode}
              pipeline={isLidar ? "lidar" : "camera"}
              showLidarModelMetrics={showLidarModelMetrics}
            />
          )}
        <div className="flex gap-3 text-xs"><button disabled={page===1} onClick={()=>setPage(v=>v-1)}>Trang trước</button><span>Trang {page}</span><button disabled={rawList.length<200} onClick={()=>setPage(v=>v+1)}>Trang sau</button></div>
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
            <div role="status" aria-live="polite" className="p-6 bg-vcf-surface rounded-vcf-card border border-vcf-border text-center text-xs text-vcf-muted">
              <span className="inline-flex items-center gap-2"><span aria-hidden="true" className="h-4 w-4 animate-spin rounded-vcf-pill border-2 border-vcf-accent border-t-transparent" />Đang tải phân tích...</span>
            </div>
          ) : analysisQuery.isError ? (
            <DataError error={analysisQuery.error} onRetry={() => void analysisQuery.refetch()} />
          ) : (
            <div role="status" className="p-6 bg-vcf-surface rounded-vcf-card border border-vcf-border text-center text-xs text-vcf-muted">
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
          showLidarModelMetrics={showLidarModelMetrics}
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
