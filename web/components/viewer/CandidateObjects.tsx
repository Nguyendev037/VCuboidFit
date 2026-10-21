"use client";

import React, { useState } from "react";
import type { RareObject } from "@/lib/api/types";
import { objectClassLabel, objectReasonText, predTagLabel } from "@/lib/glossary";

/** Tham số box 3D của một vật ứng viên (hệ EGO nuScenes: x tiến, y trái, z lên). */
export interface CandidateBoxParams {
  cx: number; cy: number; cz: number;
  l: number; w: number; h: number; yaw: number;
}

/**
 * Dấu 8 góc theo ĐÚNG thứ tự của `c4/data/geometry.py::box_corners` (size = w, l, h): hàng `l` dọc trục x,
 * `w` dọc trục y, `h` dọc trục z; góc 0–3 là mặt trước (+x). Box ứng viên BẮT BUỘC dùng chung quy ước này với
 * box GT, nếu không `cornersToCuboid` dựng ra cuboid lệch 90° và tráo trục kích thước (F2 · H25).
 */
const BOX_CORNER_SIGNS: readonly (readonly [number, number, number])[] = [
  [1, 1, 1], [1, -1, 1], [1, -1, -1], [1, 1, -1],
  [-1, 1, 1], [-1, -1, 1], [-1, -1, -1], [-1, 1, -1],
];

/** 8 góc (24 số, hàng-ngang x,y,z) của box ứng viên trong HỆ EGO — cùng quy ước với box GT. */
export function candidateBoxCorners(o: CandidateBoxParams): number[] {
  const cos = Math.cos(o.yaw);
  const sin = Math.sin(o.yaw);
  return BOX_CORNER_SIGNS.flatMap(([sx, sy, sz]) => {
    const x = (sx * o.l) / 2;
    const y = (sy * o.w) / 2;
    return [o.cx + x * cos - y * sin, o.cy + x * sin + y * cos, o.cz + (sz * o.h) / 2];
  });
}

export function CandidateObjects({ objects = [], predTags = [] }: { objects?: RareObject[]; predTags?: string[] }) {
  const [expandedFrame, setExpandedFrame] = useState<string | null>(null);
  const frameToken = objects[0]?.sample_token ?? "";
  const expanded = expandedFrame === frameToken;
  const sortedObjects = [...objects].sort((a, b) => (b.s_obj ?? 0) - (a.s_obj ?? 0));
  const visibleObjects = expanded ? sortedObjects : sortedObjects.slice(0, 6);

  if (!objects.length && !predTags.length) return null;
  return (
    <section className="space-y-2 text-xs">
      <h4 className="font-semibold">Ứng viên LiDAR · Chưa xác nhận</h4>
      <p>{predTags.map(t => `${predTagLabel(t)} (dự đoán)`).join(" · ")}</p>
      {visibleObjects.map(o => (
        <article key={o.object_id} className="rounded border border-white/10 p-2">
          <strong>{objectClassLabel(o.cls_pred)} · Chưa xác nhận</strong>
          <p>{Number.isFinite(o.dist_m) ? `cách ${Math.round(o.dist_m)} m · ` : ""}Điểm: {Number.isFinite(o.s_obj) ? o.s_obj.toFixed(2) : "—"} (dự đoán)</p>
          <p>{objectReasonText(o.reasons)}</p>
          {o.concept_top && <p>Khái niệm gần nhất: {o.concept_top}{o.concept_score != null ? ` (${o.concept_score.toFixed(2)})` : ""}</p>}
        </article>
      ))}
      {!expanded && sortedObjects.length > 6 && (
        <button type="button" className="text-blue-400 hover:underline" onClick={() => setExpandedFrame(frameToken)}>
          Xem thêm ({sortedObjects.length - 6})
        </button>
      )}
    </section>
  );
}
