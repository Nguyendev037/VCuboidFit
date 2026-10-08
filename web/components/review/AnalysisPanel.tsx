"use client";

import React from "react";
import type { Analysis, CountPct, Metrics, MetricsBlock } from "@/lib/api/types";
import { Card, CardHeader, CardTitle, CardContent } from "@/components/ui/card";

export interface AnalysisPanelProps {
  analysis: Analysis;
  selectedFilter?: string;
  onFilterChange?: (filterKey: string) => void;
  pipeline?: "camera" | "lidar";
  className?: string;
}

export function AnalysisPanel({
  analysis,
  selectedFilter,
  onFilterChange,
  pipeline = "camera",
  className = "",
}: AnalysisPanelProps) {
  const { pool, selected, histogram } = analysis;
  const rawMetrics = selected.metrics as Metrics | MetricsBlock | null | undefined;
  const selectedMetrics = rawMetrics && "hybrid" in rawMetrics ? rawMetrics.hybrid : rawMetrics;
  const ci95 = rawMetrics && "hybrid" in rawMetrics
    ? rawMetrics.ci95 ?? rawMetrics.hybrid.ci95
    : selectedMetrics?.ci95;

  const valOf = (v: unknown): number => {
    if (typeof v === "number") return v;
    if (typeof v === "object" && v !== null && "count" in v) return Number((v as { count: number }).count);
    return 0;
  };

  type Countish = number | CountPct;
  type RareLike = { total: Countish; A: Countish; B: Countish; Bp?: Countish; C: Countish };
  const poolExtra = pool as typeof pool & {
    easy?: Countish;
    easyForModel?: Countish;
    rareGt?: RareLike | null;
  };
  const isLidar = pipeline === "lidar";
  const rareObj = (pool.rare ?? poolExtra.rareGt) as RareLike | null | undefined;

  // Danh sách các thẻ phân tích bể dữ liệu (spec §3.1)
  const poolCards = [
    {
      id: "duplicates",
      title: "Trùng lặp",
      value: valOf(pool.duplicates?.frames),
      sub: `${pool.duplicates?.groups ?? 0} nhóm (cos > 0.95)`,
      color: "border-vcf-border hover:border-vcf-accent",
      activeBg: "bg-vcf-accent-soft border-vcf-accent text-vcf-accent-ink",
    },
    {
      id: "too_safe",
      title: "Quá an toàn",
      value: valOf(pool.tooSafe),
      sub: isLidar ? "rRar thấp và ít tín hiệu hình học" : "rNov ≤ 0.3, rQry ≤ 0.3",
      color: "border-vcf-border hover:border-vcf-accent",
      activeBg: "bg-vcf-accent-soft border-vcf-accent text-vcf-accent-ink",
    },
    {
      id: "easy_for_model",
      title: "Dễ với model",
      value: valOf(poolExtra.easyForModel ?? poolExtra.easy),
      sub: "rUnc ≤ 0.2 & det ≥ 0.5",
      color: "border-vcf-border hover:border-vcf-accent",
      activeBg: "bg-vcf-accent-soft border-vcf-accent text-vcf-accent-ink",
    },
    {
      id: "unlabelable",
      title: "Không gán nhãn",
      value: valOf(pool.unlabelable?.total),
      sub: `Tối: ${pool.unlabelable?.dark ?? 0} · Mờ: ${pool.unlabelable?.blurry ?? 0}`,
      color: "border-vcf-border hover:border-vcf-accent",
      activeBg: "bg-vcf-accent-soft border-vcf-accent text-vcf-accent-ink",
    },
    {
      id: "excluded_camera",
      title: "Loại bởi camera",
      value: valOf(pool.excludedByCamera),
      sub: "Lỗi cảm biến / hỏng góc",
      color: "border-vcf-border hover:border-vcf-accent",
      activeBg: "bg-vcf-accent-soft border-vcf-accent text-vcf-accent-ink",
    },
    {
      id: "high_value",
      title: "Giá trị cao",
      value: valOf(pool.highValue),
      sub: "Điểm S ≥ p90",
      color: "border-vcf-border hover:border-vcf-accent",
      activeBg: "bg-vcf-accent-soft border-vcf-accent text-vcf-accent-ink",
    },
    {
      id: "rare_gt",
      title: "Hiếm (GT)",
      value: rareObj ? valOf(rareObj.total) : "—",
      sub: rareObj
        ? `A: ${valOf(rareObj.A)} · B: ${valOf(rareObj.B)} · B′: ${valOf(rareObj.Bp)} · C: ${valOf(rareObj.C)}`
        : "Không có nhãn",
      color: "border-vcf-border hover:border-vcf-accent",
      activeBg: "bg-vcf-accent-soft border-vcf-accent text-vcf-accent-ink",
    },
  ];

  // Vẽ biểu đồ Histogram phân bố điểm
  const renderHistogram = () => {
    if (!histogram || !histogram.counts || histogram.counts.length === 0) {
      return null;
    }

    const maxCount = Math.max(...histogram.counts, 1);
    const barWidthPercent = 100 / histogram.counts.length;

    // Tìm index của budget threshold
    const thresholdIdx = histogram.bins.findIndex(
      (b) => b >= histogram.budgetThreshold
    );

    return (
      <div className="mt-3">
        <div className="flex items-center justify-between text-xs text-muted-foreground mb-1.5">
          <span>Phân bố điểm S toàn dataset</span>
          <span className="font-mono text-emerald-600 font-medium">
            Ngưỡng 5%: S ≥ {histogram.budgetThreshold.toFixed(2)}
          </span>
        </div>

        <div className="relative h-20 w-full bg-slate-50 border border-slate-200 rounded-lg p-1.5 flex items-end">
          {histogram.counts.map((count, i) => {
            const heightPercent = (count / maxCount) * 100;
            const isSelectedCutoff = i >= thresholdIdx && thresholdIdx >= 0;

            return (
              <div
                key={i}
                style={{ width: `${barWidthPercent}%` }}
                className="h-full flex items-end justify-center px-[0.5px] group relative"
              >
                <div
                  style={{ height: `${Math.max(4, heightPercent)}%` }}
                  className={`w-full rounded-t-xs transition-colors ${
                    isSelectedCutoff
                      ? "bg-emerald-500 hover:bg-emerald-600"
                      : "bg-slate-300 hover:bg-slate-400"
                  }`}
                />
                {/* Tooltip khi rê chuột */}
                <div className="hidden group-hover:block absolute bottom-full mb-1 bg-slate-900 text-white text-[10px] px-1.5 py-0.5 rounded whitespace-nowrap z-20 pointer-events-none">
                  {histogram.bins[i]?.toFixed(2)}: {count} frame
                </div>
              </div>
            );
          })}

          {/* Đường chỉ dẫn ngưỡng 5% */}
          {thresholdIdx >= 0 && (
            <div
              style={{ left: `${(thresholdIdx / histogram.counts.length) * 100}%` }}
              className="absolute top-0 bottom-0 border-l-2 border-dashed border-emerald-600 z-10 pointer-events-none"
            >
              <span className="absolute top-1 left-1 bg-emerald-600 text-white text-[9px] font-mono px-1 rounded">
                Top 5%
              </span>
            </div>
          )}
        </div>
      </div>
    );
  };

  return (
    <div
      className={`flex flex-col gap-4 w-full text-slate-800 ${className}`}
      data-testid="analysis"
    >
      {/* 1. Thẻ số phân tích tổng quan (§3.1) */}
      <Card>
        <CardHeader className="pb-3">
          <CardTitle className="text-sm font-bold flex items-center justify-between">
            <span>Phân tích Bể dữ liệu (Pool)</span>
            <span className="text-xs font-normal text-muted-foreground font-mono">
              {pool.frames.toLocaleString()} frames · {pool.scenes} scenes
            </span>
          </CardTitle>
        </CardHeader>
        <CardContent className="space-y-3">
          <div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-3 gap-2">
            {poolCards.map((card) => {
              const isActive = selectedFilter === card.id;
              return (
                <button
                  key={card.id}
                  type="button"
                  onClick={() => onFilterChange?.(card.id)}
                  className={`p-2.5 rounded-lg border text-left transition-all cursor-pointer ${
                    isActive
                      ? card.activeBg
                      : `bg-card ${card.color} hover:bg-slate-50`
                  }`}
                  data-testid={`metric-card-${card.id}`}
                >
                  {/* Tiêu đề: cho phép xuống tối đa 2 dòng, không cắt chữ; giữ chiều cao đồng nhất giữa các thẻ */}
                  <div className="text-[11px] font-medium text-slate-500 leading-snug min-h-[2.75em] break-words">
                    {card.title}
                  </div>
                  <div className="text-lg font-bold font-mono my-0.5 text-slate-900">
                    {card.value}
                  </div>
                  <div className="text-[10px] text-slate-400 truncate">
                    {card.sub}
                  </div>
                </button>
              );
            })}
          </div>

          {/* Biểu đồ Histogram */}
          {renderHistogram()}
        </CardContent>
      </Card>

      {/* 2. Hiệu năng tập 5% đã chọn (§3.2) */}
      <Card>
        <CardHeader className="pb-3">
          <CardTitle className="text-sm font-bold flex items-center justify-between">
            <span>Hiệu năng Tập Đã Chọn (5%)</span>
            {selectedMetrics && (
              <span className="text-xs font-semibold font-mono text-emerald-600 bg-emerald-50 px-2 py-0.5 rounded border border-emerald-200">
                Uplift: {selectedMetrics.uplift.toFixed(2)}x
              </span>
            )}
          </CardTitle>
        </CardHeader>
        <CardContent className="space-y-4">
          {/* 4 chỉ số chính */}
          {selectedMetrics && (
            <div className="grid grid-cols-2 sm:grid-cols-4 gap-2">
              <div className="p-2.5 bg-slate-50 rounded-lg border border-slate-100">
                <div className="text-[11px] text-slate-500">Recall@5%</div>
                <div className="text-base font-bold font-mono text-slate-900">
                  {(selectedMetrics.recall * 100).toFixed(1)}%
                </div>
                {selected.random && (
                  <div className="text-[10px] text-slate-400">
                    ngẫu nhiên: {(selected.random.mean.recall * 100).toFixed(1)}%
                  </div>
                )}
              </div>

              <div className="p-2.5 bg-slate-50 rounded-lg border border-slate-100">
                <div className="text-[11px] text-slate-500">{isLidar ? "nRecall" : "Độ thừa (Redundancy)"}</div>
                <div className="text-base font-bold font-mono text-slate-900">
                  {isLidar ? `${((selectedMetrics.nRecall ?? selectedMetrics.recall) * 100).toFixed(1)}%` : `${(selectedMetrics.redundancy * 100).toFixed(1)}%`}
                </div>
                <div className="text-[10px] text-emerald-600 font-medium">
                  {isLidar && ci95
                    ? `CI95 ${(ci95.low * 100).toFixed(0)}–${(ci95.high * 100).toFixed(0)}%`
                    : "giảm đáng kể"}
                </div>
              </div>

              <div className="p-2.5 bg-slate-50 rounded-lg border border-slate-100">
                <div className="text-[11px] text-slate-500">{isLidar ? "Scene-Recall" : "Độ phủ (Coverage)"}</div>
                <div className="text-base font-bold font-mono text-slate-900">
                  {isLidar ? `${((selectedMetrics.sceneRecall ?? selectedMetrics.coverage) * 100).toFixed(1)}%` : `${(selectedMetrics.coverage * 100).toFixed(1)}%`}
                </div>
                <div className="text-[10px] text-blue-600 font-medium">
                  {isLidar ? `${selectedMetrics.nBoxes ?? 0} box` : `+${((selectedMetrics.coverageGain ?? 0) * 100).toFixed(1)}%`}
                </div>
              </div>

              <div className="p-2.5 bg-slate-50 rounded-lg border border-slate-100">
                <div className="text-[11px] text-slate-500">Scene phủ sóng</div>
                <div className="text-base font-bold font-mono text-slate-900">
                  {selected.scenesCovered} / {pool.scenes}
                </div>
                <div className="text-[10px] text-slate-400">
                  {Math.round((selected.scenesCovered / Math.max(1, pool.scenes)) * 100)}% toàn bộ
                </div>
              </div>
            </div>
          )}

          {/* Phân bố lý do chọn (Novelty / Uncertainty / Query) */}
          {(() => {
            const selectedExtra = selected as typeof selected & {
              reasonDistribution?: Partial<Record<"novelty" | "uncertainty" | "query", number>>;
              reasons?: Partial<Record<"rarity" | "novelty" | "uncertainty" | "query" | "other", number>>;
            };
            const reasons = (selectedExtra.reasonDistribution ?? selectedExtra.reasons) as Partial<Record<"rarity" | "novelty" | "uncertainty" | "query" | "other", number>> | undefined;
            if (!reasons) return null;
            if (isLidar) {
              const rar = reasons.rarity ?? reasons.novelty ?? 0;
              const nov = reasons.novelty ?? 0;
              const unc = reasons.uncertainty ?? 0;
              const tot = Math.max(1, rar + nov + unc);
              return (
                <div className="space-y-1.5">
                  <div className="flex items-center justify-between text-xs text-slate-600">
                    <span className="font-medium">Phân bố lý do tuyển chọn:</span>
                    <span className="text-[11px] font-mono text-slate-400">Rar: {rar} · Nov: {nov} · Unc: {unc}</span>
                  </div>
                  <div className="h-3 w-full bg-slate-100 rounded-full flex overflow-hidden">
                    <div style={{ width: `${(rar / tot) * 100}%` }} className="bg-vcf-accent h-full" title="Hiếm" />
                    <div style={{ width: `${(nov / tot) * 100}%` }} className="bg-vcf-accent-soft h-full" title="Lạ với model" />
                    <div style={{ width: `${(unc / tot) * 100}%` }} className="bg-vcf-accent-ink h-full" title="Không chắc" />
                  </div>
                  <div className="flex items-center justify-between text-[10px] text-slate-500">
                    <span>Hiếm</span><span>Lạ với model</span><span>Không chắc</span>
                  </div>
                </div>
              );
            }
            const nov = reasons.novelty ?? 0;
            const unc = reasons.uncertainty ?? 0;
            const qry = reasons.query ?? 0;
            const tot = Math.max(1, nov + unc + qry);
            return (
              <div className="space-y-1.5">
                <div className="flex items-center justify-between text-xs text-slate-600">
                  <span className="font-medium">Phân bố lý do tuyển chọn:</span>
                  <span className="text-[11px] font-mono text-slate-400">
                    Nov: {nov} · Unc: {unc} · Qry: {qry}
                  </span>
                </div>
                <div className="h-3 w-full bg-slate-100 rounded-full flex overflow-hidden">
                  <div
                    style={{
                      width: `${(nov / tot) * 100}%`,
                    }}
                    className="bg-vcf-accent h-full"
                    title="Độ hiếm"
                  />
                  <div
                    style={{
                      width: `${(unc / tot) * 100}%`,
                    }}
                    className="bg-vcf-accent-soft h-full"
                    title="Độ khó"
                  />
                  <div
                    style={{
                      width: `${(qry / tot) * 100}%`,
                    }}
                    className="bg-vcf-accent-ink h-full"
                    title="Khớp kịch bản"
                  />
                </div>
                <div className="flex items-center justify-between text-[10px] text-slate-500">
                  <span className="flex items-center gap-1">
                    <span className="w-2 h-2 rounded-full bg-vcf-accent" /> Độ hiếm
                  </span>
                  <span className="flex items-center gap-1">
                    <span className="w-2 h-2 rounded-full bg-vcf-accent-soft border border-vcf-accent" /> Độ khó
                  </span>
                  <span className="flex items-center gap-1">
                    <span className="w-2 h-2 rounded-full bg-vcf-accent-ink" /> Khớp kịch bản
                  </span>
                </div>
              </div>
            );
          })()}

          {/* Recall theo từng nhóm A / B / C */}
          {selected.recallByGroup && (
            <div className="pt-2 border-t border-slate-100">
              <div className="text-xs font-medium text-slate-600 mb-2">
                Recall theo nhóm hiếm (A / B / B′ / C):
              </div>
              <div className="grid grid-cols-2 gap-2 text-center">
                <div className="p-2 bg-slate-50 rounded border border-slate-100">
                  <div className="text-[10px] text-slate-500">A · Môi trường</div>
                  <div className="text-sm font-bold font-mono text-slate-800">
                    {(selected.recallByGroup.A * 100).toFixed(1)}%
                  </div>
                </div>
                <div className="p-2 bg-slate-50 rounded border border-slate-100">
                  <div className="text-[10px] text-slate-500">B · Lớp hiếm</div>
                  <div className="text-sm font-bold font-mono text-slate-800">
                    {(selected.recallByGroup.B * 100).toFixed(1)}%
                  </div>
                </div>
                <div className="p-2 bg-slate-50 rounded border border-slate-100">
                  <div className="text-[10px] text-slate-500">B′ · Lớp trung bình</div>
                  <div className="text-sm font-bold font-mono text-slate-800">
                    {(((selected.recallByGroup as Record<string, number>).Bp ?? 0) * 100).toFixed(1)}%
                  </div>
                </div>
                <div className="p-2 bg-slate-50 rounded border border-slate-100">
                  <div className="text-[10px] text-slate-500">C · Cảm biến</div>
                  <div className="text-sm font-bold font-mono text-slate-800">
                    {(selected.recallByGroup.C * 100).toFixed(1)}%
                  </div>
                </div>
              </div>
            </div>
          )}
        </CardContent>
      </Card>
    </div>
  );
}
export default AnalysisPanel;
