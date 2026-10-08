"use client";

import React, { useEffect, useState } from "react";
import { FrameViewer } from "@/components/viewer/FrameViewer";
import { FrameGrid } from "@/components/review/FrameGrid";
import { AnalysisPanel } from "@/components/review/AnalysisPanel";
import { listFrames, getAnalysis } from "@/lib/api/client";
import type { FrameSummary, Analysis } from "@/lib/api/types";

type ViewTab = "surround" | "focus" | "review";

export default function DevViewerPage() {
  const [activeTab, setActiveTab] = useState<ViewTab>("surround");
  const [frames, setFrames] = useState<FrameSummary[]>([]);
  const [analysis, setAnalysis] = useState<Analysis | null>(null);
  const [selectedToken, setSelectedToken] = useState<string>("mock-f01");
  const [viewerOpen, setViewerOpen] = useState(false);
  const [viewerToken, setViewerToken] = useState("mock-f01");
  const [loading, setLoading] = useState(true);

  // Tải mock frames và mock analysis
  useEffect(() => {
    Promise.all([
      listFrames("job-mock-01", "sel-balanced"),
      getAnalysis("job-mock-01", "sel-balanced"),
    ])
      .then(([fList, anData]) => {
        setFrames(fList);
        setAnalysis(anData);
        if (fList.length > 0) {
          setSelectedToken(fList[0].sampleToken);
        }
        setLoading(false);
      })
      .catch((err) => {
        console.error("Lỗi nạp mock data:", err);
        setLoading(false);
      });
  }, []);

  return (
    <div className="min-h-screen bg-[#F7F8FA] text-[#0F172A] flex flex-col font-sans">
      {/* Thanh điều hướng trang dev */}
      <header className="h-14 bg-white border-b border-slate-200 px-6 flex items-center justify-between shrink-0 shadow-xs z-20">
        <div className="flex items-center gap-3">
          <div className="w-7 h-7 rounded-lg bg-blue-600 flex items-center justify-center text-white font-bold text-sm">
            V
          </div>
          <span className="font-bold text-base tracking-tight text-slate-900">
            VCuboidFIT Dev Viewer
          </span>
          <span className="bg-amber-100 text-amber-800 text-[11px] font-semibold px-2 py-0.5 rounded-full border border-amber-200">
            P03a Test Page (Mock)
          </span>
        </div>

        {/* Nút chuyển đổi 3 chế độ thử nghiệm */}
        <div className="flex items-center gap-1 bg-slate-100 p-1 rounded-lg border border-slate-200 text-xs font-medium">
          <button
            type="button"
            id="tab-surround"
            onClick={() => setActiveTab("surround")}
            className={`px-3 py-1.5 rounded-md transition-colors ${
              activeTab === "surround"
                ? "bg-white text-blue-600 shadow-xs font-semibold"
                : "text-slate-600 hover:text-slate-900"
            }`}
          >
            1. Viewer (Surround)
          </button>
          <button
            type="button"
            id="tab-focus"
            onClick={() => setActiveTab("focus")}
            className={`px-3 py-1.5 rounded-md transition-colors ${
              activeTab === "focus"
                ? "bg-white text-blue-600 shadow-xs font-semibold"
                : "text-slate-600 hover:text-slate-900"
            }`}
          >
            2. Viewer (Focus)
          </button>
          <button
            type="button"
            id="tab-review"
            onClick={() => setActiveTab("review")}
            className={`px-3 py-1.5 rounded-md transition-colors ${
              activeTab === "review"
                ? "bg-white text-blue-600 shadow-xs font-semibold"
                : "text-slate-600 hover:text-slate-900"
            }`}
          >
            3. Deep Review
          </button>
        </div>

        <div className="text-xs text-slate-500 font-mono">
          NEXT_PUBLIC_MOCK=1
        </div>
      </header>

      {/* Nội dung theo tab đang chọn */}
      <main className="flex-1 relative overflow-hidden">
        {loading ? (
          <div className="h-full flex items-center justify-center text-slate-400">
            Đang tải dữ liệu mock...
          </div>
        ) : activeTab === "surround" ? (
          // Chế độ 1: FrameViewer Surround
          <div className="h-[calc(100vh-3.5rem)] relative" id="view-surround">
            <FrameViewer
              jobId="job-mock-01"
              token={selectedToken}
              sid="sel-balanced"
              onClose={() => setActiveTab("review")}
              onPrev={() => {
                const curIdx = frames.findIndex((f) => f.sampleToken === selectedToken);
                if (curIdx > 0) setSelectedToken(frames[curIdx - 1].sampleToken);
              }}
              onNext={() => {
                const curIdx = frames.findIndex((f) => f.sampleToken === selectedToken);
                if (curIdx >= 0 && curIdx < frames.length - 1) {
                  setSelectedToken(frames[curIdx + 1].sampleToken);
                }
              }}
            />
          </div>
        ) : activeTab === "focus" ? (
          // Chế độ 2: FrameViewer Focus
          <div className="h-[calc(100vh-3.5rem)] relative" id="view-focus">
            <FrameViewer
              jobId="job-mock-01"
              token={selectedToken}
              sid="sel-balanced"
              onClose={() => setActiveTab("review")}
              onPrev={() => {
                const curIdx = frames.findIndex((f) => f.sampleToken === selectedToken);
                if (curIdx > 0) setSelectedToken(frames[curIdx - 1].sampleToken);
              }}
              onNext={() => {
                const curIdx = frames.findIndex((f) => f.sampleToken === selectedToken);
                if (curIdx >= 0 && curIdx < frames.length - 1) {
                  setSelectedToken(frames[curIdx + 1].sampleToken);
                }
              }}
            />
          </div>
        ) : (
          // Chế độ 3: Deep Review (Lưới FrameGrid + Bảng AnalysisPanel)
          <div
            className="h-[calc(100vh-3.5rem)] overflow-y-auto p-6 flex flex-col lg:flex-row gap-6 max-w-7xl mx-auto"
            id="view-review"
          >
            {/* Vùng trái (9 phần) - Danh sách FrameGrid */}
            <div className="flex-1 flex flex-col gap-4 min-w-0">
              <div className="flex items-center justify-between">
                <div>
                  <h2 className="text-lg font-bold text-slate-900">
                    Danh sách frame tuyển chọn (5%)
                  </h2>
                  <p className="text-xs text-slate-500">
                    {frames.length} frames · Nhấn Enter hoặc click đúp để mở Frame Viewer
                  </p>
                </div>
              </div>

              <FrameGrid
                frames={frames}
                selectedToken={selectedToken}
                onSelectFrame={(f) => setSelectedToken(f.sampleToken)}
                onOpenViewer={(f) => {
                  setViewerToken(f.sampleToken);
                  setViewerOpen(true);
                }}
              />
            </div>

            {/* Vùng phải (3 phần) - Bảng AnalysisPanel */}
            <div className="w-full lg:w-[420px] shrink-0">
              {analysis && (
                <AnalysisPanel
                  analysis={analysis}
                  onFilterChange={(metricKey) => {
                    console.log("Filter metric selected:", metricKey);
                  }}
                />
              )}
            </div>

            {/* Modal Viewer khi mở từ Review */}
            {viewerOpen && (
              <FrameViewer
                jobId="job-mock-01"
                token={viewerToken}
                sid="sel-balanced"
                onClose={() => setViewerOpen(false)}
              />
            )}
          </div>
        )}
      </main>
    </div>
  );
}
