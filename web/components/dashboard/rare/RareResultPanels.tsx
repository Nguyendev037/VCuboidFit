import React from "react";
import type { RareAnalysis } from "@/lib/api/types";
import { KpiStrip } from "./KpiStrip";
import { ClassMixBar } from "./ClassMixBar";
import { ResultActions } from "./ResultActions";
export { ResultActions };
/** Tổng quan lô rare_v24: 4 số + thanh ngang loại vật (người dùng 2026-10-22: bỏ biểu đồ khoảng cách, giữ một biểu đồ to). */
export function RareResultPanels({ analysis }: { analysis: RareAnalysis }) {
  return <div className="space-y-4">
    <KpiStrip analysis={analysis} />
    <ClassMixBar analysis={analysis} />
  </div>;
}
