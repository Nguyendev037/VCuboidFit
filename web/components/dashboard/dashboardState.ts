import { DEMO_KEY } from "@/lib/api/client";
import type { Preset } from "@/lib/api/types";
import { stageLabel } from "@/lib/constants";
import { isAdvancedPanelInitiallyOpen } from "@/lib/advancedParams";
import { PANEL_HELP } from "@/lib/glossary";

export const pct=(x: number) => `${Math.round(x*100)}%`;

export const formatBytes=(bytes: number) => {
  if(bytes>=1024**3) return `${(bytes/1024**3).toFixed(1)} GB`;
  if(bytes>=1024**2) return `${Math.round(bytes/1024**2)} MB`;
  return `${Math.round(bytes/1024)} KB`;
};

export const formatDuration=(seconds: number) =>
  `${seconds<10? seconds.toFixed(1):Math.round(seconds)} s`;

export const PRESET_LABELS: Record<Preset, { title: string; desc: string }> = Object.fromEntries(
  (["balanced", "rare_first", "hard_for_model", "safety_scenarios"] as const).map((preset) => {
    const help = PANEL_HELP[`preset.${preset}`];
    return [preset, { title: help.label, desc: help.desc ?? "" }];
  }),
) as Record<Preset, { title: string; desc: string }>;

export const PRESET_LOCK_TITLE="Chiến lược chỉ đổi được khi job có Tầng 1 (model seed); job này chưa có nên dùng mặc định Tầng 0.";

export const ANALYSIS_STEPS=[
  { stage: "index", name: "Lập chỉ mục", hint: "đọc ảnh & nhãn" },
  { stage: "dino", name: "Độ hiếm", hint: "Novelty" },
  { stage: "det", name: "Độ khó", hint: "Uncertainty" },
  { stage: "clip", name: "Khớp kịch bản", hint: "Query" },
  { stage: "merge", name: "Tổng hợp S", hint: "điểm cuối" },
];

export const LIDAR_ANALYSIS_STEPS=[
  { stage: "lidar_index", name: stageLabel("lidar_index", "lidar"), hint: "đọc frame và LiDAR" },
  { stage: "t0", name: stageLabel("t0", "lidar"), hint: "đặc trưng hình học" },
];

export const demoListeners=new Set<() => void>();

export const subscribeDemo=(cb: () => void) => {
  demoListeners.add(cb);
  return () => void demoListeners.delete(cb);
};

export const getDemo=() => {
  try {
    return window.sessionStorage.getItem(DEMO_KEY)==="1";
  } catch {
    return false;
  }
};

export function setDemoFlag(on: boolean) {
  try {
    if(on) window.sessionStorage.setItem(DEMO_KEY, "1");
    else window.sessionStorage.removeItem(DEMO_KEY);
  } catch {
    /* sessionStorage bị chặn: chạy chế độ thật */
  }
  demoListeners.forEach((f) => f());
}

export const UPLOAD_COLLAPSED_KEY="vcf.uploadListCollapsed";

export const readUploadCollapsed=(): boolean|null => {
  try {
    const v=window.localStorage.getItem(UPLOAD_COLLAPSED_KEY);
    return v==="1"? true:v==="0"? false:null;
  } catch {
    return null;
  }
};

export const ADVANCED_PANEL_KEY="vcf-advanced-open";

export const ADVANCED_PANEL_CHANGE="vcf-advanced-panel-change";

export let advancedPanelFallback=false;

export const getAdvancedPanelOpen=() => {
  try {
    return isAdvancedPanelInitiallyOpen(window.localStorage);
  } catch {
    return advancedPanelFallback;
  }
};

export const subscribeAdvancedPanel=(onChange: () => void) => {
  window.addEventListener("storage", onChange);
  window.addEventListener(ADVANCED_PANEL_CHANGE, onChange);
  return () => {
    window.removeEventListener("storage", onChange);
    window.removeEventListener(ADVANCED_PANEL_CHANGE, onChange);
  };
};

export function setAdvancedPanelOpen(open: boolean) {
  advancedPanelFallback=open;
  try {
    window.localStorage.setItem(ADVANCED_PANEL_KEY, open? "1":"0");
  } catch {
    // Keep the panel state for this tab when storage is unavailable.
  }
  window.dispatchEvent(new Event(ADVANCED_PANEL_CHANGE));
}

export const DEFAULT_QUERIES=[
  "người đi bộ cắt ngang",
  "xe đạp ban đêm",
  "mưa lớn",
];

export function invalidateRecovery(request: { current: number }) {
  request.current+=1;
}
