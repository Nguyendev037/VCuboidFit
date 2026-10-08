"use client";

import React, { useEffect, useMemo, useRef, useState } from "react";
import { Canvas, useThree } from "@react-three/fiber";
import { Html, OrbitControls, OrthographicCamera, PerspectiveCamera } from "@react-three/drei";
import * as THREE from "three";
import type { OrbitControls as OrbitControlsImpl } from "three-stdlib";
import type { Cam } from "@/lib/api/types";
import {
  cornersToCuboid,
  decodeFloat16Lidar,
  getCameraFrustumLines,
  getCategoryColor,
  getLidarColors,
  LIDAR_POINT_STYLE,
  type LidarColorMode,
  type LidarPointCloud,
} from "./lidarDecoder";

type Box3D = { category: string; corners: number[] };
type CameraPose = { cam: Cam; translation: number[]; rotation: number[]; intrinsic: number[][] };
type ViewMode = "free" | "top" | "rear";
type SceneView = "main" | "top" | "side" | "front";

export interface LidarSceneProps {
  lidarUrl?: string | null;
  boxes3d?: Box3D[];
  camPoses?: CameraPose[];
  showBoxes?: boolean;
  onSelectCam?: (cam: Cam) => void;
  resetTrigger?: number;
  className?: string;
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
      camera.position.set(16, 20, 22);
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
  return (
    <group
      position={transform.center}
      rotation={[0, transform.yaw, 0]}
      onPointerOver={(event) => { event.stopPropagation(); setHovered(true); }}
      onPointerOut={() => setHovered(false)}
    >
      <mesh>
        <boxGeometry args={transform.size} />
        <meshBasicMaterial color={color} transparent opacity={hovered ? 0.14 : 0.045} depthWrite={false} />
      </mesh>
      <lineSegments geometry={geometry}>
        <lineBasicMaterial color={hovered ? "#ffffff" : color} transparent opacity={hovered ? 1 : 0.9} linewidth={2} />
      </lineSegments>
      {hovered && <Html position={[0, transform.size[1] / 2 + 0.25, 0]} center distanceFactor={18}>
        <span className="whitespace-nowrap rounded border border-white/20 bg-black/90 px-2 py-1 text-[11px] font-medium text-white shadow">{box.category}</span>
      </Html>}
    </group>
  );
}

function EgoVehicle() {
  const geometry = useMemo(() => {
    const w = 0.95; const h = 1.6; const l = 2.25;
    const coords = [
      -w, 0.2, -l, w, 0.2, -l, w, 0.2, -l, w, 0.2, l,
      w, 0.2, l, -w, 0.2, l, -w, 0.2, l, -w, 0.2, -l,
      -w, h, -l, w, h, -l, w, h, -l, w, h, l,
      w, h, l, -w, h, l, -w, h, l, -w, h, -l,
      -w, 0.2, -l, -w, h, -l, w, 0.2, -l, w, h, -l,
      w, 0.2, l, w, h, l, -w, 0.2, l, -w, h, l,
      0, 0.3, -l, 0, 0.3, -l - 1.2, -0.4, 0.3, -l - 0.7, 0, 0.3, -l - 1.2,
      0.4, 0.3, -l - 0.7, 0, 0.3, -l - 1.2,
    ];
    return new THREE.BufferGeometry().setAttribute("position", new THREE.Float32BufferAttribute(coords, 3));
  }, []);
  useEffect(() => () => geometry.dispose(), [geometry]);
  return <lineSegments geometry={geometry}><lineBasicMaterial color="#38bdf8" /></lineSegments>;
}

function CameraFrustums({ camPoses, onSelectCam }: { camPoses: CameraPose[]; onSelectCam?: (cam: Cam) => void }) {
  return <group>{camPoses.map((pose) => <CameraFrustum key={pose.cam} pose={pose} onSelectCam={onSelectCam} />)}</group>;
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
  onSelectCam?: (cam: Cam) => void;
  viewMode?: ViewMode;
  resetTrigger?: number;
}) {
  return <>
    <color attach="background" args={["#080d15"]} />
    <ambientLight intensity={0.85} />
    <directionalLight position={[10, 18, 12]} intensity={0.65} />
    {view === "main" ? <>
      <PerspectiveCamera makeDefault fov={50} near={0.1} far={500} position={[16, 20, 22]} />
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
    {view === "main" && <CameraFrustums camPoses={camPoses} onSelectCam={onSelectCam} />}
  </>;
}

export function LidarScene({
  lidarUrl,
  boxes3d = [],
  camPoses = [],
  showBoxes = true,
  onSelectCam,
  resetTrigger = 0,
  className = "",
}: LidarSceneProps) {
  const [pointCloud, setPointCloud] = useState<LidarPointCloud | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [retryVersion, setRetryVersion] = useState(0);
  const [viewMode, setViewMode] = useState<ViewMode>("free");
  const [colorMode, setColorMode] = useState<LidarColorMode>("height");
  const [pointSize, setPointSize] = useState<number>(LIDAR_POINT_STYLE.defaultSize);
  const [cameraReset, setCameraReset] = useState(0);
  const colors = useMemo(() => pointCloud ? getLidarColors(pointCloud, colorMode) : null, [colorMode, pointCloud]);
  const activePointCloud = lidarUrl ? pointCloud : null;
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

  return <div className={`relative isolate h-full min-h-[220px] overflow-hidden rounded-lg bg-[#080d15] text-white ${className}`} data-testid="lidar-scene">
    <Canvas dpr={[1, 1.5]} gl={{ antialias: true, powerPreference: "high-performance" }} className="absolute inset-0">
      <SceneContents view="main" pointCloud={activePointCloud} colors={colors} pointSize={pointSize} boxes3d={boxes3d} showBoxes={showBoxes} camPoses={camPoses} onSelectCam={onSelectCam} viewMode={viewMode} resetTrigger={resetTrigger + cameraReset} />
    </Canvas>

    <div className="absolute left-2 top-2 z-10 flex max-w-[calc(100%-8rem)] flex-wrap items-center gap-1 rounded-md border border-white/10 bg-black/75 p-1.5 text-[10px] sm:left-3 sm:top-3 sm:gap-1.5 sm:p-2 sm:text-xs">
      <span className="px-1 text-white/60">Góc:</span>
      {([ ["free", "Tự do"], ["top", "Trên"], ["rear", "Sau"] ] as const).map(([mode, label]) => <button key={mode} type="button" onClick={() => setViewMode(mode)} aria-pressed={viewMode === mode} className={`rounded px-2 py-1 ${viewMode === mode ? "bg-blue-600 text-white" : "bg-white/10 text-white/80 hover:bg-white/20"}`}>{label}</button>)}
      <button type="button" aria-label="Đặt lại góc nhìn LiDAR" title="Đặt lại camera" onClick={() => { setViewMode("free"); setCameraReset((value) => value + 1); }} className="rounded bg-white/10 px-2 py-1 hover:bg-white/20">Đặt lại</button>
      <span className="mx-0.5 h-4 border-l border-white/20" />
      {([ ["height", "Độ cao"], ["intensity", "Intensity"] ] as const).map(([mode, label]) => <button key={mode} type="button" onClick={() => setColorMode(mode)} aria-pressed={colorMode === mode} className={`rounded px-2 py-1 ${colorMode === mode ? "bg-blue-600 text-white" : "bg-white/10 text-white/80 hover:bg-white/20"}`}>{label}</button>)}
    </div>
    <div className="absolute right-2 top-2 z-10 rounded-md border border-white/10 bg-black/75 px-2 py-1.5 text-[10px] text-white/80 sm:right-3 sm:top-3 sm:text-xs" role={loading ? "status" : undefined} aria-live="polite">
      {activeLoading ? "Đang nạp LiDAR…" : activePointCloud ? `${activePointCloud.count.toLocaleString()} điểm` : "Không có LiDAR"}
    </div>
    <label className="absolute left-2 top-[5.25rem] z-10 flex items-center gap-2 rounded-md border border-white/10 bg-black/70 px-2 py-1 text-[10px] text-white/80 sm:left-3 sm:top-[3.75rem] sm:text-xs">
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
    <div className="pointer-events-none absolute bottom-2 right-2 z-10 flex gap-1.5 sm:bottom-3 sm:right-3 sm:gap-2">
      {([ ["top", "Trên"], ["side", "Bên"], ["front", "Trước"] ] as const).map(([key, title]) => <div key={key} className="relative h-[62px] w-[76px] overflow-hidden rounded border border-white/25 bg-[#080d15]/90 shadow-lg sm:h-[82px] sm:w-[104px]" aria-label={`Góc nhìn ${title}`}>
        <Canvas dpr={1} frameloop="demand"><SceneContents view={key} pointCloud={activePointCloud} colors={colors} pointSize={pointSize} boxes3d={boxes3d} showBoxes={showBoxes} camPoses={[]} /></Canvas>
        <span className="absolute bottom-0 left-0 right-0 bg-black/75 px-1 py-0.5 text-center text-[9px] text-white/90">{title}</span>
      </div>)}
    </div>
    {(!lidarUrl || activeError) && !activeLoading && <div role={activeError ? "alert" : "status"} className="absolute inset-0 z-[5] flex flex-col items-center justify-center gap-3 bg-black/35 px-4 text-center text-sm text-slate-200">
      <p>{activeError ? `Không tải được LiDAR: ${activeError}` : "Frame này chưa có dữ liệu LiDAR"}</p>
      {activeError && <button type="button" onClick={() => setRetryVersion((version) => version + 1)} className="rounded bg-blue-600 px-3 py-2 text-xs font-semibold text-white hover:bg-blue-500 focus-visible:outline focus-visible:outline-2 focus-visible:outline-white">Thử lại LiDAR</button>}
    </div>}
  </div>;
}

export default LidarScene;
