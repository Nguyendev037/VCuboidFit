"use client";

/**
 * Các khối 3D của viewer LiDAR (point cloud shader, nền lưới + vòng khoảng cách, xe ego, box, frustum).
 * Tách khỏi LidarScene.tsx để LidarScene chỉ lo trạng thái + overlay UI.
 */
import React, { useEffect, useMemo, useState } from "react";
import { useThree } from "@react-three/fiber";
import { Grid, Html, Line, RoundedBox } from "@react-three/drei";
import * as THREE from "three";
import type { Cam } from "@/lib/api/types";
import { POINTPILLARS_COLOR } from "./ViewerLegend";
import {
  cornersToOrientedBox,
  EGO_VEHICLE_DIMENSIONS,
  egoToThree,
  getCameraFrustumLines,
  getCategoryColor,
  LIDAR_RENDER_STYLE,
  type LidarPointCloud,
} from "./lidarDecoder";

/* ---------------------------------------------------------------- Point cloud (điểm tròn mềm) */

const POINT_VERTEX = /* glsl */ `
uniform float uSize;
uniform float uScale;
uniform float uMinPx;
uniform float uMaxPx;
uniform float uOrtho;
uniform float uFadeNear;
uniform float uFadeFar;
varying vec3 vColor;
varying float vFade;
void main() {
  vec4 mv = modelViewMatrix * vec4(position, 1.0);
  gl_Position = projectionMatrix * mv;
  float dist = max(-mv.z, 0.1);
  float px = uOrtho > 0.5 ? uSize * uMinPx : uSize * max(uMinPx, uScale / dist);
  gl_PointSize = clamp(px, 1.0, uMaxPx);
  float r = length(position.xz);
  vFade = 1.0 - 0.7 * smoothstep(uFadeNear, uFadeFar, r);
  vColor = color;
}`;

const POINT_FRAGMENT = /* glsl */ `
uniform float uOpacity;
varying vec3 vColor;
varying float vFade;
void main() {
  vec2 c = gl_PointCoord - 0.5;
  float d = length(c) * 2.0;
  if (d > 1.0) discard;
  float edge = 1.0 - smoothstep(0.5, 1.0, d);
  vec3 col = vColor * (0.9 + 0.3 * (1.0 - d));
  gl_FragColor = vec4(col * mix(0.55, 1.0, vFade), uOpacity * edge * vFade);
}`;

export function PointCloudMesh({
  pointCloud,
  colors,
  size,
  mini = false,
}: {
  pointCloud: LidarPointCloud;
  colors: Float32Array;
  size: number;
  mini?: boolean;
}) {
  const { camera, size: viewport, gl, invalidate } = useThree();
  const geometry = useMemo(() => {
    const value = new THREE.BufferGeometry();
    value.setAttribute("position", new THREE.BufferAttribute(pointCloud.threePositions, 3));
    value.setAttribute("color", new THREE.BufferAttribute(new Float32Array(pointCloud.count * 3), 3));
    return value;
  }, [pointCloud]);

  const material = useMemo(() => new THREE.ShaderMaterial({
    vertexShader: POINT_VERTEX,
    fragmentShader: POINT_FRAGMENT,
    vertexColors: true,
    transparent: true,
    depthWrite: false,
    uniforms: {
      uSize: { value: 1 },
      uScale: { value: 100 },
      uMinPx: { value: 1.5 },
      uMaxPx: { value: 20 },
      uOrtho: { value: 0 },
      uFadeNear: { value: LIDAR_RENDER_STYLE.fadeNear },
      uFadeFar: { value: LIDAR_RENDER_STYLE.fadeFar },
      uOpacity: { value: LIDAR_RENDER_STYLE.opacity },
    },
  }), []);

  useEffect(() => {
    const color = geometry.getAttribute("color") as THREE.BufferAttribute;
    color.array.set(colors.subarray(0, color.array.length));
    color.needsUpdate = true;
    invalidate();
  }, [colors, geometry, invalidate]);

  useEffect(() => {
    const dpr = gl.getPixelRatio();
    const persp = camera as THREE.PerspectiveCamera;
    const isOrtho = !persp.isPerspectiveCamera;
    const fov = isOrtho ? 50 : persp.fov;
    const projScale = (viewport.height * dpr) / (2 * Math.tan(THREE.MathUtils.degToRad(fov) / 2));
    const u = material.uniforms;
    u.uSize.value = size;
    u.uScale.value = LIDAR_RENDER_STYLE.worldSize * projScale;
    u.uMinPx.value = LIDAR_RENDER_STYLE.minPx * dpr;
    u.uMaxPx.value = LIDAR_RENDER_STYLE.maxPx * dpr;
    u.uOrtho.value = isOrtho ? 1 : 0;
    u.uOpacity.value = mini ? LIDAR_RENDER_STYLE.miniOpacity : LIDAR_RENDER_STYLE.opacity;
    invalidate();
  }, [camera, gl, invalidate, material, mini, size, viewport.height]);

  useEffect(() => () => geometry.dispose(), [geometry]);
  useEffect(() => () => material.dispose(), [material]);

  return <points geometry={geometry} material={material} frustumCulled={false} renderOrder={2} />;
}

/* ---------------------------------------------------------------- Nền: lưới mờ dần + vòng khoảng cách */

const RING_RADII = [10, 20, 30, 40, 50] as const;

function makeLabelTexture(text: string): THREE.CanvasTexture | null {
  if (typeof document === "undefined") return null;
  const canvas = document.createElement("canvas");
  canvas.width = 128;
  canvas.height = 48;
  const ctx = canvas.getContext("2d");
  if (!ctx) return null;
  ctx.font = "600 26px ui-sans-serif, system-ui, -apple-system, 'Segoe UI', sans-serif";
  ctx.textAlign = "center";
  ctx.textBaseline = "middle";
  ctx.fillStyle = "rgba(170, 186, 206, 0.95)";
  ctx.fillText(text, 64, 25);
  const texture = new THREE.CanvasTexture(canvas);
  texture.colorSpace = THREE.SRGBColorSpace;
  texture.anisotropy = 4;
  return texture;
}

function RingLabel({ radius, y }: { radius: number; y: number }) {
  const texture = useMemo(() => makeLabelTexture(`${radius} m`), [radius]);
  useEffect(() => () => texture?.dispose(), [texture]);
  if (!texture) return null;
  // Đặt nhãn ở phía trước-phải xe (+x, -y ego) để không đè lên vùng phía sau camera mặc định.
  const angle = -Math.PI / 6;
  const scale = 1.9 + radius * 0.045;
  return (
    <sprite position={[radius * Math.cos(angle), y + 0.35, -radius * Math.sin(angle)]} scale={[scale, scale * 0.375, 1]} renderOrder={3}>
      <spriteMaterial map={texture} transparent depthWrite={false} depthTest={false} />
    </sprite>
  );
}

function circlePoints(radius: number, segments = 160): [number, number, number][] {
  return Array.from({ length: segments + 1 }, (_, i) => {
    const a = (i / segments) * Math.PI * 2;
    return [Math.cos(a) * radius, 0, Math.sin(a) * radius];
  });
}

export function GroundReference({ groundY, labels = true, grid = true }: { groundY: number; labels?: boolean; grid?: boolean }) {
  const rings = useMemo(() => RING_RADII.map((r) => ({ r, points: circlePoints(r) })), []);
  return (
    <group>
      {grid && (
        <Grid
          position={[0, groundY - 0.03, 0]}
          infiniteGrid
          cellSize={2}
          cellThickness={0.5}
          cellColor="#1f3047"
          sectionSize={10}
          sectionThickness={0.9}
          sectionColor="#2d4a6b"
          fadeDistance={85}
          fadeStrength={2.2}
          fadeFrom={0}
          followCamera={false}
        />
      )}
      <group position={[0, groundY + 0.01, 0]}>
        {rings.map(({ r, points }, index) => (
          <Line
            key={r}
            points={points}
            color={index % 2 === 1 ? "#5b7a99" : "#3f5975"}
            lineWidth={index % 2 === 1 ? 1.2 : 1}
            transparent
            opacity={0.55 - index * 0.06}
            depthWrite={false}
          />
        ))}
      </group>
      {labels && RING_RADII.map((r) => <RingLabel key={r} radius={r} y={groundY} />)}
    </group>
  );
}

/* ---------------------------------------------------------------- Xe ego (mô hình khối) */

function makeGlowTexture(): THREE.CanvasTexture | null {
  if (typeof document === "undefined") return null;
  const canvas = document.createElement("canvas");
  canvas.width = 128;
  canvas.height = 128;
  const ctx = canvas.getContext("2d");
  if (!ctx) return null;
  const gradient = ctx.createRadialGradient(64, 64, 4, 64, 64, 64);
  gradient.addColorStop(0, "rgba(56, 189, 248, 0.45)");
  gradient.addColorStop(0.45, "rgba(56, 189, 248, 0.14)");
  gradient.addColorStop(1, "rgba(56, 189, 248, 0)");
  ctx.fillStyle = gradient;
  ctx.fillRect(0, 0, 128, 128);
  const texture = new THREE.CanvasTexture(canvas);
  texture.colorSpace = THREE.SRGBColorSpace;
  return texture;
}

const CHEVRON = (() => {
  const shape = new THREE.Shape();
  shape.moveTo(0.9, 0);
  shape.lineTo(-0.2, 0.62);
  shape.lineTo(0.12, 0);
  shape.lineTo(-0.2, -0.62);
  shape.closePath();
  return shape;
})();

/** Xe ego dựng từ primitive, đúng EGO_VEHICLE_DIMENSIONS (dài 4.08, rộng 1.73, cao 1.56; tâm x = 1.34). */
export function EgoVehicle({ groundY = 0, detailed = true }: { groundY?: number; detailed?: boolean }) {
  const { length: L, width: W, height: H, centerX, centerY } = EGO_VEHICLE_DIMENSIONS;
  const glow = useMemo(() => (detailed ? makeGlowTexture() : null), [detailed]);
  const chevronGeometry = useMemo(() => new THREE.ShapeGeometry(CHEVRON), []);
  useEffect(() => () => { glow?.dispose(); chevronGeometry.dispose(); }, [chevronGeometry, glow]);
  const [cx, , cz] = egoToThree(centerX, centerY, 0);

  const wheelR = 0.31;
  const wheelW = 0.22;
  const bodyBottom = 0.2;
  const bodyTop = 0.88;
  const bodyH = bodyTop - bodyBottom;
  const cabinH = H - bodyTop + 0.04;
  // Trục sau = gốc ego (x = 0); chiều dài cơ sở Zoe ≈ 2.59 m.
  const rearAxle = -centerX;
  const frontAxle = rearAxle + 2.59;

  return (
    <group position={[cx, groundY, cz]}>
      {glow && (
        <mesh rotation={[-Math.PI / 2, 0, 0]} position={[0, 0.015, 0]} renderOrder={1}>
          <planeGeometry args={[L * 2.2, L * 2.2]} />
          <meshBasicMaterial map={glow} transparent depthWrite={false} />
        </mesh>
      )}
      {/* Thân dưới */}
      <RoundedBox args={[L, bodyH, W]} radius={0.16} smoothness={3} position={[0, bodyBottom + bodyH / 2, 0]}>
        <meshStandardMaterial color="#d6dee8" roughness={0.38} metalness={0.25} />
      </RoundedBox>
      {/* Khoang kính */}
      <RoundedBox args={[L * 0.56, cabinH, W * 0.86]} radius={0.14} smoothness={3} position={[-L * 0.06, bodyTop + cabinH / 2 - 0.04, 0]}>
        <meshStandardMaterial color="#0f1b2b" roughness={0.12} metalness={0.7} />
      </RoundedBox>
      {/* Nóc */}
      <RoundedBox args={[L * 0.44, 0.06, W * 0.78]} radius={0.03} smoothness={2} position={[-L * 0.08, H - 0.03, 0]}>
        <meshStandardMaterial color="#e2e8f0" roughness={0.4} metalness={0.2} />
      </RoundedBox>
      {/* Cảm biến LiDAR trên nóc */}
      <mesh position={[-L * 0.08 + 0.05, H + 0.07, 0]}>
        <cylinderGeometry args={[0.13, 0.15, 0.14, 24]} />
        <meshStandardMaterial color="#1e293b" roughness={0.3} metalness={0.6} emissive="#0ea5e9" emissiveIntensity={0.25} />
      </mesh>
      {/* Bánh xe */}
      {detailed && [frontAxle, rearAxle].flatMap((x) => [1, -1].map((side) => (
        <mesh key={`${x}-${side}`} position={[x, wheelR, side * (W / 2 - wheelW / 2 + 0.02)]} rotation={[Math.PI / 2, 0, 0]}>
          <cylinderGeometry args={[wheelR, wheelR, wheelW, 24]} />
          <meshStandardMaterial color="#111827" roughness={0.8} />
        </mesh>
      )))}
      {/* Đèn pha (trước, +x) và đèn hậu (sau) */}
      {[1, -1].map((side) => (
        <React.Fragment key={side}>
          <mesh position={[L / 2 + 0.005, 0.66, side * W * 0.33]}>
            <boxGeometry args={[0.03, 0.1, 0.36]} />
            <meshBasicMaterial color="#e0f2fe" toneMapped={false} />
          </mesh>
          <mesh position={[-L / 2 - 0.005, 0.7, side * W * 0.34]}>
            <boxGeometry args={[0.03, 0.09, 0.34]} />
            <meshBasicMaterial color="#f43f5e" toneMapped={false} />
          </mesh>
        </React.Fragment>
      ))}
      {/* Mũi tên hướng đi trên mặt đất */}
      <mesh geometry={chevronGeometry} rotation={[-Math.PI / 2, 0, 0]} position={[L / 2 + 0.9, 0.03, 0]} renderOrder={1}>
        <meshBasicMaterial color="#38bdf8" transparent opacity={0.85} depthWrite={false} side={THREE.DoubleSide} />
      </mesh>
    </group>
  );
}

/* ---------------------------------------------------------------- Box 3D */

export type DisplayBox = { category: string; corners: number[]; candidate?: boolean; source?: string };

function boxEdgePoints(l: number, h: number, w: number): [number, number, number][] {
  const x = l / 2;
  const y = h / 2;
  const z = w / 2;
  const c: [number, number, number][] = [
    [x, -y, z], [x, -y, -z], [-x, -y, -z], [-x, -y, z],
    [x, y, z], [x, y, -z], [-x, y, -z], [-x, y, z],
  ];
  const edges: [number, number][] = [
    [0, 1], [1, 2], [2, 3], [3, 0],
    [4, 5], [5, 6], [6, 7], [7, 4],
    [0, 4], [1, 5], [2, 6], [3, 7],
  ];
  const out: [number, number, number][] = edges.flatMap(([a, b]) => [c[a], c[b]]);
  // Vạch "mũi" trên nóc: từ tâm nóc tới giữa cạnh trước ⇒ thấy hướng ngay cả khi nhìn từ trên.
  out.push([0, y, 0], [x, y, 0]);
  return out;
}

function sourceLabel(box: DisplayBox): string {
  if (!box.candidate) return " · GT";
  if (box.source === "pointpillars") return " · PointPillars";
  if (box.source === "merged") return " · Cụm/PP";
  return " · Cụm LiDAR";
}

export function Cuboid({ box, compact = false }: { box: DisplayBox; compact?: boolean }) {
  const [hovered, setHovered] = useState(false);
  const transform = useMemo(() => cornersToOrientedBox(box.corners), [box.corners]);
  const isPP = box.source === "pointpillars";
  const baseColor = isPP ? POINTPILLARS_COLOR : getCategoryColor(box.category);
  const [l, h, w] = transform?.size ?? [1, 1, 1];
  const edgePoints = useMemo(() => boxEdgePoints(l, h, w), [l, h, w]);
  const lineColor = useMemo(
    () => (hovered ? new THREE.Color(baseColor).lerp(new THREE.Color("#ffffff"), 0.45).getStyle() : baseColor),
    [baseColor, hovered],
  );
  if (!transform) return null;

  return (
    <group
      position={transform.center}
      rotation={[0, transform.yaw, 0]}
      onPointerOver={(event) => { event.stopPropagation(); setHovered(true); }}
      onPointerOut={() => setHovered(false)}
    >
      <mesh renderOrder={1}>
        <boxGeometry args={transform.size} />
        <meshStandardMaterial
          color={baseColor}
          emissive={baseColor}
          emissiveIntensity={0.35}
          transparent
          opacity={hovered ? 0.26 : box.candidate ? 0.08 : 0.12}
          depthWrite={false}
          roughness={0.6}
        />
      </mesh>
      {/* Mặt trước sáng hơn ⇒ chỉ hướng heading */}
      <mesh position={[l / 2 + 0.002, 0, 0]} rotation={[0, Math.PI / 2, 0]} renderOrder={1}>
        <planeGeometry args={[w, h]} />
        <meshBasicMaterial color={baseColor} transparent opacity={hovered ? 0.45 : 0.3} depthWrite={false} side={THREE.DoubleSide} />
      </mesh>
      {/* Bóng đáy */}
      <mesh position={[0, -h / 2 + 0.02, 0]} rotation={[-Math.PI / 2, 0, 0]} renderOrder={1}>
        <planeGeometry args={[l, w]} />
        <meshBasicMaterial color={baseColor} transparent opacity={hovered ? 0.3 : 0.16} depthWrite={false} side={THREE.DoubleSide} />
      </mesh>
      <Line
        points={edgePoints}
        segments
        color={lineColor}
        lineWidth={(compact ? 1.2 : 2.2) + (hovered ? 1 : 0)}
        dashed={Boolean(box.candidate)}
        dashSize={0.32}
        gapSize={0.2}
        transparent
        opacity={hovered ? 1 : 0.95}
      />
      {hovered && !compact && (
        <Html position={[0, h / 2 + 0.35, 0]} center zIndexRange={[8, 0]}>
          <span className="whitespace-nowrap rounded-md border border-white/15 bg-slate-950/90 px-2 py-1 text-[11px] font-medium text-white shadow-lg backdrop-blur">
            <span aria-hidden="true" className="mr-1.5 inline-block h-2 w-2 rounded-full align-middle" style={{ backgroundColor: baseColor }} />
            {box.category}
            {sourceLabel(box)}
          </span>
        </Html>
      )}
    </group>
  );
}

export function Boxes3DMesh({ boxes3d, compact = false }: { boxes3d: DisplayBox[]; compact?: boolean }) {
  return (
    <group>
      {boxes3d.map((box, index) => <Cuboid key={`${box.category}-${index}`} box={box} compact={compact} />)}
    </group>
  );
}

/* ---------------------------------------------------------------- Frustum camera */

export type CameraPose = { cam: Cam; translation: number[]; rotation: number[]; intrinsic: number[][] };

export function CameraFrustums({ camPoses, onSelectCam }: { camPoses: CameraPose[]; onSelectCam?: (cam: Cam) => void }) {
  return (
    <group name="camera-frustums" userData={{ isFrustum: true }}>
      {camPoses.map((pose) => <CameraFrustum key={pose.cam} pose={pose} onSelectCam={onSelectCam} />)}
    </group>
  );
}

function CameraFrustum({ pose, onSelectCam }: { pose: CameraPose; onSelectCam?: (cam: Cam) => void }) {
  const points = useMemo(() => {
    const coords = getCameraFrustumLines(pose.translation, pose.rotation);
    const out: [number, number, number][] = [];
    for (let i = 0; i + 2 < coords.length; i += 3) out.push([coords[i], coords[i + 1], coords[i + 2]]);
    return out;
  }, [pose]);
  const [hovered, setHovered] = useState(false);
  if (points.length < 2) return null;
  return (
    <group>
      <Line points={points} segments color={hovered ? "#bae6fd" : "#60a5fa"} lineWidth={hovered ? 2 : 1.3} transparent opacity={0.8} />
      <mesh
        position={egoToThree(pose.translation[0], pose.translation[1], pose.translation[2])}
        onClick={(event) => { event.stopPropagation(); onSelectCam?.(pose.cam); }}
        onPointerOver={(event) => { event.stopPropagation(); setHovered(true); }}
        onPointerOut={() => setHovered(false)}
      >
        <sphereGeometry args={[0.18, 16, 16]} />
        <meshBasicMaterial color={hovered ? "#e0f2fe" : "#60a5fa"} />
      </mesh>
    </group>
  );
}
