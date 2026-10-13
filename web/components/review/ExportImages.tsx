"use client";
import React, { useState } from "react";
import { exportImagesUrl } from "@/lib/api/client";
export function ExportImages({ jobId, sid, budget }: {jobId: string; sid: string; budget: number}) {
 const [cams,setCams] = useState<"all"|"front">("all");
 const [lidar,setLidar] = useState(true);
 return <div className="flex flex-wrap items-center gap-2 text-xs">
 <select aria-label="Camera xuất ảnh" value={cams} onChange={e=>setCams(e.target.value as "all"|"front")} className="rounded border p-2"><option value="all">6 camera</option><option value="front">Chỉ camera trước</option></select>
 <label className="flex items-center gap-1"><input type="checkbox" checked={lidar} onChange={e=>setLidar(e.target.checked)}/>Kèm ảnh LiDAR</label>
 <a className="rounded-lg border border-blue-300 bg-blue-50 px-3 py-2 font-semibold text-blue-800" href={exportImagesUrl(jobId,sid,budget,{cams,lidar})}>Xuất ảnh hiếm (ZIP)</a></div>;
}
