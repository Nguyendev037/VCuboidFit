import React from "react";
import type { FrameContext } from "@/lib/api/types";
import { CONTEXT_AXES, CONTEXT_CLASSES, CV_FLAG_LABELS } from "@/lib/glossary";
export function ContextPanel({ context, cam }: { context?: FrameContext | null; cam: string }) {
 const value = context?.perCam[cam];
 if (!value) return null;
 return <section className="space-y-3 rounded-lg border border-slate-500/30 p-3 text-xs" aria-label="Bối cảnh camera">
 <h4 className="font-semibold">Bối cảnh {cam.replace("CAM_", "")} · dự đoán</h4>
 {Object.entries(CONTEXT_AXES).map(([axis,label])=><div key={axis} data-testid="context-axis"><p className="mb-1 font-semibold">{label}</p><div className="flex h-2 overflow-hidden rounded bg-slate-500/20" role="img" aria-label={`${label}: ${Object.entries(value.probs[axis] ?? {}).map(([cls,prob])=>`${CONTEXT_CLASSES[cls] ?? cls} ${Math.round(prob*100)}%`).join(", ")}`}>
 {Object.entries(value.probs[axis] ?? {}).map(([cls,prob],i)=><span key={cls} style={{width:`${Math.max(0,Math.min(1,prob))*100}%`,background:["#2563eb","#10b981","#f59e0b"][i%3]}}/>)}</div>
 <p className="mt-1">{Object.entries(value.probs[axis] ?? {}).map(([cls,prob])=>`${CONTEXT_CLASSES[cls] ?? cls}: ${(prob*100).toFixed(1)}%`).join(" · ") || "Chưa có xác suất"}</p></div>)}
 <p>Cờ CV: {value.cvFlags.map(f=>CV_FLAG_LABELS[f] ?? f).join(" · ") || "Không có"}</p>
 {value.review && <p className="font-semibold text-amber-500">Bối cảnh cần xem</p>}
 {value.reviewReasons.map(r=><p key={r}>{reviewReasonLabel(r)}</p>)}
 </section>;
}
export function reviewReasonLabel(reason: string) {
 const [axis,code] = reason.split(":");
 const labels: Record<string,string> = { DISAGREE: "Các tín hiệu không đồng ý", LOW_MARGIN: "Xác suất chưa phân biệt rõ", IMG_UNREADABLE: "Không đọc được ảnh" };
 return code ? `${CONTEXT_AXES[axis] ?? axis}: ${labels[code] ?? code}` : labels[axis] ?? reason;
}
