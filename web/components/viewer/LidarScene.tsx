"use client";

import React, { useEffect, useMemo, useRef, useState } from "react";
import { Canvas, useThree } from "@react-three/fiber";
import { Html, OrbitControls, OrthographicCamera, PerspectiveCamera } from "@react-three/drei";
import * as THREE from "three";
import type { OrbitControls as OrbitControlsImpl } from "three-stdlib";
import type { RareObject } from "@/lib/api/types";
import type { Cam } from "@/lib/api/types";
import { candidateBoxCorners } from "./CandidateObjects";
import { POINTPILLARS_COLOR } from "./ViewerLegend";
import {
  buildEgoVehicleLines,
  cornersToCuboid,
  decodeFloat16Lidar,
  filterLidarPointCloud,
  getCameraFrustumLines,
  getCategoryColor,
  getLidarColors,
  LIDAR_POINT_STYLE,
  type LidarColorMode,
  type LidarPointCloud,
} from "./lidarDecoder";

export type BoxSource = "gt" | "cluster" | "pointpillars" | "merged";
export type Box3D = { category: string; corners: number[]; candidate?: boolean; source?: BoxSource };
export interface LayerToggles { gt: boolean; cluster: boolean; pointpillars: boolean; frustums: boolean }
export const DEFAULT_LAYER_TOGGLES: LayerToggles = {
  gt: true,
  cluster: true,
  pointpillars: true,
  frustums: false,
};

type CameraPose = { cam: Cam; translation: number[]; rotation: number[]; intrinsic: number[][] };
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

function CameraController({ viewMode, resetTrigger }: { viewMode: ViewMode; resetTrigger: number }) {
  const { camera } = useThree();
  const controlsRef = useRef<OrbitControlsImpl>(null);

  useEffect(() => {
    const controls = controlsRef.current;
    if (!controls) return;
    if (viewMode === "top") {
      camera.position.set(0, 50, 0.001);
      camera.up.set(0, 0, -1);
      controls.target.set(0, 0, 0);
    } else if (viewMode === "rear") {
      camera.position.set(0, 3.5, 9);
      camera.up.set(0, 1, 0);
      controls.target.set(0, 1.2, -12);
    } else {
      camera.position.set(13, 16, 18);
      camera.up.set(0, 1, 0);
      controls.target.set(0, 0, 0);
    }
    controls.update();
  }, [camera, resetTrigger, viewMode]);

  return <OrbitControls ref={controlsRef} enableDamping dampingFactor={0.08} maxDistance={120} minDistance={1} />;
}

function PointCloudMesh({
  pointCloud,
  colors,
  size,
  opacity,
}: {
  pointCloud: LidarPointCloud;
  colors: Float32Array;
  size: number;
  opacity: number;
}) {
  const geometry = useMemo(() => {
    const value = new THREE.BufferGeometry();
    value.setAttribute("position", new THREE.BufferAttribute(pointCloud.threePositions, 3));
    value.setAttribute("color", new THREE.BufferAttribute(new Float32Array(pointCloud.count * 3), 3));
    return value;
  }, [pointCloud]);

  useEffect(() => {
    const color = geometry.getAttribute("color") as THREE.BufferAttribute;
    color.array.set(colors);
    color.needsUpdate = true;
  }, [colors, geometry]);

  useEffect(() => () => geometry.dispose(), [geometry]);

  return (
    <points geometry={geometry} frustumCulled={false}>
      <pointsMaterial size={size} vertexColors sizeAttenuation={false} transparent opacity={opacity} depthWrite={false} />
    </points>
  );
}

function Boxes3DMesh({ boxes3d }: { boxes3d: Box3D[] }) {
  return (
    <group>
      {boxes3d.map((box, index) => {
        const transform = cornersToCuboid(box.corners);
        if (!transform) return null;
        const color = getCategoryColor(box.category);
        return <Cuboid key={`${box.category}-${index}`} box={box} transform={transform} color={color} />;
      })}
    </group>
  );
}

function Cuboid({
  box,
  transform,
  color,
}: {
  box: Box3D;
  transform: NonNullable<ReturnType<typeof cornersToCuboid>>;
  color: string;
}) {
  const [hovered, setHovered] = useState(false);
  const [sizeX, sizeY, sizeZ] = transform.size;
  const boxGeometry = useMemo(() => new THREE.BoxGeometry(sizeX, sizeY, sizeZ), [sizeX, sizeY, sizeZ]);
  const geometry = useMemo(() => new THREE.EdgesGeometry(boxGeometry), [boxGeometry]);
  useEffect(() => () => { geometry.dispose(); boxGeometry.dispose(); }, [boxGeometry, geometry]);

  const isPP = box.source === "pointpillars";
  const lineColor = isPP ? POINTPILLARS_COLOR : color;

  return (
    <group
      position={transform.center}
      rotation={[0, transform.yaw, 0]}
      onPointerOver={(event) => { event.stopPropagation(); setHovered(true); }}
      onPointerOut={() => setHovered(false)}
    >
      <mesh>
        <boxGeometry args={transform.size} />
        <meshBasicMaterial color={lineColor} transparent opacity={hovered ? 0.14 : 0.045} depthWrite={false} />
      </mesh>
      <lineSegments geometry={geometry} onUpdate={line => line.computeLineDistances()}>
        {box.candidate
          ? <lineDashedMaterial color={hovered ? "#ffffff" : lineColor} dashSize={0.25} gapSize={0.15} transparent opacity={hovered ? 1 : 0.9} />
          : <lineBasicMaterial color={hovered ? "#ffffff" : lineColor} transparent opacity={hovered ? 1 : 0.9} linewidth={2} />}
      </lineSegments>
      {hovered && <Html position={[0, transform.size[1] / 2 + 0.25, 0]} center distanceFactor={18}>
        <span className="whitespace-nowrap rounded border border-white/20 bg-black/90 px-2 py-1 text-[11px] font-medium text-white shadow">
          {box.category}
          {box.candidate ? (isPP ? " · PointPillars" : box.source === "merged" ? " · Cụm/PP" : " · Cụm LiDAR") : " · GT"}
        </span>
      </Html>}
    </group>
  );
}

function EgoVehicle() {
  const geometry = useMemo(() => {
    const coords = buildEgoVehicleLines();
    return new THREE.BufferGeometry().setAttribute("position", new THREE.BufferAttribute(coords, 3));
  }, []);
  useEffect(() => () => geometry.dispose(), [geometry]);
  return <lineSegments geometry={geometry}><lineBasicMaterial color="#38bdf8" transparent opacity={0.5} /></lineSegments>;
}

function CameraFrustums({ camPoses, onSelectCam }: { camPoses: CameraPose[]; onSelectCam?: (cam: Cam) => void }) {
  return (
    <group name="camera-frustums" userData={{ isFrustum: true }}>
      {camPoses.map((pose) => <CameraFrustum key={pose.cam} pose={pose} onSelectCam={onSelectCam} />)}
    </group>
  );
}

function CameraFrustum({ pose, onSelectCam }: { pose: CameraPose; onSelectCam?: (cam: Cam) => void }) {
  const geometry = useMemo(() => new THREE.BufferGeometry().setAttribute(
    "position",
    new THREE.BufferAttribute(getCameraFrustumLines(pose.translation, pose.rotation), 3),
  ), [pose]);
  useEffect(() => () => geometry.dispose(), [geometry]);
  return <group>
    <lineSegments geometry={geometry}><lineBasicMaterial color="#60a5fa" transparent opacity={0.72} /></lineSegments>
    <mesh position={[pose.translation[0], pose.translation[2], -pose.translation[1]]} onClick={(event) => { event.stopPropagation(); onSelectCam?.(pose.cam); }}>
      <sphereGeometry args={[0.18, 8, 8]} /><meshBasicMaterial color="#60a5fa" />
    </mesh>
  </group>;
}

function SceneContents({
  view,
  pointCloud,
  colors,
  pointSize,
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

  return <>
    <color attach="background" args={["#080d15"]} />
    <ambientLight intensity={0.85} />
    <directionalLight position={[10, 18, 12]} intensity={0.65} />
    {view === "main" ? <>
      <PerspectiveCamera makeDefault fov={50} near={0.1} far={500} position={[13, 16, 18]} />
      <CameraController viewMode={viewMode} resetTrigger={resetTrigger} />
    </> : <>
      <OrthographicCamera makeDefault position={
        view === "top" ? [0, 50, 0.001] : view === "side" ? [50, 2, 0] : [0, 2, 50]
      } up={view === "top" ? [0, 0, -1] : [0, 1, 0]} zoom={3} near={0.1} far={500} onUpdate={(camera) => camera.lookAt(0, 0, 0)} />
    </>}
    <gridHelper args={[80, 80, "#334155", "#1e293b"]} position={[0, -0.05, 0]} />
    <axesHelper args={[3]} />
    <EgoVehicle />
    {pointCloud && colors && (
      <PointCloudMesh
        pointCloud={pointCloud}
        colors={colors}
        size={view === "main" ? pointSize : Math.min(pointSize, 1)}
        opacity={view === "main" ? LIDAR_POINT_STYLE.mainOpacity : LIDAR_POINT_STYLE.miniOpacity}
      />
    )}
    {showBoxes && <Boxes3DMesh boxes3d={boxes3d} />}
    {view === "main" && showFrustums && <CameraFrustums camPoses={camPoses} onSelectCam={onSelectCam} />}
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
  const colors = useMemo(
    () => (filteredPointCloud ? getLidarColors(filteredPointCloud, colorMode) : null),
    [colorMode, filteredPointCloud],
  );
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

  return <div className={`relative isolate h-full min-h-[220px] overflow-hidden rounded-lg bg-[#080d15] text-white ${className}`} data-testid="lidar-scene" data-frustums={activeLayers.frustums ? "1" : "0"} data-filter-ego={filterEgo ? "1" : "0"}>
    <Canvas dpr={[1, 1.5]} gl={{ antialias: true, powerPreference: "high-performance" }} className="absolute inset-0">
      <SceneContents
        view="main"
        pointCloud={activePointCloud}
        colors={colors}
        pointSize={pointSize}
        boxes3d={displayBoxes}
        showBoxes={showBoxes}
        camPoses={camPoses}
        showFrustums={activeLayers.frustums}
        onSelectCam={onSelectCam}
        viewMode={viewMode}
        resetTrigger={resetTrigger + cameraReset}
      />
    </Canvas>

    <button type="button" aria-expanded={mobileControlsOpen} onClick={() => setMobileControlsOpen((open) => !open)} className="absolute left-2 top-2 z-10 rounded-md border border-white/10 bg-black/75 px-2 py-1.5 text-[10px] text-white md:hidden">
      {mobileControlsOpen ? "Ẩn điều khiển" : "Điều khiển"}
    </button>
    <div className={`${mobileControlsOpen ? "flex" : "hidden"} md:flex absolute left-2 top-11 z-10 max-w-[calc(100%-5rem)] flex-wrap items-center gap-1 rounded-md border border-white/10 bg-black/80 p-1.5 text-[10px] sm:left-3 sm:top-3 sm:gap-1.5 sm:p-2 sm:text-xs`}>
      <span className="px-1 text-white/60">Góc:</span>
      {([ ["free", "Tự do"], ["top", "Trên"], ["rear", "Sau"] ] as const).map(([mode, label]) => <button key={mode} type="button" onClick={() => setViewMode(mode)} aria-pressed={viewMode === mode} className={`rounded px-2 py-1 ${viewMode === mode ? "bg-blue-600 text-white" : "bg-white/10 text-white/80 hover:bg-white/20"}`}>{label}</button>)}
      <button type="button" aria-label="Đặt lại góc nhìn LiDAR" title="Đặt lại camera" onClick={() => { setViewMode("free"); setCameraReset((value) => value + 1); }} className="rounded bg-white/10 px-2 py-1 hover:bg-white/20">Đặt lại</button>
      <span className="mx-0.5 h-4 border-l border-white/20" />
      {([ ["height", "Độ cao"], ["intensity", "Intensity"] ] as const).map(([mode, label]) => <button key={mode} type="button" onClick={() => setColorMode(mode)} aria-pressed={colorMode === mode} className={`rounded px-2 py-1 ${colorMode === mode ? "bg-blue-600 text-white" : "bg-white/10 text-white/80 hover:bg-white/20"}`}>{label}</button>)}
      <span className="mx-0.5 h-4 border-l border-white/20" />
      <span className="px-1 text-white/60">Lớp:</span>
      <button
        type="button"
        onClick={() => handleToggle("gt")}
        aria-pressed={activeLayers.gt}
        className={`rounded px-2 py-1 ${activeLayers.gt ? "bg-blue-600 text-white" : "bg-white/10 text-white/80 hover:bg-white/20"}`}
      >
        GT
      </button>
      <button
        type="button"
        onClick={() => handleToggle("cluster")}
        aria-pressed={activeLayers.cluster}
        className={`rounded px-2 py-1 ${activeLayers.cluster ? "bg-blue-600 text-white" : "bg-white/10 text-white/80 hover:bg-white/20"}`}
      >
        Cụm LiDAR
      </button>
      <button
        type="button"
        onClick={() => handleToggle("pointpillars")}
        aria-pressed={activeLayers.pointpillars}
        className={`rounded px-2 py-1 ${activeLayers.pointpillars ? "bg-blue-600 text-white" : "bg-white/10 text-white/80 hover:bg-white/20"}`}
      >
        PointPillars
      </button>
      <button
        type="button"
        onClick={() => handleToggle("frustums")}
        aria-pressed={activeLayers.frustums}
        className={`rounded px-2 py-1 ${activeLayers.frustums ? "bg-blue-600 text-white" : "bg-white/10 text-white/80 hover:bg-white/20"}`}
      >
        Camera (C)
      </button>
      <button
        type="button"
        onClick={toggleFilterEgo}
        aria-pressed={!filterEgo}
        data-filter-ego={filterEgo ? "on" : "off"}
        className={`rounded px-2 py-1 ${!filterEgo ? "bg-blue-600 text-white" : "bg-white/10 text-white/80 hover:bg-white/20"}`}
        title={filterEgo ? "Hiện điểm thân xe" : "Ẩn điểm thân xe"}
      >
        Điểm thân xe
      </button>
    </div>
    <div className="absolute right-2 top-2 z-10 rounded-md border border-white/10 bg-black/75 px-2 py-1.5 text-[10px] text-white/80 sm:right-3 sm:top-3 sm:text-xs" role={loading ? "status" : undefined} aria-live="polite">
      {activeLoading ? "Đang nạp LiDAR…" : activePointCloud ? `${activePointCloud.count.toLocaleString()} điểm` : "Không có LiDAR"}
    </div>
    <label className={`${mobileControlsOpen ? "flex" : "hidden"} md:flex absolute left-2 top-[5.25rem] z-10 items-center gap-2 rounded-md border border-white/10 bg-black/80 px-2 py-1 text-[10px] text-white/80 sm:left-3 sm:top-[3.75rem] sm:text-xs`}>
      Cỡ điểm
        <input
          aria-label="Kích thước điểm LiDAR"
          type="range"
          min={LIDAR_POINT_STYLE.minSize}
          max={LIDAR_POINT_STYLE.maxSize}
          step={LIDAR_POINT_STYLE.step}
          value={pointSize}
          onChange={(event) => setPointSize(Number(event.target.value))}
          className="w-20 accent-blue-500 sm:w-24"
        />
      <output>{pointSize.toFixed(1)}</output>
    </label>
    <div className="pointer-events-none absolute bottom-2 right-2 z-10 hidden gap-1.5 md:flex sm:bottom-3 sm:right-3 sm:gap-2">
      {([ ["top", "Trên"], ["side", "Bên"], ["front", "Trước"] ] as const).map(([key, title]) => <div key={key} className="relative h-[62px] w-[76px] overflow-hidden rounded border border-white/25 bg-[#080d15]/90 shadow-lg sm:h-[82px] sm:w-[104px]" aria-label={`Góc nhìn ${title}`}>
        <Canvas dpr={1} frameloop="demand"><SceneContents view={key} pointCloud={activePointCloud} colors={colors} pointSize={pointSize} boxes3d={displayBoxes} showBoxes={showBoxes} camPoses={[]} /></Canvas>
        <span className="absolute bottom-0 left-0 right-0 bg-black/75 px-1 py-0.5 text-center text-[9px] text-white/90">{title}</span>
      </div>)}
    </div>
    {(!lidarUrl || activeError) && !activeLoading && <div role={activeError ? "alert" : "status"} className="absolute inset-0 z-[5] flex flex-col items-center justify-center gap-3 bg-black/35 px-4 text-center text-sm text-slate-200">
      <p>{activeError ? `Không tải được LiDAR: ${activeError}` : "Frame này chưa có dữ liệu LiDAR"}</p>
      {activeError && <p className="break-all text-xs">{lidarUrl?.split("/").pop()}</p>}
      {activeError && <button type="button" onClick={() => setRetryVersion((version) => version + 1)} className="rounded bg-blue-600 px-3 py-2 text-xs font-semibold text-white hover:bg-blue-500 focus-visible:outline focus-visible:outline-2 focus-visible:outline-white">Thử lại LiDAR</button>}
    </div>}
  </div>;
}

export default LidarScene;
