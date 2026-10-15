"use client";

import React, { useEffect, useMemo, useRef, useState } from "react";
import { Canvas, useThree } from "@react-three/fiber";
import { OrbitControls, OrthographicCamera, PerspectiveCamera } from "@react-three/drei";
import * as THREE from "three";
import type { OrbitControls as OrbitControlsImpl } from "three-stdlib";
import { Camera, Layers, Palette, RotateCcw, ScanLine, SlidersHorizontal } from "lucide-react";
import type { RareObject } from "@/lib/api/types";
import type { Cam } from "@/lib/api/types";
import { candidateBoxCorners } from "./CandidateObjects";
import { POINTPILLARS_COLOR } from "./ViewerLegend";
import {
  decodeFloat16Lidar,
  estimateGroundLevel,
  filterLidarPointCloud,
  getLidarDisplayColors,
  lidarDisplayRgb,
  LIDAR_POINT_STYLE,
  type LidarColorMode,
  type LidarPointCloud,
} from "./lidarDecoder";
import {
  Boxes3DMesh,
  CameraFrustums,
  EgoVehicle,
  GroundReference,
  PointCloudMesh,
  type CameraPose,
} from "./lidarSceneObjects";

export type BoxSource = "gt" | "cluster" | "pointpillars" | "merged";
export type Box3D = { category: string; corners: number[]; candidate?: boolean; source?: BoxSource };
export interface LayerToggles { gt: boolean; cluster: boolean; pointpillars: boolean; frustums: boolean }
export const DEFAULT_LAYER_TOGGLES: LayerToggles = {
  gt: true,
  cluster: true,
  pointpillars: true,
  frustums: false,
};

type ViewMode = "free" | "top" | "rear";
type SceneView = "main" | "top" | "side" | "front";

export interface LidarSceneProps {
  lidarUrl?: string | null;
  boxes3d?: Box3D[];
  objects?: RareObject[];
  camPoses?: CameraPose[];
  showBoxes?: boolean;
  onSelectCam?: (cam: Cam) => void;
  resetTrigger?: number;
  className?: string;
  layerToggles?: LayerToggles;
  onToggleLayer?: (layer: keyof LayerToggles) => void;
  filterEgo?: boolean;
  onToggleFilterEgo?: () => void;
}

/** Góc nhìn: ego tiến theo +x (Three), trái = -z. "Sau" = camera đuổi phía sau xe nhìn về trước. */
function CameraController({ viewMode, resetTrigger, groundY }: { viewMode: ViewMode; resetTrigger: number; groundY: number }) {
  const { camera } = useThree();
  const controlsRef = useRef<OrbitControlsImpl>(null);
  const groundRef = useRef(groundY);
  useEffect(() => { groundRef.current = groundY; }, [groundY]);

  useEffect(() => {
    const controls = controlsRef.current;
    if (!controls) return;
    const g = groundRef.current;
    if (viewMode === "top") {
      camera.position.set(4, g + 62, 0.001);
      camera.up.set(1, 0, 0);
      controls.target.set(4, g, 0);
    } else if (viewMode === "rear") {
      camera.position.set(-9, g + 4.2, 0);
      camera.up.set(0, 1, 0);
      controls.target.set(14, g + 0.8, 0);
    } else {
      camera.position.set(-15, g + 15, 15);
      camera.up.set(0, 1, 0);
      controls.target.set(5, g, 0);
    }
    controls.update();
  }, [camera, resetTrigger, viewMode]);

  return <OrbitControls ref={controlsRef} enableDamping dampingFactor={0.08} maxDistance={140} minDistance={1.5} maxPolarAngle={Math.PI * 0.495} />;
}

const SCENE_BG = "#070b12";
/**
 * LIDAR_TOP nuScenes gắn ở x ≈ 0.94 m hệ ego, trục cảm biến x→phải, y→trước (xoay -90° quanh z so với ego).
 * Cloud ở hệ cảm biến ⇒ hiển thị: xoay -90° quanh trục đứng Three + dịch (0.94, nâng, 0) để đầu xe trùng hướng đường.
 */
const LIDAR_TOP_MOUNT_X = 0.94;

/** Thanh màu chú giải: cùng dải turbo với điểm. */
const LIDAR_GRADIENT_CSS = `linear-gradient(90deg, ${Array.from({ length: 9 }, (_, i) => {
  const [r, g, b] = lidarDisplayRgb(i / 8);
  return `rgb(${Math.round(r * 255)} ${Math.round(g * 255)} ${Math.round(b * 255)}) ${(i / 8) * 100}%`;
}).join(", ")})`;

function SceneContents({
  view,
  pointCloud,
  colors,
  pointSize,
  groundY,
  pointLift = 0,
  boxes3d,
  showBoxes,
  camPoses,
  showFrustums = false,
  onSelectCam,
  viewMode = "free",
  resetTrigger = 0,
}: {
  view: SceneView;
  pointCloud: LidarPointCloud | null;
  colors: Float32Array | null;
  pointSize: number;
  groundY: number;
  pointLift?: number;
  boxes3d: Box3D[];
  showBoxes: boolean;
  camPoses: CameraPose[];
  showFrustums?: boolean;
  onSelectCam?: (cam: Cam) => void;
  viewMode?: ViewMode;
  resetTrigger?: number;
}) {
  const { scene } = useThree();
  useEffect(() => {
    if (typeof window !== "undefined") {
      (window as unknown as { __vcf_scene?: THREE.Scene }).__vcf_scene = scene;
    }
  }, [scene]);
  const isMain = view === "main";

  return <>
    {isMain && <fog attach="fog" args={[SCENE_BG, 70, 160]} />}
    <hemisphereLight args={["#dbeafe", "#0b1220", 0.9]} />
    <ambientLight intensity={0.25} />
    <directionalLight position={[-8, 16, 10]} intensity={1.6} />
    <directionalLight position={[10, 6, -12]} intensity={0.45} color="#93c5fd" />
    {isMain ? <>
      <PerspectiveCamera makeDefault fov={50} near={0.1} far={500} position={[13, 16, 18]} />
      <CameraController viewMode={viewMode} resetTrigger={resetTrigger} groundY={groundY} />
    </> : <>
      <OrthographicCamera makeDefault position={
        view === "top" ? [6, 50, 0.001] : view === "side" ? [0, groundY + 1, 50] : [50, groundY + 1, 0]
      } up={view === "top" ? [1, 0, 0] : [0, 1, 0]} zoom={view === "top" ? 2.4 : 3} near={0.1} far={500} onUpdate={(camera) => camera.lookAt(view === "top" ? 6 : 0, view === "top" ? 0 : groundY + 1, 0)} />
    </>}
    {(isMain || view === "top") && <GroundReference groundY={groundY} labels={isMain} grid={isMain} />}
    <EgoVehicle groundY={groundY} detailed={isMain} />
    {pointCloud && colors && (
      <group
        position={pointLift > 0 ? [LIDAR_TOP_MOUNT_X, pointLift, 0] : [0, 0, 0]}
        rotation={[0, pointLift > 0 ? -Math.PI / 2 : 0, 0]}
      >
      <PointCloudMesh
        pointCloud={pointCloud}
        colors={colors}
        size={isMain ? pointSize : Math.min(pointSize, 1.25)}
        mini={!isMain}
      />
      </group>
    )}
    {showBoxes && <Boxes3DMesh boxes3d={boxes3d} compact={!isMain} />}
    {isMain && showFrustums && <CameraFrustums camPoses={camPoses} onSelectCam={onSelectCam} />}
  </>;
}

export function LidarScene({
  lidarUrl,
  boxes3d = [],
  objects = [],
  camPoses = [],
  showBoxes = true,
  onSelectCam,
  resetTrigger = 0,
  className = "",
  layerToggles: propLayerToggles,
  onToggleLayer,
  filterEgo: propFilterEgo,
  onToggleFilterEgo,
}: LidarSceneProps) {
  const [internalLayers, setInternalLayers] = useState<LayerToggles>(DEFAULT_LAYER_TOGGLES);
  const activeLayers = propLayerToggles ?? internalLayers;
  const [internalFilterEgo, setInternalFilterEgo] = useState(true);
  const filterEgo = propFilterEgo ?? internalFilterEgo;

  const handleToggle = (key: keyof LayerToggles) => {
    if (onToggleLayer) {
      onToggleLayer(key);
    } else {
      setInternalLayers((prev) => ({ ...prev, [key]: !prev[key] }));
    }
  };

  const toggleFilterEgo = () => {
    if (onToggleFilterEgo) {
      onToggleFilterEgo();
    } else {
      setInternalFilterEgo((prev) => !prev);
    }
  };

  const displayBoxes: Box3D[] = useMemo(() => {
    if (!showBoxes) return [];
    const all: Box3D[] = [
      ...boxes3d.map((b) => ({
        ...b,
        source: b.source ?? "gt",
        candidate: b.candidate ?? false,
      })),
      ...objects.map((o) => {
        const source: BoxSource =
          o.source === "pointpillars"
            ? "pointpillars"
            : o.source === "merged"
            ? "merged"
            : "cluster";
        return {
          category: o.cls_pred,
          corners: candidateBoxCorners(o),
          candidate: true,
          source,
        };
      }),
    ];

    return all.filter((box) => {
      const src = box.source ?? (box.candidate ? "cluster" : "gt");
      if (src === "gt") return activeLayers.gt;
      if (src === "cluster") return activeLayers.cluster;
      if (src === "pointpillars") return activeLayers.pointpillars;
      if (src === "merged") return activeLayers.cluster || activeLayers.pointpillars;
      return true;
    });
  }, [showBoxes, boxes3d, objects, activeLayers.gt, activeLayers.cluster, activeLayers.pointpillars]);

  const [pointCloud, setPointCloud] = useState<LidarPointCloud | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [retryVersion, setRetryVersion] = useState(0);
  const [viewMode, setViewMode] = useState<ViewMode>("free");
  const [colorMode, setColorMode] = useState<LidarColorMode>("height");
  const [pointSize, setPointSize] = useState<number>(LIDAR_POINT_STYLE.defaultSize);
  const [cameraReset, setCameraReset] = useState(0);
  const [mobileControlsOpen, setMobileControlsOpen] = useState(false);
  const filteredPointCloud = useMemo(
    () => (pointCloud ? filterLidarPointCloud(pointCloud, filterEgo) : null),
    [pointCloud, filterEgo],
  );
  const display = useMemo(
    () => (filteredPointCloud ? getLidarDisplayColors(filteredPointCloud, colorMode) : null),
    [colorMode, filteredPointCloud],
  );
  const colors = display?.colors ?? null;
  // Mặt đất ước lượng từ cloud GỐC (không đổi khi bật/tắt lọc thân xe).
  const rawGround = useMemo(() => (pointCloud ? estimateGroundLevel(pointCloud) : 0), [pointCloud]);
  // Mặt đất < -1.2 m ⇒ cloud gần như chắc ở hệ CẢM BIẾN (LiDAR cao ~1.8 m), còn box ở hệ ego (mặt đất ~0):
  // chỉ khi HIỂN THỊ thì đưa điểm về hệ ego (xoay + nâng, xem LIDAR_TOP_MOUNT_X); dữ liệu/bộ lọc không đổi.
  // Cloud hệ ego chuẩn (đầu ra worker) ⇒ pointLift = 0, không xoay.
  const pointLift = rawGround < -1.2 ? -rawGround : 0;
  const groundY = rawGround + pointLift;
  const activePointCloud = lidarUrl ? filteredPointCloud : null;
  const activeError = lidarUrl ? error : null;
  const activeLoading = Boolean(lidarUrl && loading);

  useEffect(() => {
    let active = true;
    if (!lidarUrl) return () => { active = false; };
    queueMicrotask(() => {
      if (active) {
        setLoading(true);
        setError(null);
      }
    });
    fetch(lidarUrl)
      .then((response) => { if (!response.ok) throw new Error(`HTTP ${response.status}`); return response.arrayBuffer(); })
      .then((buffer) => { if (active) setPointCloud(decodeFloat16Lidar(buffer)); })
      .catch((reason: unknown) => { if (active) setError(reason instanceof Error ? reason.message : "Lỗi tải point cloud"); })
      .finally(() => { if (active) setLoading(false); });
    return () => { active = false; };
  }, [lidarUrl, retryVersion]);

  const segBtn = (active: boolean) =>
    `rounded-md px-2 py-1 text-[11px] font-medium leading-none transition-colors focus-visible:outline focus-visible:outline-1 focus-visible:outline-sky-300 ${active ? "bg-white/[0.14] text-white shadow-sm ring-1 ring-inset ring-white/15" : "text-slate-400 hover:bg-white/[0.06] hover:text-slate-100"}`;
  const chip = (active: boolean) =>
    `inline-flex items-center gap-1.5 rounded-md px-2 py-1 text-[11px] font-medium leading-none ring-1 ring-inset transition-colors focus-visible:outline focus-visible:outline-1 focus-visible:outline-sky-300 ${active ? "bg-sky-400/[0.12] text-sky-50 ring-sky-300/30" : "text-slate-400 ring-white/[0.08] hover:bg-white/[0.05] hover:text-slate-200"}`;
  const glass = "rounded-xl border border-white/[0.08] bg-slate-950/60 shadow-[0_10px_30px_-12px_rgba(0,0,0,0.7)] backdrop-blur-md";
  const segGroup = "flex items-center gap-0.5 rounded-lg bg-white/[0.03] p-0.5 ring-1 ring-inset ring-white/[0.08]";
  const icon = "h-3.5 w-3.5 shrink-0 text-slate-500";
  const formatRange = (value: number) => (colorMode === "height" ? `${(value + pointLift).toFixed(1)} m` : value.toFixed(0));

  return <div className={`relative isolate h-full min-h-[220px] overflow-hidden rounded-lg bg-[#070b12] text-white ${className}`} data-testid="lidar-scene" data-frustums={activeLayers.frustums ? "1" : "0"} data-filter-ego={filterEgo ? "1" : "0"}>
    <div aria-hidden="true" className="pointer-events-none absolute inset-0 bg-[radial-gradient(120%_95%_at_50%_28%,#132238_0%,#0a1320_48%,#05080d_100%)]" />
    <Canvas dpr={[1, 2]} flat gl={{ antialias: true, alpha: true, powerPreference: "high-performance" }} className="absolute inset-0">
      <SceneContents
        view="main"
        pointCloud={activePointCloud}
        colors={colors}
        pointSize={pointSize}
        groundY={groundY}
        pointLift={pointLift}
        boxes3d={displayBoxes}
        showBoxes={showBoxes}
        camPoses={camPoses}
        showFrustums={activeLayers.frustums}
        onSelectCam={onSelectCam}
        viewMode={viewMode}
        resetTrigger={resetTrigger + cameraReset}
      />
    </Canvas>
    <div aria-hidden="true" className="pointer-events-none absolute inset-0 shadow-[inset_0_0_140px_rgba(0,0,0,0.6)]" />

    <button type="button" aria-expanded={mobileControlsOpen} onClick={() => setMobileControlsOpen((open) => !open)} className={`absolute left-2 top-2 z-10 inline-flex items-center gap-1.5 px-2.5 py-1.5 text-[11px] font-medium text-slate-100 md:hidden ${glass}`}>
      <SlidersHorizontal aria-hidden="true" className="h-3.5 w-3.5 text-slate-400" />
      {mobileControlsOpen ? "Ẩn điều khiển" : "Điều khiển"}
    </button>
    <div className={`${mobileControlsOpen ? "flex" : "hidden"} md:flex absolute left-2 top-11 z-10 max-w-[calc(100%-1rem)] flex-col gap-1.5 p-1.5 sm:left-3 sm:top-3 md:max-w-[calc(100%-10rem)] ${glass}`}>
      <div className="flex flex-wrap items-center gap-1.5">
        <div role="group" aria-label="Góc nhìn" className={segGroup}>
          <Camera aria-hidden="true" className={`${icon} mx-1`} />
          {([ ["free", "Tự do"], ["top", "Trên"], ["rear", "Sau"] ] as const).map(([mode, label]) => <button key={mode} type="button" onClick={() => setViewMode(mode)} aria-pressed={viewMode === mode} className={segBtn(viewMode === mode)}>{label}</button>)}
          <span aria-hidden="true" className="mx-0.5 h-3.5 w-px bg-white/10" />
          <button type="button" aria-label="Đặt lại góc nhìn LiDAR" title="Đặt lại camera" onClick={() => { setViewMode("free"); setCameraReset((value) => value + 1); }} className={`${segBtn(false)} inline-flex items-center gap-1`}>
            <RotateCcw aria-hidden="true" className="h-3 w-3" />
            Đặt lại
          </button>
        </div>
        <div role="group" aria-label="Tô màu điểm" className={segGroup}>
          <Palette aria-hidden="true" className={`${icon} mx-1`} />
          {([ ["height", "Độ cao"], ["intensity", "Intensity"] ] as const).map(([mode, label]) => <button key={mode} type="button" onClick={() => setColorMode(mode)} aria-pressed={colorMode === mode} className={segBtn(colorMode === mode)}>{label}</button>)}
        </div>
      </div>
      <div role="group" aria-label="Lớp hiển thị" className="flex flex-wrap items-center gap-1">
        <Layers aria-hidden="true" className={`${icon} mx-1`} />
        <button type="button" onClick={() => handleToggle("gt")} aria-pressed={activeLayers.gt} className={chip(activeLayers.gt)}>
          <span aria-hidden="true" className="h-[2px] w-3 rounded-full bg-current opacity-80" />
          GT
        </button>
        <button type="button" onClick={() => handleToggle("cluster")} aria-pressed={activeLayers.cluster} className={chip(activeLayers.cluster)}>
          <span aria-hidden="true" className="w-3 border-t-2 border-dashed border-current opacity-80" />
          Cụm LiDAR
        </button>
        <button type="button" onClick={() => handleToggle("pointpillars")} aria-pressed={activeLayers.pointpillars} className={chip(activeLayers.pointpillars)}>
          <span aria-hidden="true" className="w-3 border-t-2 border-dashed" style={{ borderColor: POINTPILLARS_COLOR }} />
          PointPillars
        </button>
        <span aria-hidden="true" className="mx-0.5 h-3.5 w-px bg-white/10" />
        <button type="button" onClick={() => handleToggle("frustums")} aria-pressed={activeLayers.frustums} className={chip(activeLayers.frustums)}>
          Camera (C)
        </button>
        <button
          type="button"
          onClick={toggleFilterEgo}
          aria-pressed={!filterEgo}
          data-filter-ego={filterEgo ? "on" : "off"}
          className={chip(!filterEgo)}
          title={filterEgo ? "Hiện điểm thân xe" : "Ẩn điểm thân xe"}
        >
          Điểm thân xe
        </button>
      </div>
      <label className="flex items-center gap-2 px-1 text-[11px] text-slate-400">
        <SlidersHorizontal aria-hidden="true" className="h-3.5 w-3.5 text-slate-500" />
        Cỡ điểm
        <input
          aria-label="Kích thước điểm LiDAR"
          type="range"
          min={LIDAR_POINT_STYLE.minSize}
          max={LIDAR_POINT_STYLE.maxSize}
          step={LIDAR_POINT_STYLE.step}
          value={pointSize}
          onChange={(event) => setPointSize(Number(event.target.value))}
          className="h-1 w-24 cursor-pointer accent-sky-400 sm:w-28"
        />
        <output className="w-6 font-mono text-[10px] tabular-nums text-slate-300">{pointSize.toFixed(1)}</output>
      </label>
    </div>
    <div className={`absolute right-2 top-2 z-10 inline-flex items-center gap-1.5 px-2.5 py-1.5 text-[11px] font-medium tabular-nums text-slate-200 sm:right-3 sm:top-3 ${glass}`} role={loading ? "status" : undefined} aria-live="polite">
      <span aria-hidden="true" className={`h-1.5 w-1.5 rounded-full ${activeLoading ? "animate-pulse bg-amber-300" : activePointCloud ? "bg-emerald-400 shadow-[0_0_6px_rgba(52,211,153,0.8)]" : "bg-slate-500"}`} />
      {activeLoading ? "Đang nạp LiDAR…" : activePointCloud ? `${activePointCloud.count.toLocaleString()} điểm` : "Không có LiDAR"}
    </div>
    {display && activePointCloud && <div aria-hidden="true" className={`pointer-events-none absolute bottom-2 left-2 z-10 hidden px-2.5 py-1.5 sm:block sm:bottom-3 sm:left-3 ${glass}`}>
      <div className="mb-1 flex items-center gap-1.5 text-[10px] font-medium uppercase tracking-[0.12em] text-slate-400">
        <ScanLine className="h-3 w-3" />
        {colorMode === "height" ? "Độ cao" : "Intensity"}
      </div>
      <div className="h-1.5 w-36 rounded-full" style={{ backgroundImage: LIDAR_GRADIENT_CSS }} />
      <div className="mt-1 flex justify-between font-mono text-[9px] tabular-nums text-slate-400">
        <span>{formatRange(display.lo)}</span>
        <span>{formatRange(display.hi)}</span>
      </div>
    </div>}
    <div className="pointer-events-none absolute bottom-2 right-2 z-10 hidden gap-1.5 md:flex sm:bottom-3 sm:right-3 sm:gap-2">
      {([ ["top", "Trên"], ["side", "Bên"], ["front", "Trước"] ] as const).map(([key, title]) => <div key={key} className="relative h-[74px] w-[96px] overflow-hidden rounded-lg border border-white/[0.09] bg-[radial-gradient(120%_100%_at_50%_35%,#112033_0%,#070b12_100%)] shadow-[0_10px_30px_-12px_rgba(0,0,0,0.8)] lg:h-[90px] lg:w-[120px]" aria-label={`Góc nhìn ${title}`}>
        <Canvas dpr={[1, 2]} flat frameloop="demand" gl={{ antialias: true, alpha: true }}><SceneContents view={key} pointCloud={activePointCloud} colors={colors} pointSize={pointSize} groundY={groundY} pointLift={pointLift} boxes3d={displayBoxes} showBoxes={showBoxes} camPoses={[]} /></Canvas>
        <span className="absolute left-1.5 top-1 text-[9px] font-semibold uppercase tracking-[0.14em] text-slate-300/75">{title}</span>
      </div>)}
    </div>
    {(!lidarUrl || activeError) && !activeLoading && <div role={activeError ? "alert" : "status"} className="absolute inset-0 z-[5] flex flex-col items-center justify-center gap-3 bg-slate-950/50 px-4 text-center text-sm text-slate-200 backdrop-blur-[2px]">
      <p>{activeError ? `Không tải được LiDAR: ${activeError}` : "Frame này chưa có dữ liệu LiDAR"}</p>
      {activeError && <p className="break-all text-xs text-slate-400">{lidarUrl?.split("/").pop()}</p>}
      {activeError && <button type="button" onClick={() => setRetryVersion((version) => version + 1)} className="rounded-md bg-sky-500/90 px-3 py-2 text-xs font-semibold text-white shadow hover:bg-sky-400 focus-visible:outline focus-visible:outline-2 focus-visible:outline-white">Thử lại LiDAR</button>}
    </div>}
  </div>;
}

export default LidarScene;
