import React from "react";
import type { RareObject } from "@/lib/api/types";
import { PRED_TAG_LABELS } from "@/lib/glossary";
export function CandidateObjects({ objects = [], predTags = [] }: { objects?: RareObject[]; predTags?: string[] }) {
 if (!objects.length && !predTags.length) return null;
 return <section className="space-y-2 text-xs"><h4 className="font-semibold">Ứng viên LiDAR · Chưa xác nhận</h4>
 <p>{predTags.map(t=>`${PRED_TAG_LABELS[t] ?? t} (dự đoán)`).join(" · ")}</p>
 {objects.map(o=><article key={o.object_id} className="rounded border border-white/10 p-2"><strong>{o.cls_pred} · Chưa xác nhận</strong><p>{o.reasons}</p>{o.concept_top && <p>Khái niệm gần nhất: {o.concept_top}{o.concept_score != null ? ` (${o.concept_score.toFixed(2)})` : ""}</p>}</article>)}
 </section>;
}
