import type { Cam, CamDetail } from "@/lib/api/types";

export interface CameraGrouping {
  front: CamDetail[];
  back: CamDetail[];
  all: CamDetail[];
}

export const FRONT_CAMERAS: Cam[] = [
  "CAM_FRONT_LEFT",
  "CAM_FRONT",
  "CAM_FRONT_RIGHT",
];

export const BACK_CAMERAS: Cam[] = [
  "CAM_BACK_LEFT",
  "CAM_BACK",
  "CAM_BACK_RIGHT",
];

/**
 * Phân chia danh sách camera thành 2 hàng: trước (3 cam) và sau (3 cam).
 * Các camera thiếu sẽ tự động bị bỏ qua (ô thiếu tự ẩn, lưới tự co giãn).
 */
export function groupCamerasByPosition(cams: CamDetail[] = []): CameraGrouping {
  const camMap = new Map<Cam, CamDetail>();
  for (const c of cams) {
    camMap.set(c.cam, c);
  }

  const front: CamDetail[] = [];
  for (const name of FRONT_CAMERAS) {
    const found = camMap.get(name);
    if (found) front.push(found);
  }

  const back: CamDetail[] = [];
  for (const name of BACK_CAMERAS) {
    const found = camMap.get(name);
    if (found) back.push(found);
  }

  return {
    front,
    back,
    all: cams,
  };
}

export interface ViewerActions {
  onPrev?: () => void;
  onNext?: () => void;
  onClose?: () => void;
  setMode?: (mode: "surround" | "focus") => void;
  setFocusTarget?: (target: Cam | "lidar") => void;
  toggleBoxes?: () => void;
  toggleLidarOverlay?: () => void;
  toggleInfoPanel?: () => void;
  reset3dView?: () => void;
}

/**
 * Xử lý phím tắt cho Frame Viewer theo spec tổng §5.4.
 * ←/→, Esc, 0, 1–6, 7/L, B, P, I, R.
 */
export function handleViewerKeyDown(
  e: { key: string; code?: string; preventDefault?: () => void },
  actions: ViewerActions
): boolean {
  switch (e.key) {
    case "ArrowLeft":
      e.preventDefault?.();
      actions.onPrev?.();
      return true;
    case "ArrowRight":
      e.preventDefault?.();
      actions.onNext?.();
      return true;
    case "Escape":
      e.preventDefault?.();
      actions.onClose?.();
      return true;
    case "0":
      e.preventDefault?.();
      actions.setMode?.("surround");
      return true;
    case "1":
      e.preventDefault?.();
      actions.setMode?.("focus");
      actions.setFocusTarget?.("CAM_FRONT_LEFT");
      return true;
    case "2":
      e.preventDefault?.();
      actions.setMode?.("focus");
      actions.setFocusTarget?.("CAM_FRONT");
      return true;
    case "3":
      e.preventDefault?.();
      actions.setMode?.("focus");
      actions.setFocusTarget?.("CAM_FRONT_RIGHT");
      return true;
    case "4":
      e.preventDefault?.();
      actions.setMode?.("focus");
      actions.setFocusTarget?.("CAM_BACK_LEFT");
      return true;
    case "5":
      e.preventDefault?.();
      actions.setMode?.("focus");
      actions.setFocusTarget?.("CAM_BACK");
      return true;
    case "6":
      e.preventDefault?.();
      actions.setMode?.("focus");
      actions.setFocusTarget?.("CAM_BACK_RIGHT");
      return true;
    case "7":
    case "l":
    case "L":
      e.preventDefault?.();
      actions.setMode?.("focus");
      actions.setFocusTarget?.("lidar");
      return true;
    case "b":
    case "B":
      e.preventDefault?.();
      actions.toggleBoxes?.();
      return true;
    case "p":
    case "P":
      e.preventDefault?.();
      actions.toggleLidarOverlay?.();
      return true;
    case "i":
    case "I":
      e.preventDefault?.();
      actions.toggleInfoPanel?.();
      return true;
    case "r":
    case "R":
      e.preventDefault?.();
      actions.reset3dView?.();
      return true;
    default:
      return false;
  }
}
