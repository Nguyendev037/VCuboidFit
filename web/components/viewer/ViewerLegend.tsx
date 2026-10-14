import React from "react";
import { getCategoryColor } from "./lidarDecoder";

export const POINTPILLARS_COLOR = "#a855f7";

export function ViewerLegend() {
  return (
    <div aria-label="Chú giải box" className="flex flex-wrap items-center gap-x-4 gap-y-1 px-3 py-1.5 text-xs text-slate-200 bg-black/40 border-b border-white/5">
      <span>GT: nét liền · ứng viên Cụm: nét đứt theo loại · PointPillars: nét đứt tím</span>
      <span className="inline-flex items-center gap-1">
        <span aria-hidden="true" style={{ backgroundColor: POINTPILLARS_COLOR }} className="h-2.5 w-2.5 rounded-full" />
        PointPillars
      </span>
      {[
        ["vehicle.car", "Xe"],
        ["human.pedestrian", "VRU · người đi bộ"],
        ["vehicle.bicycle", "VRU · xe đạp/xe máy"],
      ].map(([category, label]) => (
        <span key={category} className="inline-flex items-center gap-1">
          <span aria-hidden="true" style={{ backgroundColor: getCategoryColor(category) }} className="h-2.5 w-2.5 rounded-full" />
          {label}
        </span>
      ))}
    </div>
  );
}
