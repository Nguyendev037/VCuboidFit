/**
 * Giải mã LiDAR định dạng f16-xyzi từ file .bin nuScenes.
 */

export function decodeFloat16(u16: number): number {
  const sign = (u16 & 0x8000) ? -1 : 1;
  const exponent = (u16 >> 10) & 0x1f;
  const fraction = u16 & 0x03ff;

  if (exponent === 0) {
    if (fraction === 0) return sign * 0;
    // Subnormal number: 2^(-14) * (fraction / 1024)
    return sign * Math.pow(2, -14) * (fraction / 1024);
  } else if (exponent === 31) {
    return fraction === 0 ? sign * Infinity : NaN;
  }
  // Normalized number: 2^(exponent - 15) * (1 + fraction / 1024)
  return sign * Math.pow(2, exponent - 15) * (1 + fraction / 1024);
}

export interface LidarPointCloud {
  count: number;
  /** Tọa độ Three.js: (x, z, -y) */
  threePositions: Float32Array;
  /** Tọa độ nuScenes ego gốc: (x, y, z) */
  rawPositions: Float32Array;
  /** Cường độ phản xạ intensity */
  intensities: Float32Array;
  /** Màu RGB tô theo độ cao [0..1] */
  colors: Float32Array;
  minZ: number;
  maxZ: number;
}

export type LidarColorMode = "height" | "intensity";

export const LIDAR_POINT_STYLE = {
  defaultSize: 1.25,
  minSize: 0.5,
  maxSize: 4,
  step: 0.25,
  mainOpacity: 0.72,
  miniOpacity: 0.58,
  brightness: 0.82,
} as const;

export interface CuboidTransform {
  center: [number, number, number];
  size: [number, number, number];
  yaw: number;
}

/**
 * Ánh xạ giá trị [0..1] sang màu RGB (Turbo / Heatmap).
 */
export function heightToRgb(t: number): [number, number, number] {
  const clamped = Math.max(0, Math.min(1, t));
  // 5 stops: Blue -> Cyan -> Green -> Yellow -> Red
  if (clamped < 0.25) {
    const f = clamped / 0.25;
    return [0.05 + 0.05 * f, 0.2 + 0.6 * f, 0.8 + 0.1 * f];
  } else if (clamped < 0.5) {
    const f = (clamped - 0.25) / 0.25;
    return [0.1 + 0.1 * f, 0.8 + 0.15 * f, 0.9 - 0.6 * f];
  } else if (clamped < 0.75) {
    const f = (clamped - 0.5) / 0.25;
    return [0.2 + 0.75 * f, 0.95 - 0.1 * f, 0.3 - 0.2 * f];
  } else {
    const f = (clamped - 0.75) / 0.25;
    return [0.95, 0.85 - 0.65 * f, 0.1];
  }
}

export function getLidarColors(
  pointCloud: LidarPointCloud,
  mode: LidarColorMode,
): Float32Array {
  const colors = new Float32Array(pointCloud.count * 3);
  const span = Math.max(0.1, pointCloud.maxZ - pointCloud.minZ);
  for (let i = 0; i < pointCloud.count; i++) {
    const value = mode === "height"
      ? (pointCloud.rawPositions[i * 3 + 2] - pointCloud.minZ) / span
      : pointCloud.intensities[i];
    const [r, g, b] = heightToRgb(value);
    colors.set([
      r * LIDAR_POINT_STYLE.brightness,
      g * LIDAR_POINT_STYLE.brightness,
      b * LIDAR_POINT_STYLE.brightness,
    ], i * 3);
  }
  return colors;
}

export function cornersToCuboid(corners: number[]): CuboidTransform | null {
  if (corners.length < 24 || corners.slice(0, 24).some((value) => !Number.isFinite(value))) return null;
  const points = Array.from({ length: 8 }, (_, index) => {
    const x = corners[index * 3];
    const y = corners[index * 3 + 1];
    const z = corners[index * 3 + 2];
    return [x, z, -y] as const;
  });
  const distance = (a: readonly number[], b: readonly number[]) =>
    Math.hypot(a[0] - b[0], a[1] - b[1], a[2] - b[2]);
  const center = points.reduce<[number, number, number]>(
    (sum, point) => [sum[0] + point[0] / 8, sum[1] + point[1] / 8, sum[2] + point[2] / 8],
    [0, 0, 0],
  );
  const edge = [points[1][0] - points[0][0], points[1][2] - points[0][2]];
  return {
    center,
    size: [distance(points[0], points[1]), distance(points[0], points[4]), distance(points[0], points[3])],
    yaw: Math.atan2(edge[1], edge[0]),
  };
}

/** Ego nuScenes (x tiến, y trái, z lên) → Three.js (x, z, -y); cùng ánh xạ với điểm LiDAR và cuboid. */
function egoToThree(x: number, y: number, z: number): [number, number, number] {
  return [x, z, -y || 0];
}

/**
 * Xoay vector v bằng quaternion (w, x, y, z) theo quy ước nuScenes/pyquaternion: v' = q·v·q*.
 * Quaternion được chuẩn hoá; không hữu hạn hoặc chuẩn 0 ⇒ null.
 */
function rotateByQuaternion(
  rotation: readonly number[],
  v: readonly [number, number, number],
): [number, number, number] | null {
  const norm = Math.hypot(rotation[0], rotation[1], rotation[2], rotation[3]);
  if (!Number.isFinite(norm) || norm < 1e-9) return null;
  const [w, x, y, z] = [rotation[0] / norm, rotation[1] / norm, rotation[2] / norm, rotation[3] / norm];
  const [px, py, pz] = v;
  // t = 2·(q_xyz × v); v' = v + w·t + q_xyz × t
  const tx = 2 * (y * pz - z * py);
  const ty = 2 * (z * px - x * pz);
  const tz = 2 * (x * py - y * px);
  return [
    px + w * tx + (y * tz - z * ty),
    py + w * ty + (z * tx - x * tz),
    pz + w * tz + (x * ty - y * tx),
  ];
}

/**
 * Đoạn thẳng (Three.js) của frustum camera: gốc → 4 góc đáy + 4 cạnh đáy.
 * translation/rotation = pose camera→ego của calibrated_sensor nuScenes; hệ camera x phải, y xuống, z tiến.
 */
export function getCameraFrustumLines(
  translation: number[],
  rotation: number[],
  depth = 4,
  halfWidth = 1.7,
  halfHeight = 1,
): Float32Array {
  if (translation.length < 3 || rotation.length < 4) return new Float32Array(0);
  if (!translation.slice(0, 3).every(Number.isFinite)) return new Float32Array(0);
  const [tx, ty, tz] = translation;
  const origin = egoToThree(tx, ty, tz);
  const localCorners: [number, number, number][] = [
    [-halfWidth, -halfHeight, depth], [halfWidth, -halfHeight, depth],
    [halfWidth, halfHeight, depth], [-halfWidth, halfHeight, depth],
  ];
  const corners: [number, number, number][] = [];
  for (const local of localCorners) {
    const rotated = rotateByQuaternion(rotation, local);
    if (!rotated) return new Float32Array(0);
    corners.push(egoToThree(tx + rotated[0], ty + rotated[1], tz + rotated[2]));
  }
  const edges: [number, number][] = [[-1, 0], [-1, 1], [-1, 2], [-1, 3], [0, 1], [1, 2], [2, 3], [3, 0]];
  const output = new Float32Array(edges.length * 6);
  edges.forEach(([from, to], index) => {
    output.set(from < 0 ? origin : corners[from], index * 6);
    output.set(corners[to], index * 6 + 3);
  });
  return output;
}

/**
 * Giải mã buffer nhị phân chứa các điểm float16 [x, y, z, intensity].
 */
export function decodeFloat16Lidar(buffer: ArrayBuffer): LidarPointCloud {
  const u16View = new Uint16Array(buffer);
  const pointCount = Math.floor(u16View.length / 4);

  const threePositions = new Float32Array(pointCount * 3);
  const rawPositions = new Float32Array(pointCount * 3);
  const intensities = new Float32Array(pointCount);
  const colors = new Float32Array(pointCount * 3);

  let minZ = Infinity;
  let maxZ = -Infinity;

  // Bước 1: giải mã tọa độ và tìm min/max Z (độ cao)
  for (let i = 0; i < pointCount; i++) {
    const offset = i * 4;
    const x = decodeFloat16(u16View[offset]);
    const y = decodeFloat16(u16View[offset + 1]);
    const z = decodeFloat16(u16View[offset + 2]);
    const intensity = decodeFloat16(u16View[offset + 3]);

    rawPositions[i * 3] = x;
    rawPositions[i * 3 + 1] = y;
    rawPositions[i * 3 + 2] = z;

    // Chuyển sang hệ Three.js:
    // nuScenes: x = right, y = front, z = up
    // Three.js: X = right, Y = up, Z = -front
    threePositions[i * 3] = x;
    threePositions[i * 3 + 1] = z;
    threePositions[i * 3 + 2] = -y;

    intensities[i] = intensity;

    if (z < minZ) minZ = z;
    if (z > maxZ) maxZ = z;
  }

  if (!Number.isFinite(minZ) || !Number.isFinite(maxZ) || minZ === maxZ) {
    minZ = -2.0;
    maxZ = 3.0;
  }

  // Dải độ cao điển hình trong nuScenes: ~ -2.0m (mặt đường) đến +3.0m
  const span = Math.max(0.1, maxZ - minZ);

  // Bước 2: gán màu theo độ cao
  for (let i = 0; i < pointCount; i++) {
    const z = rawPositions[i * 3 + 2];
    const norm = (z - minZ) / span;
    const [r, g, b] = heightToRgb(norm);
    colors[i * 3] = r * LIDAR_POINT_STYLE.brightness;
    colors[i * 3 + 1] = g * LIDAR_POINT_STYLE.brightness;
    colors[i * 3 + 2] = b * LIDAR_POINT_STYLE.brightness;
  }

  return {
    count: pointCount,
    threePositions,
    rawPositions,
    intensities,
    colors,
    minZ,
    maxZ,
  };
}

/**
 * Chuyển đổi 8 góc (24 float) của box 3D thành 12 cạnh khung dây (Three.js coords).
 * Mỗi cạnh gồm 2 đỉnh = 6 float. 12 cạnh = 72 float.
 */
export function buildBox3dWireframeLines(corners24: number[]): Float32Array {
  if (corners24.length < 24) return new Float32Array(0);

  // nuScenes ego coords -> Three.js: (x, z, -y)
  const pts: [number, number, number][] = [];
  for (let i = 0; i < 8; i++) {
    const x = corners24[i * 3];
    const y = corners24[i * 3 + 1];
    const z = corners24[i * 3 + 2];
    pts.push([x, z, -y]);
  }

  // 12 cạnh:
  // Đáy (0-1-2-3-0)
  // Đỉnh (4-5-6-7-4)
  // Trụ đứng (0-4, 1-5, 2-6, 3-7)
  // + 2 đường chéo mặt trước (0-2 và 1-3)
  const edges: [number, number][] = [
    // Đáy
    [0, 1], [1, 2], [2, 3], [3, 0],
    // Đỉnh
    [4, 5], [5, 6], [6, 7], [7, 4],
    // Cột
    [0, 4], [1, 5], [2, 6], [3, 7],
    // Chéo mặt trước
    [0, 2], [1, 3],
  ];

  const lineCoords = new Float32Array(edges.length * 6);
  let ptr = 0;
  for (const [startIdx, endIdx] of edges) {
    const p1 = pts[startIdx];
    const p2 = pts[endIdx];
    lineCoords[ptr++] = p1[0];
    lineCoords[ptr++] = p1[1];
    lineCoords[ptr++] = p1[2];
    lineCoords[ptr++] = p2[0];
    lineCoords[ptr++] = p2[1];
    lineCoords[ptr++] = p2[2];
  }

  return lineCoords;
}

/**
 * Lấy màu tương ứng cho nhóm category.
 */
export function getCategoryColor(category: string): string {
  const cat = category.toLowerCase();
  if (cat.includes("human") || cat.includes("pedestrian")) {
    return "#facc15";
  }
  if (cat.includes("bicycle") || cat.includes("motorcycle") || cat.includes("cyclist")) {
    return "#fb923c";
  }
  if (cat.includes("vehicle") || cat.includes("car") || cat.includes("truck") || cat.includes("bus")) {
    return "#38bdf8"; // Sky / Cyan
  }
  if (cat.includes("movable_object") || cat.includes("traffic_cone") || cat.includes("barrier")) {
    return "#c084fc"; // Purple
  }
  return "#4ade80"; // Green
}
