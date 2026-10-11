"use client";

import React, { useState, useEffect, useMemo, useRef } from "react";
import Link from "next/link";
import {
  Layers,
  RefreshCw,
  Play,
  CheckCircle2,
  AlertTriangle,
  ShieldCheck,
  Search,
  Filter,
  Eye,
  Car,
  Bike,
  CloudRain,
  User,
  ArrowUpRight,
  TrendingUp,
  FileSpreadsheet,
  BarChart3,
  SlidersHorizontal,
  X,
  Compass,
} from "lucide-react";

interface RankedFrame {
  rank: string;
  rank_nodedup: string;
  fid: string;
  scene: string;
  t: string;
  s_frame: string;
  rule_only: string;
  mean_det_score: string;
  obj_agg: string;
  crowd_count: string;
  night: string;
  rain_score: string;
  ood: string;
  ood_flag: string;
  gate: string;
  gate_fail: string;
  slice_primary: string;
  kept: string;
  selected: string;
  explore: string;
  reasons: string;
}

interface ObjectBox {
  fid: string;
  cid: string;
  source: string;
  class_name: string;
  det_score: string;
  dist_m: string;
  n_points: string;
  L: string;
  W: string;
  H: string;
  cx: string;
  cy: string;
  cz: string;
  yaw: string;
  s_obj: string;
  far: string;
  few: string;
  confusion: string;
  missed_by_model: string;
  reasons: string;
}

interface M6Report {
  n_frames_T: number;
  n_rare_frames: number;
  base_rate: number;
  budgets: number[];
  pipeline: Record<string, number>;
  pipeline_nodedup: Record<string, number>;
  rule_only_ablation: Record<string, number>;
  confidence_only: Record<string, number>;
  random_mean: Record<string, number>;
  random_std: Record<string, number>;
  yield_vru_per_frame: Record<string, number>;
  slices: Record<string, { n_pos: number; R?: number; [k: string]: unknown }>;
  outlier_gate?: {
    counts_T: Record<string, number>;
    injected_leak_rate?: Record<string, { leak_rate: number; suspect_rate: number }>;
  };
}

export default function V2DashboardPage() {
  const [availableRuns, setAvailableRuns] = useState<string[]>([]);
  const [currentRun, setCurrentRun] = useState<string>("outputs_test");
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const [report, setReport] = useState<M6Report | null>(null);
  const [frames, setFrames] = useState<RankedFrame[]>([]);
  const [objects, setObjects] = useState<ObjectBox[]>([]);
  const [review, setReview] = useState<RankedFrame[]>([]);

  // Navigation tab
  const [activeTab, setActiveTab] = useState<"ranking" | "m6" | "inspector" | "gate">("ranking");

  // Filtering
  const [searchQuery, setSearchQuery] = useState("");
  const [selectedSlice, setSelectedSlice] = useState<string>("all");
  const [onlySelected, setOnlySelected] = useState<boolean>(true);

  // Inspector modal/state
  const [inspectFid, setInspectFid] = useState<string | null>(null);

  // Run experiment modal
  const [showRunModal, setShowRunModal] = useState(false);
  const [runBudget, setRunBudget] = useState(50);
  const [runSource, setRunSource] = useState("synthetic");
  const [runningPipeline, setRunningPipeline] = useState(false);
  const [runTerminalLog, setRunTerminalLog] = useState<string | null>(null);

  // Load run data
  const loadRun = async (runName: string) => {
    setLoading(true);
    setError(null);
    try {
      const res = await fetch(`/api/v2/runs?run=${encodeURIComponent(runName)}`);
      if (!res.ok) throw new Error(`HTTP error: ${res.status}`);
      const data = await res.json();
      setAvailableRuns(data.availableRuns || []);
      setCurrentRun(data.selectedRun || runName);
      setReport(data.report || null);
      setFrames(data.frames || []);
      setObjects(data.objects || []);
      setReview(data.review || []);
      if (data.frames && data.frames.length > 0 && !inspectFid) {
        setInspectFid(data.frames[0].fid);
      }
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    loadRun(currentRun);
  }, []);

  // Filtered frames
  const filteredFrames = useMemo(() => {
    return frames.filter((f) => {
      if (onlySelected && f.selected !== "1") return false;
      if (selectedSlice !== "all" && f.slice_primary !== selectedSlice) return false;
      if (searchQuery) {
        const q = searchQuery.toLowerCase();
        const matchFid = f.fid.toLowerCase().includes(q);
        const matchScene = f.scene.toLowerCase().includes(q);
        const matchReasons = f.reasons.toLowerCase().includes(q);
        if (!matchFid && !matchScene && !matchReasons) return false;
      }
      return true;
    });
  }, [frames, onlySelected, selectedSlice, searchQuery]);

  // Objects for inspected frame
  const currentFrameObjects = useMemo(() => {
    if (!inspectFid) return [];
    return objects.filter((o) => o.fid === inspectFid);
  }, [objects, inspectFid]);

  const inspectedFrameInfo = useMemo(() => {
    if (!inspectFid) return null;
    return frames.find((f) => f.fid === inspectFid) || null;
  }, [frames, inspectFid]);

  // Handle run pipeline
  const handleExecuteRun = async () => {
    setRunningPipeline(true);
    setRunTerminalLog("Đang khởi động tiến trình M0-M5 và M6 đánh giá...");
    try {
      const res = await fetch("/api/v2/run", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          budget: runBudget,
          source: runSource,
          runName: `run_b${runBudget}_${Date.now().toString().slice(-4)}`,
        }),
      });
      const data = await res.json();
      if (!res.ok) throw new Error(data.error || "Chạy thất bại");
      setRunTerminalLog(
        (data.runOutput || "") + "\n\n=== M6 BÁO CÁO ===\n" + (data.evalOutput || "")
      );
      // Reload runs
      await loadRun(data.runName);
    } catch (e: unknown) {
      setRunTerminalLog(`LỖI: ${e instanceof Error ? e.message : String(e)}`);
    } finally {
      setRunningPipeline(false);
    }
  };

  return (
    <div className="min-h-screen bg-slate-950 text-slate-100 flex flex-col font-sans">
      {/* Top Navbar */}
      <header className="border-b border-slate-800 bg-slate-900/80 backdrop-blur sticky top-0 z-40 px-4 sm:px-8 py-3.5 flex flex-wrap items-center justify-between gap-4">
        <div className="flex items-center gap-3">
          <div className="w-9 h-9 rounded-xl bg-gradient-to-tr from-indigo-600 to-violet-500 flex items-center justify-center text-white shadow-md shadow-indigo-500/20">
            <Compass className="w-5 h-5" />
          </div>
          <div>
            <div className="flex items-center gap-2">
              <span className="font-bold text-base tracking-tight text-white">VCuboidFIT v2</span>
              <span className="px-2 py-0.5 text-[10px] font-semibold uppercase tracking-wider rounded-md bg-indigo-500/20 text-indigo-300 border border-indigo-500/30">
                v2_beta
              </span>
            </div>
            <p className="text-[11px] text-slate-400 font-medium">Rare-Frame Mining (M0–M6) Baseline</p>
          </div>
        </div>

        {/* Center / Run Switcher */}
        <div className="flex items-center gap-2.5">
          <div className="flex items-center gap-2 bg-slate-800/80 border border-slate-700/80 rounded-lg px-2.5 py-1.5 text-xs">
            <span className="text-slate-400 font-medium">Lô kết quả:</span>
            <select
              value={currentRun}
              onChange={(e) => loadRun(e.target.value)}
              className="bg-transparent font-semibold text-slate-200 outline-none cursor-pointer"
            >
              {availableRuns.map((r) => (
                <option key={r} value={r} className="bg-slate-900 text-slate-200">
                  {r}
                </option>
              ))}
            </select>
          </div>

          <button
            onClick={() => loadRun(currentRun)}
            title="Tải lại kết quả"
            className="p-2 rounded-lg bg-slate-800/80 hover:bg-slate-700 text-slate-300 hover:text-white transition-colors border border-slate-700/80"
          >
            <RefreshCw className={`w-3.5 h-3.5 ${loading ? "animate-spin" : ""}`} />
          </button>

          <button
            onClick={() => setShowRunModal(true)}
            className="flex items-center gap-1.5 bg-gradient-to-r from-indigo-600 to-violet-600 hover:from-indigo-500 hover:to-violet-500 text-white font-semibold text-xs px-3.5 py-2 rounded-lg shadow-sm transition-all shadow-indigo-600/30"
          >
            <Play className="w-3.5 h-3.5 fill-current" />
            <span>Chạy thử nghiệm</span>
          </button>
        </div>

        {/* Right switch link */}
        <div className="flex items-center gap-3">
          <Link
            href="/"
            className="inline-flex items-center gap-1.5 text-xs font-semibold px-3 py-1.5 rounded-lg border border-slate-700 bg-slate-800/50 hover:bg-slate-800 text-slate-300 hover:text-white transition-colors"
          >
            <span>Về v1 (Main Baseline)</span>
            <ArrowUpRight className="w-3.5 h-3.5 text-slate-400" />
          </Link>
        </div>
      </header>

      {/* Main Container */}
      <main className="flex-1 max-w-7xl w-full mx-auto p-4 sm:p-6 lg:p-8 flex flex-col gap-6">
        {/* Error notification if any */}
        {error && (
          <div className="bg-rose-950/40 border border-rose-800/50 rounded-xl p-4 text-rose-200 text-xs flex items-center justify-between">
            <div className="flex items-center gap-2">
              <AlertTriangle className="w-4 h-4 text-rose-400" />
              <span>{error}</span>
            </div>
            <button onClick={() => setError(null)} className="text-rose-400 hover:text-rose-200">
              <X className="w-4 h-4" />
            </button>
          </div>
        )}

        {/* Summary Metric Cards */}
        {report && (
          <div className="grid grid-cols-2 md:grid-cols-3 lg:grid-cols-6 gap-3.5">
            <div className="bg-slate-900/60 border border-slate-800/80 rounded-xl p-4 flex flex-col justify-between">
              <div className="text-[11px] font-medium text-slate-400 uppercase tracking-wider">Tổng Frame T</div>
              <div className="text-2xl font-bold text-white mt-1">{report.n_frames_T}</div>
              <div className="text-[11px] text-slate-500 mt-1">Đánh giá trên nhãn giấu</div>
            </div>

            <div className="bg-slate-900/60 border border-slate-800/80 rounded-xl p-4 flex flex-col justify-between">
              <div className="text-[11px] font-medium text-slate-400 uppercase tracking-wider">Frame Hiếm (GT)</div>
              <div className="text-2xl font-bold text-amber-400 mt-1">{report.n_rare_frames}</div>
              <div className="text-[11px] text-amber-400/80 mt-1">
                Base rate {(report.base_rate * 100).toFixed(1)}%
              </div>
            </div>

            <div className="bg-slate-900/60 border border-slate-800/80 rounded-xl p-4 flex flex-col justify-between">
              <div className="text-[11px] font-medium text-slate-400 uppercase tracking-wider">Precision @ 50</div>
              <div className="text-2xl font-bold text-emerald-400 mt-1">
                {((report.pipeline["P@50"] ?? 0) * 100).toFixed(1)}%
              </div>
              <div className="text-[11px] text-emerald-400/80 mt-1 flex items-center gap-1">
                <TrendingUp className="w-3 h-3" />
                <span>
                  +
                  {(((report.pipeline["P@50"] ?? 0) - (report.random_mean["P@50"] ?? 0)) * 100).toFixed(
                    1
                  )}
                  % vs Random
                </span>
              </div>
            </div>

            <div className="bg-slate-900/60 border border-slate-800/80 rounded-xl p-4 flex flex-col justify-between">
              <div className="text-[11px] font-medium text-slate-400 uppercase tracking-wider">Recall @ 50</div>
              <div className="text-2xl font-bold text-indigo-400 mt-1">
                {((report.pipeline["R@50"] ?? 0) * 100).toFixed(1)}%
              </div>
              <div className="text-[11px] text-indigo-400/80 mt-1">
                Random: {((report.random_mean["R@50"] ?? 0) * 100).toFixed(1)}%
              </div>
            </div>

            <div className="bg-slate-900/60 border border-slate-800/80 rounded-xl p-4 flex flex-col justify-between">
              <div className="text-[11px] font-medium text-slate-400 uppercase tracking-wider">Yield VRU / Frame</div>
              <div className="text-2xl font-bold text-sky-400 mt-1">
                {report.yield_vru_per_frame?.pipeline ?? "—"}
              </div>
              <div className="text-[11px] text-slate-400 mt-1">
                Random: {report.yield_vru_per_frame?.random_mean ?? "—"}
              </div>
            </div>

            <div className="bg-slate-900/60 border border-slate-800/80 rounded-xl p-4 flex flex-col justify-between">
              <div className="text-[11px] font-medium text-slate-400 uppercase tracking-wider">Cổng Ngoại Lai</div>
              <div className="text-2xl font-bold text-teal-400 mt-1">
                <span className="text-teal-400">
                  {report.outlier_gate?.counts_T?.valid ?? frames.filter((f) => f.gate === "valid").length}
                </span>
                <span className="text-slate-500 text-sm font-normal"> / {frames.length}</span>
              </div>
              <div className="text-[11px] text-slate-400 mt-1">
                Nghi ngờ: {report.outlier_gate?.counts_T?.suspect ?? review.length}
              </div>
            </div>
          </div>
        )}

        {/* Tab Selector */}
        <div className="flex items-center gap-2 border-b border-slate-800 pb-2">
          <button
            onClick={() => setActiveTab("ranking")}
            className={`flex items-center gap-2 px-4 py-2 text-xs font-semibold rounded-lg transition-colors ${
              activeTab === "ranking"
                ? "bg-indigo-600 text-white"
                : "text-slate-400 hover:text-white hover:bg-slate-800/60"
            }`}
          >
            <FileSpreadsheet className="w-4 h-4" />
            <span>Bảng Xếp Hạng Frame ({filteredFrames.length})</span>
          </button>

          <button
            onClick={() => setActiveTab("m6")}
            className={`flex items-center gap-2 px-4 py-2 text-xs font-semibold rounded-lg transition-colors ${
              activeTab === "m6"
                ? "bg-indigo-600 text-white"
                : "text-slate-400 hover:text-white hover:bg-slate-800/60"
            }`}
          >
            <BarChart3 className="w-4 h-4" />
            <span>Đánh Giá M6 & Baseline</span>
          </button>

          <button
            onClick={() => setActiveTab("inspector")}
            className={`flex items-center gap-2 px-4 py-2 text-xs font-semibold rounded-lg transition-colors ${
              activeTab === "inspector"
                ? "bg-indigo-600 text-white"
                : "text-slate-400 hover:text-white hover:bg-slate-800/60"
            }`}
          >
            <Eye className="w-4 h-4" />
            <span>Soi Vật Thể 3D & BEV {inspectFid ? `(${inspectFid})` : ""}</span>
          </button>

          <button
            onClick={() => setActiveTab("gate")}
            className={`flex items-center gap-2 px-4 py-2 text-xs font-semibold rounded-lg transition-colors ${
              activeTab === "gate"
                ? "bg-indigo-600 text-white"
                : "text-slate-400 hover:text-white hover:bg-slate-800/60"
            }`}
          >
            <ShieldCheck className="w-4 h-4" />
            <span>Cổng Ngoại Lai & Lỗi Giả ({review.length})</span>
          </button>
        </div>

        {/* TAB 1: RANKING TABLE */}
        {activeTab === "ranking" && (
          <div className="flex flex-col gap-4">
            {/* Filter Bar */}
            <div className="bg-slate-900/80 border border-slate-800 rounded-xl p-3.5 flex flex-wrap items-center justify-between gap-3">
              <div className="flex items-center gap-2.5 flex-1 min-w-[260px]">
                <Search className="w-4 h-4 text-slate-400" />
                <input
                  type="text"
                  placeholder="Tìm theo Frame ID, Scene, hoặc lý do (mưa, xe đạp, xa >30m)..."
                  value={searchQuery}
                  onChange={(e) => setSearchQuery(e.target.value)}
                  className="bg-transparent text-xs text-slate-200 outline-none w-full placeholder:text-slate-500"
                />
                {searchQuery && (
                  <button onClick={() => setSearchQuery("")} className="text-slate-500 hover:text-slate-300">
                    <X className="w-3.5 h-3.5" />
                  </button>
                )}
              </div>

              <div className="flex flex-wrap items-center gap-2">
                <div className="flex items-center gap-1.5 text-xs text-slate-400">
                  <Filter className="w-3.5 h-3.5" />
                  <span>Slice:</span>
                  <select
                    value={selectedSlice}
                    onChange={(e) => setSelectedSlice(e.target.value)}
                    className="bg-slate-800 border border-slate-700 rounded-md px-2 py-1 text-xs text-slate-200 outline-none cursor-pointer"
                  >
                    <option value="all">Tất cả slice</option>
                    <option value="rare_class">Lớp hiếm (xe đạp / xe máy)</option>
                    <option value="rain">Thời tiết mưa</option>
                    <option value="far_few">VRU xa &gt;30m / ít điểm</option>
                  </select>
                </div>

                <label className="flex items-center gap-1.5 text-xs text-slate-300 cursor-pointer bg-slate-800 border border-slate-700 px-2.5 py-1 rounded-md">
                  <input
                    type="checkbox"
                    checked={onlySelected}
                    onChange={(e) => setOnlySelected(e.target.checked)}
                    className="rounded accent-indigo-500"
                  />
                  <span>Chỉ lấy Lô đã chọn (selected=1)</span>
                </label>
              </div>
            </div>

            {/* Table */}
            <div className="bg-slate-900/60 border border-slate-800 rounded-xl overflow-hidden shadow-xl">
              <div className="overflow-x-auto">
                <table className="w-full text-left text-xs">
                  <thead className="bg-slate-900 text-slate-400 uppercase tracking-wider text-[10px] font-semibold border-b border-slate-800">
                    <tr>
                      <th className="py-3 px-4">Hạng</th>
                      <th className="py-3 px-4">Frame ID</th>
                      <th className="py-3 px-4">Scene &amp; Giây</th>
                      <th className="py-3 px-4">Độ Hiếm (Score)</th>
                      <th className="py-3 px-4">Cổng</th>
                      <th className="py-3 px-4">Slice Chính</th>
                      <th className="py-3 px-4">Lý Do Chi Tiết</th>
                      <th className="py-3 px-4 text-right">Hành Động</th>
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-slate-800/60">
                    {filteredFrames.map((f) => {
                      const scoreVal = parseFloat(f.s_frame) || 0;
                      return (
                        <tr
                          key={f.fid}
                          className="hover:bg-slate-800/40 transition-colors group cursor-pointer"
                          onClick={() => {
                            setInspectFid(f.fid);
                            setActiveTab("inspector");
                          }}
                        >
                          <td className="py-3 px-4 font-mono font-bold text-slate-300">
                            #{f.rank}
                            {f.selected === "1" && (
                              <span className="ml-1.5 px-1.5 py-0.5 text-[9px] rounded bg-emerald-500/20 text-emerald-400 border border-emerald-500/30 font-sans">
                                Gán
                              </span>
                            )}
                          </td>
                          <td className="py-3 px-4 font-mono font-medium text-indigo-300">
                            {f.fid}
                          </td>
                          <td className="py-3 px-4 text-slate-400">
                            {f.scene} · {f.t}s
                          </td>
                          <td className="py-3 px-4">
                            <div className="flex items-center gap-2">
                              <span className="font-mono font-bold text-slate-200">
                                {scoreVal.toFixed(3)}
                              </span>
                              <div className="w-16 h-1.5 bg-slate-800 rounded-full overflow-hidden">
                                <div
                                  className="h-full bg-gradient-to-r from-indigo-500 to-violet-500 rounded-full"
                                  style={{ width: `${Math.min(100, scoreVal * 100)}%` }}
                                />
                              </div>
                            </div>
                          </td>
                          <td className="py-3 px-4">
                            {f.gate === "valid" ? (
                              <span className="inline-flex items-center gap-1 text-[10px] font-medium px-2 py-0.5 rounded-full bg-emerald-500/10 text-emerald-400 border border-emerald-500/20">
                                <CheckCircle2 className="w-2.5 h-2.5" /> Hợp lệ
                              </span>
                            ) : (
                              <span className="inline-flex items-center gap-1 text-[10px] font-medium px-2 py-0.5 rounded-full bg-amber-500/10 text-amber-400 border border-amber-500/20">
                                <AlertTriangle className="w-2.5 h-2.5" /> Nghi ngờ
                              </span>
                            )}
                          </td>
                          <td className="py-3 px-4">
                            <span className="text-[11px] font-medium px-2 py-0.5 rounded bg-slate-800 text-slate-300 border border-slate-700">
                              {f.slice_primary}
                            </span>
                          </td>
                          <td className="py-3 px-4 max-w-md">
                            <p className="text-slate-300 text-[11px] line-clamp-2 leading-relaxed">
                              {f.reasons}
                            </p>
                          </td>
                          <td className="py-3 px-4 text-right">
                            <button
                              onClick={(e) => {
                                e.stopPropagation();
                                setInspectFid(f.fid);
                                setActiveTab("inspector");
                              }}
                              className="px-2.5 py-1 text-[11px] rounded bg-indigo-600/30 hover:bg-indigo-600 text-indigo-200 hover:text-white border border-indigo-500/30 transition-all font-medium inline-flex items-center gap-1"
                            >
                              <Eye className="w-3 h-3" />
                              <span>Soi 3D</span>
                            </button>
                          </td>
                        </tr>
                      );
                    })}
                  </tbody>
                </table>
              </div>
            </div>
          </div>
        )}

        {/* TAB 2: M6 BENCHMARK EVALUATION */}
        {activeTab === "m6" && report && (
          <div className="flex flex-col gap-6">
            {/* Header info */}
            <div className="bg-slate-900/60 border border-slate-800 rounded-xl p-5">
              <h2 className="font-bold text-base text-white flex items-center gap-2">
                <BarChart3 className="w-5 h-5 text-indigo-400" />
                <span>Báo Cáo Đánh Giá M6 — So Sánh Pipeline v2 vs Các Baseline</span>
              </h2>
              <p className="text-xs text-slate-400 mt-1">
                Đánh giá trên {report.n_frames_T} keyframe của tập kiểm thử T (giữ kín nhãn Ground Truth lúc xếp hạng).
              </p>
            </div>

            {/* Comparison Table */}
            <div className="bg-slate-900/60 border border-slate-800 rounded-xl overflow-hidden">
              <div className="p-4 border-b border-slate-800">
                <h3 className="font-semibold text-sm text-slate-200">
                  Hiệu năng Precision &amp; Recall theo các mức Ngân Sách B (50, 100, 150)
                </h3>
              </div>
              <div className="overflow-x-auto">
                <table className="w-full text-left text-xs">
                  <thead className="bg-slate-900 text-slate-400 uppercase tracking-wider text-[10px] font-semibold border-b border-slate-800">
                    <tr>
                      <th className="py-3 px-4">Chỉ số</th>
                      <th className="py-3 px-4 text-indigo-300">Pipeline v2 (Đóng băng)</th>
                      <th className="py-3 px-4">Random Baseline (mean ± std)</th>
                      <th className="py-3 px-4">Rule-only Ablation</th>
                      <th className="py-3 px-4">Confidence-only</th>
                      <th className="py-3 px-4">NoDedup (Không lọc trùng)</th>
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-slate-800/60 font-mono">
                    <tr>
                      <td className="py-3 px-4 font-sans font-semibold text-slate-300">P @ 50</td>
                      <td className="py-3 px-4 font-bold text-emerald-400">
                        {((report.pipeline["P@50"] ?? 0) * 100).toFixed(1)}%
                      </td>
                      <td className="py-3 px-4 text-slate-400">
                        {((report.random_mean["P@50"] ?? 0) * 100).toFixed(1)}% ±{" "}
                        {((report.random_std["P@50"] ?? 0) * 100).toFixed(1)}%
                      </td>
                      <td className="py-3 px-4 text-slate-300">
                        {((report.rule_only_ablation["P@50"] ?? 0) * 100).toFixed(1)}%
                      </td>
                      <td className="py-3 px-4 text-slate-300">
                        {((report.confidence_only["P@50"] ?? 0) * 100).toFixed(1)}%
                      </td>
                      <td className="py-3 px-4 text-slate-300">
                        {((report.pipeline_nodedup["P@50"] ?? 0) * 100).toFixed(1)}%
                      </td>
                    </tr>
                    <tr>
                      <td className="py-3 px-4 font-sans font-semibold text-slate-300">R @ 50</td>
                      <td className="py-3 px-4 font-bold text-emerald-400">
                        {((report.pipeline["R@50"] ?? 0) * 100).toFixed(1)}%
                      </td>
                      <td className="py-3 px-4 text-slate-400">
                        {((report.random_mean["R@50"] ?? 0) * 100).toFixed(1)}% ±{" "}
                        {((report.random_std["R@50"] ?? 0) * 100).toFixed(1)}%
                      </td>
                      <td className="py-3 px-4 text-slate-300">
                        {((report.rule_only_ablation["R@50"] ?? 0) * 100).toFixed(1)}%
                      </td>
                      <td className="py-3 px-4 text-slate-300">
                        {((report.confidence_only["R@50"] ?? 0) * 100).toFixed(1)}%
                      </td>
                      <td className="py-3 px-4 text-slate-300">
                        {((report.pipeline_nodedup["R@50"] ?? 0) * 100).toFixed(1)}%
                      </td>
                    </tr>
                    <tr>
                      <td className="py-3 px-4 font-sans font-semibold text-slate-300">P @ 100</td>
                      <td className="py-3 px-4 font-bold text-indigo-400">
                        {((report.pipeline["P@100"] ?? 0) * 100).toFixed(1)}%
                      </td>
                      <td className="py-3 px-4 text-slate-400">
                        {((report.random_mean["P@100"] ?? 0) * 100).toFixed(1)}% ±{" "}
                        {((report.random_std["P@100"] ?? 0) * 100).toFixed(1)}%
                      </td>
                      <td className="py-3 px-4 text-slate-300">
                        {((report.rule_only_ablation["P@100"] ?? 0) * 100).toFixed(1)}%
                      </td>
                      <td className="py-3 px-4 text-slate-300">
                        {((report.confidence_only["P@100"] ?? 0) * 100).toFixed(1)}%
                      </td>
                      <td className="py-3 px-4 text-slate-300">
                        {((report.pipeline_nodedup["P@100"] ?? 0) * 100).toFixed(1)}%
                      </td>
                    </tr>
                    <tr>
                      <td className="py-3 px-4 font-sans font-semibold text-slate-300">R @ 100</td>
                      <td className="py-3 px-4 font-bold text-indigo-400">
                        {((report.pipeline["R@100"] ?? 0) * 100).toFixed(1)}%
                      </td>
                      <td className="py-3 px-4 text-slate-400">
                        {((report.random_mean["R@100"] ?? 0) * 100).toFixed(1)}% ±{" "}
                        {((report.random_std["R@100"] ?? 0) * 100).toFixed(1)}%
                      </td>
                      <td className="py-3 px-4 text-slate-300">
                        {((report.rule_only_ablation["R@100"] ?? 0) * 100).toFixed(1)}%
                      </td>
                      <td className="py-3 px-4 text-slate-300">
                        {((report.confidence_only["R@100"] ?? 0) * 100).toFixed(1)}%
                      </td>
                      <td className="py-3 px-4 text-slate-300">
                        {((report.pipeline_nodedup["R@100"] ?? 0) * 100).toFixed(1)}%
                      </td>
                    </tr>
                    <tr className="bg-slate-900/40">
                      <td className="py-3 px-4 font-sans font-semibold text-slate-200">
                        Average Precision (AP)
                      </td>
                      <td className="py-3 px-4 font-bold text-violet-300">
                        {(report.pipeline["AP"] ?? 0).toFixed(3)}
                      </td>
                      <td className="py-3 px-4 text-slate-500">—</td>
                      <td className="py-3 px-4 text-slate-300">
                        {(report.rule_only_ablation["AP"] ?? 0).toFixed(3)}
                      </td>
                      <td className="py-3 px-4 text-slate-300">
                        {(report.confidence_only["AP"] ?? 0).toFixed(3)}
                      </td>
                      <td className="py-3 px-4 text-slate-300">
                        {(report.pipeline_nodedup["AP"] ?? 0).toFixed(3)}
                      </td>
                    </tr>
                  </tbody>
                </table>
              </div>
            </div>

            {/* Slices Cards */}
            <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
              {Object.entries(report.slices).map(([sname, sdata]) => (
                <div key={sname} className="bg-slate-900/60 border border-slate-800 rounded-xl p-4">
                  <div className="flex items-center justify-between">
                    <span className="font-semibold text-xs text-white capitalize">{sname}</span>
                    <span className="text-[10px] text-slate-400 bg-slate-800 px-2 py-0.5 rounded font-mono">
                      n={sdata.n_pos}
                    </span>
                  </div>
                  <div className="mt-3 flex items-baseline justify-between">
                    <span className="text-[11px] text-slate-400">Recall @ 100:</span>
                    <span className="font-mono font-bold text-sm text-indigo-400">
                      {typeof sdata["R@100"] === "number" ? `${(sdata["R@100"] * 100).toFixed(1)}%` : "—"}
                    </span>
                  </div>
                  {typeof sdata["random_R@100"] === "number" && (
                    <div className="mt-1 flex items-baseline justify-between text-[11px] text-slate-500">
                      <span>Random:</span>
                      <span className="font-mono">{(sdata["random_R@100"] * 100).toFixed(1)}%</span>
                    </div>
                  )}
                </div>
              ))}
            </div>
          </div>
        )}

        {/* TAB 3: OBJECT & BEV INSPECTOR */}
        {activeTab === "inspector" && (
          <div className="grid grid-cols-1 lg:grid-cols-12 gap-6">
            {/* Left: 2D BEV Canvas Viewer */}
            <div className="lg:col-span-7 bg-slate-900/60 border border-slate-800 rounded-xl p-5 flex flex-col gap-4">
              <div className="flex items-center justify-between border-b border-slate-800 pb-3">
                <div className="flex items-center gap-2">
                  <Eye className="w-4 h-4 text-indigo-400" />
                  <h3 className="font-bold text-sm text-white">
                    Sơ Đồ 2D BEV (Bird&apos;s Eye View) — {inspectFid || "Chưa chọn"}
                  </h3>
                </div>
                <div className="flex items-center gap-2">
                  <select
                    value={inspectFid || ""}
                    onChange={(e) => setInspectFid(e.target.value)}
                    className="bg-slate-800 border border-slate-700 rounded px-2.5 py-1 text-xs text-slate-200 outline-none"
                  >
                    {frames.map((f) => (
                      <option key={f.fid} value={f.fid}>
                        #{f.rank} — {f.fid} ({f.slice_primary})
                      </option>
                    ))}
                  </select>
                </div>
              </div>

              {/* BEV Canvas */}
              <div className="w-full flex justify-center items-center py-2">
                <BevCanvas objects={currentFrameObjects} />
              </div>

              {/* Legend */}
              <div className="flex flex-wrap items-center justify-center gap-4 text-[11px] text-slate-400 pt-2 border-t border-slate-800">
                <div className="flex items-center gap-1.5">
                  <span className="w-3 h-3 rounded bg-blue-500 inline-block" />
                  <span>Xe tự hành (Ego)</span>
                </div>
                <div className="flex items-center gap-1.5">
                  <span className="w-3 h-3 rounded bg-emerald-500 inline-block" />
                  <span>Xe đạp (Bicycle)</span>
                </div>
                <div className="flex items-center gap-1.5">
                  <span className="w-3 h-3 rounded bg-sky-400 inline-block" />
                  <span>Xe máy (Motorcycle)</span>
                </div>
                <div className="flex items-center gap-1.5">
                  <span className="w-3 h-3 rounded bg-amber-400 inline-block" />
                  <span>Người đi bộ (Pedestrian)</span>
                </div>
                <div className="flex items-center gap-1.5">
                  <span className="w-3 h-3 rounded border-2 border-dashed border-rose-500 inline-block" />
                  <span>Model bỏ sót (Missed)</span>
                </div>
              </div>
            </div>

            {/* Right: Objects list & reasons */}
            <div className="lg:col-span-5 flex flex-col gap-4">
              {inspectedFrameInfo && (
                <div className="bg-slate-900/60 border border-slate-800 rounded-xl p-4">
                  <div className="text-[10px] text-slate-400 uppercase font-semibold">Lý do chọn frame này</div>
                  <p className="text-xs text-slate-200 mt-1.5 leading-relaxed font-medium">
                    {inspectedFrameInfo.reasons}
                  </p>
                  <div className="flex flex-wrap items-center gap-2 mt-3 text-[11px]">
                    <span className="px-2 py-0.5 rounded bg-slate-800 text-slate-300 font-mono">
                      Hạng: #{inspectedFrameInfo.rank}
                    </span>
                    <span className="px-2 py-0.5 rounded bg-indigo-500/20 text-indigo-300 font-mono">
                      Score: {parseFloat(inspectedFrameInfo.s_frame).toFixed(3)}
                    </span>
                    <span className="px-2 py-0.5 rounded bg-emerald-500/20 text-emerald-300 font-mono">
                      Cổng: {inspectedFrameInfo.gate}
                    </span>
                  </div>
                </div>
              )}

              {/* Objects in frame */}
              <div className="bg-slate-900/60 border border-slate-800 rounded-xl p-4 flex-1 flex flex-col">
                <div className="flex items-center justify-between pb-2 border-b border-slate-800">
                  <span className="font-semibold text-xs text-white">
                    Vật Thể Khoanh Box ({currentFrameObjects.length})
                  </span>
                  <span className="text-[11px] text-slate-400">Trích từ objects_T.csv</span>
                </div>

                <div className="mt-3 flex flex-col gap-2.5 overflow-y-auto max-h-[460px]">
                  {currentFrameObjects.length === 0 ? (
                    <div className="text-xs text-slate-500 text-center py-8">
                      Không có box vật thể nào trong frame này.
                    </div>
                  ) : (
                    currentFrameObjects.map((obj, idx) => (
                      <div
                        key={idx}
                        className={`p-3 rounded-lg border text-xs flex flex-col gap-1.5 transition-colors ${
                          obj.missed_by_model === "1"
                            ? "bg-rose-950/20 border-rose-800/60 text-rose-100"
                            : "bg-slate-800/50 border-slate-700/60 text-slate-200"
                        }`}
                      >
                        <div className="flex items-center justify-between">
                          <span className="font-bold flex items-center gap-1.5">
                            {obj.class_name === "bicycle" ? (
                              <Bike className="w-3.5 h-3.5 text-emerald-400" />
                            ) : obj.class_name === "motorcycle" ? (
                              <Bike className="w-3.5 h-3.5 text-sky-400" />
                            ) : obj.class_name === "pedestrian" ? (
                              <User className="w-3.5 h-3.5 text-amber-400" />
                            ) : (
                              <Car className="w-3.5 h-3.5 text-slate-400" />
                            )}
                            <span className="capitalize">{obj.class_name}</span>
                          </span>

                          <div className="flex items-center gap-1.5">
                            {obj.missed_by_model === "1" && (
                              <span className="px-1.5 py-0.5 rounded text-[9px] font-bold bg-rose-600 text-white">
                                MODEL BỎ SÓT
                              </span>
                            )}
                            <span className="font-mono text-[11px] text-indigo-300">
                              dist: {parseFloat(obj.dist_m).toFixed(1)}m
                            </span>
                          </div>
                        </div>

                        <div className="grid grid-cols-2 gap-1 text-[11px] text-slate-400 font-mono">
                          <div>
                            Tâm: ({parseFloat(obj.cx).toFixed(1)}, {parseFloat(obj.cy).toFixed(1)},{" "}
                            {parseFloat(obj.cz).toFixed(1)})
                          </div>
                          <div>
                            Kích thước: {parseFloat(obj.L).toFixed(1)} × {parseFloat(obj.W).toFixed(1)} ×{" "}
                            {parseFloat(obj.H).toFixed(1)} m
                          </div>
                          <div>Điểm: {obj.n_points} pts</div>
                          <div>Score vật: {parseFloat(obj.s_obj).toFixed(3)}</div>
                        </div>

                        {obj.reasons && (
                          <div className="text-[10px] text-slate-400 italic pt-1 border-t border-slate-700/40">
                            {obj.reasons}
                          </div>
                        )}
                      </div>
                    ))
                  )}
                </div>
              </div>
            </div>
          </div>
        )}

        {/* TAB 4: OUTLIER GATE VERIFICATION */}
        {activeTab === "gate" && (
          <div className="flex flex-col gap-6">
            <div className="bg-slate-900/60 border border-slate-800 rounded-xl p-5">
              <h2 className="font-bold text-base text-white flex items-center gap-2">
                <ShieldCheck className="w-5 h-5 text-teal-400" />
                <span>Cổng Ngoại Lai (Outlier Gate) — 4 Phép Thử &amp; Báo Cáo Kiểm Chứng</span>
              </h2>
              <p className="text-xs text-slate-400 mt-1 leading-relaxed">
                Cổng chạy ngay sau M1 để sàng lọc frame lỗi cảm biến/ghi file (Ngoại lai) hoặc nghi ngờ điểm ma trước
                khi tính điểm hiếm. Điểm OOD chỉ đóng vai trò cờ cảnh báo (w_ood = 0), không cộng điểm chọn.
              </p>
            </div>

            {/* Test rules summary */}
            <div className="grid grid-cols-1 md:grid-cols-4 gap-4">
              <div className="bg-slate-900/60 border border-slate-800 rounded-xl p-4 flex flex-col gap-1.5">
                <div className="text-teal-400 font-bold text-xs">1. Dữ Liệu Hợp Lệ</div>
                <p className="text-[11px] text-slate-400 leading-relaxed">
                  Đủ điểm (&ge; 25% trung vị), không NaN/inf, cường độ &ge; 0, &le; 5% điểm dưới mặt đất, có ego pose.
                </p>
              </div>

              <div className="bg-slate-900/60 border border-slate-800 rounded-xl p-4 flex flex-col gap-1.5">
                <div className="text-teal-400 font-bold text-xs">2. Nhất Quán Thời Gian</div>
                <p className="text-[11px] text-slate-400 leading-relaxed">
                  Đối chiếu keyframe liền trước/sau trong bán kính 1.5m + 3m/s &times; &Delta;t để phát hiện điểm
                  &quot;ma&quot;.
                </p>
              </div>

              <div className="bg-slate-900/60 border border-slate-800 rounded-xl p-4 flex flex-col gap-1.5">
                <div className="text-teal-400 font-bold text-xs">3. Hợp Lý Hình Học</div>
                <p className="text-[11px] text-slate-400 leading-relaxed">
                  Loại vật lơ lửng &gt; 1m so với mặt đất cục bộ; box VRU phải có kích thước khả dĩ.
                </p>
              </div>

              <div className="bg-slate-900/60 border border-slate-800 rounded-xl p-4 flex flex-col gap-1.5">
                <div className="text-teal-400 font-bold text-xs">4. Khoảng Cách k-NN</div>
                <p className="text-[11px] text-slate-400 leading-relaxed">
                  Khoảng cách k-NN (k=5) tới tập V ở scene khác không vượt phân vị 99.9% để loại lệch domain.
                </p>
              </div>
            </div>

            {/* Suspect table */}
            <div className="bg-slate-900/60 border border-slate-800 rounded-xl overflow-hidden">
              <div className="p-4 border-b border-slate-800 flex items-center justify-between">
                <h3 className="font-semibold text-sm text-slate-200">
                  Danh Sách Frame Nghi Ngờ Trong Lô Này ({review.length})
                </h3>
                <span className="text-xs text-slate-400">review_T.csv (Không giao cho đội gán nhãn)</span>
              </div>
              {review.length === 0 ? (
                <div className="p-8 text-center text-xs text-slate-500">
                  Không có frame nào bị xếp Nghi ngờ hoặc Ngoại lai. Dữ liệu sạch 100%.
                </div>
              ) : (
                <div className="overflow-x-auto">
                  <table className="w-full text-left text-xs">
                    <thead className="bg-slate-900 text-slate-400 uppercase tracking-wider text-[10px] font-semibold border-b border-slate-800">
                      <tr>
                        <th className="py-3 px-4">Frame ID</th>
                        <th className="py-3 px-4">Scene</th>
                        <th className="py-3 px-4">Cổng</th>
                        <th className="py-3 px-4">Lý Do Trượt (Gate Fail)</th>
                      </tr>
                    </thead>
                    <tbody className="divide-y divide-slate-800/60 font-mono">
                      {review.map((r) => (
                        <tr key={r.fid} className="hover:bg-slate-800/40">
                          <td className="py-3 px-4 text-indigo-300 font-bold">{r.fid}</td>
                          <td className="py-3 px-4 text-slate-400">{r.scene}</td>
                          <td className="py-3 px-4">
                            <span className="px-2 py-0.5 rounded text-[10px] font-sans font-bold bg-amber-500/20 text-amber-300 border border-amber-500/30">
                              {r.gate}
                            </span>
                          </td>
                          <td className="py-3 px-4 text-slate-300 font-sans text-xs">
                            {r.gate_fail || "Trượt kiểm tra hình học hoặc nhất quán thời gian"}
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              )}
            </div>
          </div>
        )}
      </main>

      {/* Modal: Chạy pipeline mới */}
      {showRunModal && (
        <div className="fixed inset-0 z-50 bg-black/75 backdrop-blur-xs flex items-center justify-center p-4">
          <div className="bg-slate-900 border border-slate-800 rounded-2xl max-w-lg w-full p-6 shadow-2xl flex flex-col gap-4">
            <div className="flex items-center justify-between border-b border-slate-800 pb-3">
              <div className="flex items-center gap-2">
                <SlidersHorizontal className="w-5 h-5 text-indigo-400" />
                <h3 className="font-bold text-base text-white">Chạy Thử Nghiệm Pipeline v2</h3>
              </div>
              <button onClick={() => setShowRunModal(false)} className="text-slate-400 hover:text-white">
                <X className="w-5 h-5" />
              </button>
            </div>

            <div className="flex flex-col gap-3 text-xs">
              <div>
                <label className="text-slate-300 font-medium block mb-1">Nguồn Dữ Liệu:</label>
                <select
                  value={runSource}
                  onChange={(e) => setRunSource(e.target.value)}
                  className="w-full bg-slate-800 border border-slate-700 rounded-lg px-3 py-2 text-slate-200 outline-none"
                >
                  <option value="synthetic">Dữ liệu tổng hợp (Synthetic — Chạy tức thì, 400 frames)</option>
                  <option value="nuscenes">nuScenes (Cần có thư mục /data/nuScenes)</option>
                </select>
              </div>

              <div>
                <label className="text-slate-300 font-medium block mb-1">
                  Ngân Sách Chọn $B$ (Số Frame Gán Nhãn):
                </label>
                <input
                  type="number"
                  min={10}
                  max={200}
                  step={10}
                  value={runBudget}
                  onChange={(e) => setRunBudget(Number(e.target.value))}
                  className="w-full bg-slate-800 border border-slate-700 rounded-lg px-3 py-2 text-slate-200 outline-none font-mono"
                />
                <span className="text-[11px] text-slate-500 mt-1 block">
                  Pipeline sẽ chọn đúng {runBudget} frame hiếm nhất theo thuật toán M4/M5.
                </span>
              </div>

              {runTerminalLog && (
                <div className="mt-2 bg-slate-950 border border-slate-800 rounded-lg p-3 max-h-48 overflow-y-auto font-mono text-[11px] text-slate-300 whitespace-pre-wrap">
                  {runTerminalLog}
                </div>
              )}
            </div>

            <div className="flex items-center justify-end gap-3 pt-3 border-t border-slate-800">
              <button
                type="button"
                onClick={() => setShowRunModal(false)}
                className="px-4 py-2 rounded-lg text-xs font-semibold text-slate-400 hover:text-white"
              >
                Đóng
              </button>

              <button
                type="button"
                disabled={runningPipeline}
                onClick={handleExecuteRun}
                className="flex items-center gap-2 bg-indigo-600 hover:bg-indigo-500 disabled:opacity-50 text-white font-semibold text-xs px-5 py-2 rounded-lg shadow-sm"
              >
                {runningPipeline ? (
                  <>
                    <RefreshCw className="w-3.5 h-3.5 animate-spin" />
                    <span>Đang chạy...</span>
                  </>
                ) : (
                  <>
                    <Play className="w-3.5 h-3.5 fill-current" />
                    <span>Bắt đầu chạy</span>
                  </>
                )}
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}

// 2D BEV Canvas Component
function BevCanvas({ objects }: { objects: ObjectBox[] }) {
  const canvasRef = useRef<HTMLCanvasElement | null>(null);

  useEffect(() => {
    const canvas = canvasRef.current;
    if (!canvas) return;
    const ctx = canvas.getContext("2d");
    if (!ctx) return;

    const width = canvas.width;
    const height = canvas.height;
    ctx.clearRect(0, 0, width, height);

    // Background
    ctx.fillStyle = "#090d16";
    ctx.fillRect(0, 0, width, height);

    // Center coordinates: Ego car is at bottom-middle or center
    // Let's place ego at (centerX, height - 60) looking upwards (positive X is up, positive Y is left)
    const centerX = width / 2;
    const centerY = height - 50;
    const scale = 5.2; // 1 meter = 5.2 pixels (fits up to 55 meters)

    // Draw range rings
    ctx.strokeStyle = "#1e293b";
    ctx.lineWidth = 1;
    ctx.font = "9px monospace";
    ctx.fillStyle = "#475569";

    const rings = [10, 20, 30, 40, 50];
    rings.forEach((r) => {
      ctx.beginPath();
      ctx.arc(centerX, centerY, r * scale, Math.PI, 2 * Math.PI);
      ctx.stroke();
      ctx.fillText(`${r}m`, centerX + 4, centerY - r * scale + 10);
    });

    // Draw axes
    ctx.strokeStyle = "#334155";
    ctx.beginPath();
    ctx.moveTo(centerX, 20);
    ctx.lineTo(centerX, centerY + 20);
    ctx.stroke();

    // Draw Ego Vehicle (Centered at 0, 0)
    ctx.fillStyle = "#3b82f6";
    const egoL = 4.5 * scale;
    const egoW = 2.0 * scale;
    ctx.fillRect(centerX - egoW / 2, centerY - egoL / 2, egoW, egoL);
    ctx.fillStyle = "#ffffff";
    ctx.beginPath();
    ctx.moveTo(centerX, centerY - egoL / 2);
    ctx.lineTo(centerX - 4, centerY - egoL / 2 + 8);
    ctx.lineTo(centerX + 4, centerY - egoL / 2 + 8);
    ctx.fill();

    // Draw Objects
    objects.forEach((obj) => {
      const cx = parseFloat(obj.cx) || 0;
      const cy = parseFloat(obj.cy) || 0;
      const l = (parseFloat(obj.L) || 2) * scale;
      const w = (parseFloat(obj.W) || 1) * scale;
      const yaw = parseFloat(obj.yaw) || 0;

      // In autonomous vehicle sensor frame:
      // X is forward (up on canvas), Y is left (left on canvas)
      const posX = centerX - cy * scale;
      const posY = centerY - cx * scale;

      ctx.save();
      ctx.translate(posX, posY);
      ctx.rotate(-yaw);

      // Color by class
      if (obj.class_name === "bicycle") {
        ctx.fillStyle = "rgba(16, 185, 129, 0.4)";
        ctx.strokeStyle = "#10b981";
      } else if (obj.class_name === "motorcycle") {
        ctx.fillStyle = "rgba(56, 189, 248, 0.4)";
        ctx.strokeStyle = "#38bdf8";
      } else if (obj.class_name === "pedestrian") {
        ctx.fillStyle = "rgba(251, 191, 36, 0.4)";
        ctx.strokeStyle = "#fbbf24";
      } else {
        ctx.fillStyle = "rgba(148, 163, 184, 0.3)";
        ctx.strokeStyle = "#94a3b8";
      }

      if (obj.missed_by_model === "1") {
        ctx.strokeStyle = "#f43f5e";
        ctx.setLineDash([3, 2]);
      } else {
        ctx.setLineDash([]);
      }

      ctx.lineWidth = 1.5;
      ctx.fillRect(-w / 2, -l / 2, w, l);
      ctx.strokeRect(-w / 2, -l / 2, w, l);

      // Front orientation notch
      ctx.beginPath();
      ctx.moveTo(0, -l / 2);
      ctx.lineTo(0, -l / 2 - 4);
      ctx.stroke();

      ctx.restore();

      // Label
      ctx.fillStyle = "#e2e8f0";
      ctx.font = "9px sans-serif";
      ctx.fillText(`${obj.class_name}`, posX + 5, posY - 4);
    });
  }, [objects]);

  return (
    <canvas
      ref={canvasRef}
      width={460}
      height={320}
      className="rounded-xl border border-slate-800 shadow-inner"
    />
  );
}
