import React from "react";
import { getCategoryColor } from "./lidarDecoder";
export function ViewerLegend() {
 return <div aria-label="Chú giải box" className="flex flex-wrap gap-x-4 gap-y-1 px-3 py-2 text-xs text-slate-200 bg-black/40">
  <span>GT: nét liền · ứng viên: nét đứt (chưa xác nhận)</span>
  {[["vehicle.car","Xe"],["human.pedestrian","VRU · người đi bộ"],["vehicle.bicycle","VRU · xe đạp/xe máy"]].map(([category,label])=><span key={category} className="inline-flex items-center gap-1"><span aria-hidden="true" style={{backgroundColor:getCategoryColor(category)}} className="h-2.5 w-2.5 rounded-full" />{label}</span>)}
 </div>;
}
