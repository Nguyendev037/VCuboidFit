"use client";
import React, { useState } from "react";
import { exportImagesUrl } from "@/lib/api/client";
import { ApiError } from "@/lib/api/errors";
import { fetchExport } from "@/lib/exportDownload";
export function ExportImages({ jobId, sid, budget }: {jobId: string; sid: string; budget: number}) {
 const [cams,setCams] = useState<"all"|"front">("all");
 const [lidar,setLidar] = useState(true);
 const [busy,setBusy]=useState(false);
 const [error,setError]=useState<string|null>(null);
 const download=async()=>{
  setBusy(true);setError(null);
  try {
   const blob=await fetchExport(exportImagesUrl(jobId,sid,budget,{cams,lidar}));
   const url=URL.createObjectURL(blob);const anchor=document.createElement("a");
   anchor.href=url;anchor.download=`vcf_${jobId}_${sid}_rare.zip`;anchor.click();
   setTimeout(()=>URL.revokeObjectURL(url),1000);
  } catch(err) {
   setError(err instanceof ApiError ? `${err.status || "network"} · ${err.code}: ${err.message}` : String(err));
  } finally {setBusy(false);}
 };
 return <div className="flex flex-wrap items-center gap-2 text-xs">
 <select aria-label="Camera xuất ảnh" value={cams} onChange={e=>setCams(e.target.value as "all"|"front")} className="rounded border p-2"><option value="all">6 camera</option><option value="front">Chỉ camera trước</option></select>
 <label className="flex items-center gap-1"><input type="checkbox" checked={lidar} onChange={e=>setLidar(e.target.checked)}/>Kèm ảnh LiDAR</label>
 <button type="button" disabled={busy} onClick={()=>void download()} className="rounded-lg border border-vcf-accent bg-vcf-accent-soft px-3 py-2 font-semibold text-vcf-accent-ink disabled:opacity-50">{busy ? "Đang tải ZIP…" : "Xuất ảnh hiếm (ZIP)"}</button>
 {error&&<div role="alert" className="w-full rounded-vcf-control border border-vcf-danger bg-vcf-danger-soft p-3 text-vcf-danger"><p>Xuất ZIP lỗi: {error}</p><p>Kiểm tra worker và lô đã chọn, rồi tải lại.</p><button type="button" disabled={busy} onClick={()=>void download()} className="mt-2 underline">Tải lại</button></div>}</div>;
}
