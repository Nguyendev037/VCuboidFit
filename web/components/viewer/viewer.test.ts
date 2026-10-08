import { describe, it, expect, vi } from "vitest";
import * as THREE from "three";
import {
  decodeFloat16,
  decodeFloat16Lidar,
  buildBox3dWireframeLines,
  getCategoryColor,
  getLidarColors,
  LIDAR_POINT_STYLE,
  getCameraFrustumLines,
  cornersToCuboid,
} from "./lidarDecoder";
import {
  groupCamerasByPosition,
  handleViewerKeyDown,
  type ViewerActions,
} from "./viewerUtils";
import type { Cam, CamDetail } from "@/lib/api/types";
import { getCamCompactName, getCamFriendlyName } from "./CameraImage";

describe("LiDAR Float16 Decoder", () => {
  it("shortens surround camera labels for narrow mobile tiles", () => {
    expect(getCamCompactName("CAM_FRONT_LEFT")).toBe("Front L");
    expect(getCamCompactName("CAM_BACK_RIGHT")).toBe("Back R");
    expect(getCamFriendlyName("CAM_FRONT_LEFT")).toBe("Front Left");
  });

  it("tô màu intensity bằng thuộc tính màu mới, không sửa vị trí điểm", () => {
    const pointCloud = {
      count: 2,
      threePositions: new Float32Array([1, 2, 3, 4, 5, 6]),
      rawPositions: new Float32Array([0, 0, -1, 0, 0, 1]),
      intensities: new Float32Array([0, 1]),
      colors: new Float32Array(6),
      minZ: -1,
      maxZ: 1,
    };

    const colors = getLidarColors(pointCloud, "intensity");
    expect(colors).toHaveLength(6);
    expect(colors[0]).toBeCloseTo(0.05 * LIDAR_POINT_STYLE.brightness);
    expect(colors[1]).toBeCloseTo(0.2 * LIDAR_POINT_STYLE.brightness);
    expect(colors[2]).toBeCloseTo(0.8 * LIDAR_POINT_STYLE.brightness);
    expect(colors[3]).toBeCloseTo(0.95 * LIDAR_POINT_STYLE.brightness);
    expect(colors[4]).toBeCloseTo(0.2 * LIDAR_POINT_STYLE.brightness);
    expect(colors[5]).toBeCloseTo(0.1 * LIDAR_POINT_STYLE.brightness);
    expect(pointCloud.threePositions).toEqual(new Float32Array([1, 2, 3, 4, 5, 6]));
  });

  it("giữ mặc định điểm LiDAR mảnh hơn ảnh evidence cũ", () => {
    expect(LIDAR_POINT_STYLE.defaultSize).toBeLessThan(2);
    expect(LIDAR_POINT_STYLE.mainOpacity).toBeLessThan(0.8);
    expect(LIDAR_POINT_STYLE.brightness).toBeLessThan(0.9);
    expect(LIDAR_POINT_STYLE.maxSize).toBeLessThanOrEqual(4);
  });

  it("ánh xạ hai đầu dải độ cao sang hai màu điểm khác nhau", () => {
    const pointCloud = {
      count: 2,
      threePositions: new Float32Array(6),
      rawPositions: new Float32Array([0, 0, -2, 0, 0, 3]),
      intensities: new Float32Array(2),
      colors: new Float32Array(6),
      minZ: -2,
      maxZ: 3,
    };
    const colors = getLidarColors(pointCloud, "height");
    expect(colors[2]).toBeCloseTo(0.8 * LIDAR_POINT_STYLE.brightness);
    expect(colors[3]).toBeCloseTo(0.95 * LIDAR_POINT_STYLE.brightness);
    expect(colors[4]).toBeCloseTo(0.2 * LIDAR_POINT_STYLE.brightness);
  });

  it("chuyển 8 góc cuboid sang tâm, kích thước và hướng trong hệ Three.js", () => {
    const corners = [
      1, 1, 0, 1, -1, 0, -1, -1, 0, -1, 1, 0,
      1, 1, 2, 1, -1, 2, -1, -1, 2, -1, 1, 2,
    ];
    expect(cornersToCuboid(corners)).toEqual({
      center: [0, 1, 0],
      size: [2, 2, 2],
      yaw: Math.PI / 2,
    });
    expect(cornersToCuboid([0, 1])).toBeNull();
  });

  it("tạo frustum hữu hạn từ translation và quaternion camera", () => {
    const lines = getCameraFrustumLines([1, 0, 2], [1, 0, 0, 0]);
    expect(lines).toHaveLength(48);
    expect(Array.from(lines.slice(0, 3))).toEqual([1, 2, 0]);
    expect(Array.from(lines).every(Number.isFinite)).toBe(true);
  });

  // Hồi quy: phép xoay quaternion sai làm 6 frustum toả lên trời, méo (pose đơn vị không bắt được).
  describe("frustum với pose camera THẬT nuScenes v1.0-mini", () => {
    // calibrated_sensor đầu tiên của mỗi kênh camera (sensor.json ↔ calibrated_sensor.json);
    // camera→ego, rotation (w, x, y, z); hệ camera: x phải, y xuống, z tiến.
    type NuscCamPose = { cam: string; translation: number[]; rotation: number[]; dir: [number, number] };
    const NUSC_MINI_CAM_POSES: NuscCamPose[] = [
      { cam: "CAM_FRONT", translation: [1.70079118954, 0.0159456324149, 1.51095763913],
        rotation: [0.4998015430569128, -0.5030316162024876, 0.4997798114386805, -0.49737083824542755], dir: [1, 0] },
      { cam: "CAM_FRONT_RIGHT", translation: [1.5508477543, -0.493404796419, 1.49574800619],
        rotation: [0.2060347966337182, -0.2026940577919598, 0.6824507824531167, -0.6713610884174485], dir: [1, -1] },
      { cam: "CAM_BACK_RIGHT", translation: [1.0148780988, -0.480568219723, 1.56239545128],
        rotation: [0.12280980120078765, -0.132400842670559, -0.7004305821388234, 0.690496031265798], dir: [-1, -1] },
      { cam: "CAM_BACK", translation: [0.0283260309358, 0.00345136761476, 1.57910346144],
        rotation: [0.5037872666382278, -0.49740249788611096, -0.4941850223835201, 0.5045496097725578], dir: [-1, 0] },
      { cam: "CAM_BACK_LEFT", translation: [1.03569100218, 0.484795032713, 1.59097014818],
        rotation: [0.6924185592174665, -0.7031619420114925, -0.11648342771943819, 0.11203317912370753], dir: [-1, 1] },
      { cam: "CAM_FRONT_LEFT", translation: [1.52387798135, 0.494631336551, 1.50932822144],
        rotation: [0.6757265034669446, -0.6736266522251881, 0.21214015046209478, -0.21122827103904068], dir: [1, 1] },
    ];
    const DEPTH = 4;
    const HALF_W = 1.7;
    const HALF_H = 1;
    const egoToThree = ([x, y, z]: readonly number[]) => [x, z, -y];
    const parts = (lines: Float32Array) => {
      // 4 đoạn đầu = gốc camera → góc đáy i
      const origin = Array.from(lines.slice(0, 3));
      const corners = [0, 1, 2, 3].map((i) => Array.from(lines.slice(i * 6 + 3, i * 6 + 6)));
      const base = [0, 1, 2].map((k) => corners.reduce((sum, corner) => sum + corner[k], 0) / 4);
      return { origin, corners, base };
    };

    it.each(NUSC_MINI_CAM_POSES)("$cam: chĩa ngang, đúng hướng, ra xa xe", ({ cam, translation, rotation, dir }) => {
      const { origin, base } = parts(getCameraFrustumLines(translation, rotation));
      const [threeTx, threeTy, threeTz] = egoToThree(translation);
      expect(origin[0]).toBeCloseTo(threeTx, 5);
      expect(origin[1]).toBeCloseTo(threeTy, 5);
      expect(origin[2]).toBeCloseTo(threeTz, 5);
      const d = [base[0] - origin[0], base[1] - origin[1], base[2] - origin[2]];
      expect(Math.hypot(...d)).toBeCloseTo(DEPTH, 3);
      // gần mặt phẳng ngang: tâm đáy chênh độ cao với camera < 0.5 m
      expect(Math.abs(d[1])).toBeLessThan(0.5);
      // hướng trong hệ ego: x = three.x, y = -three.z
      const [egoDx, egoDy] = [d[0], -d[2]];
      if (dir[0] !== 0) expect(Math.sign(egoDx)).toBe(dir[0]);
      if (dir[1] !== 0) expect(Math.sign(egoDy)).toBe(dir[1]);
      if (cam === "CAM_FRONT") expect(egoDx).toBeGreaterThan(0.95 * DEPTH);
      if (cam === "CAM_BACK") expect(egoDx).toBeLessThan(-0.95 * DEPTH);
      // ra xa xe: tâm đáy xa gốc ego hơn camera
      expect(Math.hypot(...base)).toBeGreaterThan(Math.hypot(...origin));
    });

    it.each(NUSC_MINI_CAM_POSES)("$cam: góc đáy khớp three.js applyQuaternion, khung ảnh không lật", ({ translation, rotation }) => {
      const [w, x, y, z] = rotation;
      const q = new THREE.Quaternion(x, y, z, w).normalize();
      const { corners } = parts(getCameraFrustumLines(translation, rotation));
      const local = [[-HALF_W, -HALF_H, DEPTH], [HALF_W, -HALF_H, DEPTH], [HALF_W, HALF_H, DEPTH], [-HALF_W, HALF_H, DEPTH]];
      local.forEach(([px, py, pz], i) => {
        const v = new THREE.Vector3(px, py, pz).applyQuaternion(q);
        const expected = egoToThree([v.x + translation[0], v.y + translation[1], v.z + translation[2]]);
        expected.forEach((value, k) => expect(corners[i][k]).toBeCloseTo(value, 4));
      });
      // y camera hướng xuống ⇒ 2 góc mép trên (py = -halfH) cao hơn 2 góc mép dưới
      expect(Math.min(corners[0][1], corners[1][1])).toBeGreaterThan(Math.max(corners[2][1], corners[3][1]) + HALF_H);
    });

    it("chuẩn hoá quaternion không đơn vị; quaternion hỏng ⇒ không vẽ", () => {
      const { translation, rotation } = NUSC_MINI_CAM_POSES[0];
      const unit = getCameraFrustumLines(translation, rotation);
      const scaled = getCameraFrustumLines(translation, rotation.map((v) => v * 2));
      Array.from(unit).forEach((value, i) => expect(scaled[i]).toBeCloseTo(value, 4));
      expect(getCameraFrustumLines(translation, [0, 0, 0, 0])).toHaveLength(0);
      expect(getCameraFrustumLines(translation, [Number.NaN, 0, 0, 0])).toHaveLength(0);
    });
  });

  it("giải mã float16 chuẩn xác cho các số đặc biệt và thông thường", () => {
    // 0.0 -> 0x0000
    expect(decodeFloat16(0x0000)).toBe(0);
    // -0.0 -> 0x8000
    expect(Object.is(decodeFloat16(0x8000), -0)).toBe(true);

    // 1.0 -> sign=0, exp=15 (01111), frac=0 -> 0x3c00
    expect(decodeFloat16(0x3c00)).toBe(1.0);

    // -2.0 -> sign=1, exp=16 (10000), frac=0 -> 0xc000
    expect(decodeFloat16(0xc000)).toBe(-2.0);

    // 1.5 -> sign=0, exp=15 (01111), frac=1024/2=512 -> 0x3e00
    expect(decodeFloat16(0x3e00)).toBe(1.5);

    // Infinity: 0x7c00
    expect(decodeFloat16(0x7c00)).toBe(Infinity);
    // -Infinity: 0xfc00
    expect(decodeFloat16(0xfc00)).toBe(-Infinity);

    // NaN: 0x7c01
    expect(Number.isNaN(decodeFloat16(0x7c01))).toBe(true);

    // Subnormal number: exp=0, frac=1 -> 2^(-14) * (1/1024) = 2^(-24)
    const subnormal = decodeFloat16(0x0001);
    expect(subnormal).toBeCloseTo(Math.pow(2, -24), 10);
  });

  it("giải mã buffer LiDAR nhị phân f16-xyzi và chuyển đổi sang Three.js", () => {
    // Tạo buffer mô phỏng 2 điểm LiDAR (mỗi điểm 4 số float16 = 8 bytes)
    const buffer = new ArrayBuffer(16);
    const u16View = new Uint16Array(buffer);

    // Điểm 1: x = 1.0, y = 2.0, z = 0.5, i = 1.0
    // 1.0 = 0x3c00, 2.0 = 0x4000, 0.5 = 0x3800, i = 0x3c00
    u16View[0] = 0x3c00;
    u16View[1] = 0x4000;
    u16View[2] = 0x3800;
    u16View[3] = 0x3c00;

    // Điểm 2: x = -1.0, y = 3.0, z = -0.5, i = 0.5
    // -1.0 = 0xbc00, 3.0 = 0x4200, -0.5 = 0xb800, i = 0x3800
    u16View[4] = 0xbc00;
    u16View[5] = 0x4200;
    u16View[6] = 0xb800;
    u16View[7] = 0x3800;

    const cloud = decodeFloat16Lidar(buffer);

    expect(cloud.count).toBe(2);

    // Điểm 1 tọa độ thô: (1.0, 2.0, 0.5)
    expect(cloud.rawPositions[0]).toBeCloseTo(1.0);
    expect(cloud.rawPositions[1]).toBeCloseTo(2.0);
    expect(cloud.rawPositions[2]).toBeCloseTo(0.5);

    // Điểm 1 tọa độ Three.js: X = x, Y = z (độ cao), Z = -y
    expect(cloud.threePositions[0]).toBeCloseTo(1.0);
    expect(cloud.threePositions[1]).toBeCloseTo(0.5);
    expect(cloud.threePositions[2]).toBeCloseTo(-2.0);

    // Điểm 2 tọa độ Three.js: X = -1.0, Y = -0.5, Z = -3.0
    expect(cloud.threePositions[3]).toBeCloseTo(-1.0);
    expect(cloud.threePositions[4]).toBeCloseTo(-0.5);
    expect(cloud.threePositions[5]).toBeCloseTo(-3.0);

    // Cường độ phản xạ
    expect(cloud.intensities[0]).toBeCloseTo(1.0);
    expect(cloud.intensities[1]).toBeCloseTo(0.5);

    // Min/Max Z
    expect(cloud.minZ).toBeCloseTo(-0.5);
    expect(cloud.maxZ).toBeCloseTo(0.5);

    // Màu tô theo độ cao có 3 kênh RGB cho mỗi điểm
    expect(cloud.colors.length).toBe(6);
  });

  it("xây dựng khung dây 3D wireframe box từ 8 góc", () => {
    // 8 góc giả định (24 số)
    const corners = [
      1, 1, 0,  1, -1, 0,  -1, -1, 0,  -1, 1, 0, // Đáy (0-3)
      1, 1, 2,  1, -1, 2,  -1, -1, 2,  -1, 1, 2, // Đỉnh (4-7)
    ];

    const lines = buildBox3dWireframeLines(corners);
    // 14 cạnh (12 cạnh hộp + 2 chéo mặt trước), mỗi cạnh 2 đỉnh = 6 float -> 14 * 6 = 84 floats
    expect(lines.length).toBe(14 * 6);
  });

  it("phân loại màu sắc theo danh mục đối tượng đúng chuẩn", () => {
    expect(getCategoryColor("vehicle.car")).toBe("#38bdf8");
    expect(getCategoryColor("human.pedestrian.adult")).toBe("#facc15");
    expect(getCategoryColor("vehicle.motorcycle")).toBe("#fb923c");
    expect(getCategoryColor("movable_object.trafficcone")).toBe("#c084fc");
  });
});

describe("Camera Layout & Missing Camera Handling", () => {
  const makeMockCam = (cam: string): CamDetail =>
    ({
      cam: cam as Cam,
      imageUrl: `/mock/${cam}.jpg`,
      width: 800,
      height: 450,
      boxes: [],
      score: { nov: 0.5, unc: 0.5, qry: 0.5, s: 0.5 },
      qOk: true,
    } as CamDetail);

  it("phân chia đúng 3 camera trước và 3 camera sau khi đủ 6 camera", () => {
    const cams = [
      makeMockCam("CAM_FRONT_LEFT"),
      makeMockCam("CAM_FRONT"),
      makeMockCam("CAM_FRONT_RIGHT"),
      makeMockCam("CAM_BACK_LEFT"),
      makeMockCam("CAM_BACK"),
      makeMockCam("CAM_BACK_RIGHT"),
    ];

    const groups = groupCamerasByPosition(cams);
    expect(groups.front.length).toBe(3);
    expect(groups.back.length).toBe(3);
    expect(groups.front.map((c) => c.cam)).toEqual([
      "CAM_FRONT_LEFT",
      "CAM_FRONT",
      "CAM_FRONT_RIGHT",
    ]);
    expect(groups.back.map((c) => c.cam)).toEqual([
      "CAM_BACK_LEFT",
      "CAM_BACK",
      "CAM_BACK_RIGHT",
    ]);
  });

  it("tự động ẩn ô camera bị thiếu (ví dụ CAM_BACK hoặc CAM_FRONT_RIGHT)", () => {
    // Giả lập frame thiếu CAM_BACK (chỉ còn 5 camera như trong mock-f03)
    const camsWithoutBack = [
      makeMockCam("CAM_FRONT_LEFT"),
      makeMockCam("CAM_FRONT"),
      makeMockCam("CAM_FRONT_RIGHT"),
      makeMockCam("CAM_BACK_LEFT"),
      makeMockCam("CAM_BACK_RIGHT"),
    ];

    const groups1 = groupCamerasByPosition(camsWithoutBack);
    expect(groups1.front.length).toBe(3);
    expect(groups1.back.length).toBe(2);
    expect(groups1.back.map((c) => c.cam)).toEqual([
      "CAM_BACK_LEFT",
      "CAM_BACK_RIGHT",
    ]);

    // Giả lập frame thiếu cả CAM_FRONT_LEFT và CAM_BACK
    const camsPartial = [
      makeMockCam("CAM_FRONT"),
      makeMockCam("CAM_FRONT_RIGHT"),
      makeMockCam("CAM_BACK_LEFT"),
      makeMockCam("CAM_BACK_RIGHT"),
    ];

    const groups2 = groupCamerasByPosition(camsPartial);
    expect(groups2.front.length).toBe(2);
    expect(groups2.back.length).toBe(2);
    expect(groups2.front.map((c) => c.cam)).toEqual([
      "CAM_FRONT",
      "CAM_FRONT_RIGHT",
    ]);
  });
});

describe("Keyboard Shortcuts & Navigation", () => {
  it("gọi đúng callbacks khi nhấn các phím spec §5.4: ←/→, Esc, 0, 1–6, 7/L, B, P, I, R", () => {
    const actions: ViewerActions = {
      onPrev: vi.fn(),
      onNext: vi.fn(),
      onClose: vi.fn(),
      setMode: vi.fn(),
      setFocusTarget: vi.fn(),
      toggleBoxes: vi.fn(),
      toggleLidarOverlay: vi.fn(),
      toggleInfoPanel: vi.fn(),
      reset3dView: vi.fn(),
    };

    const press = (key: string) => {
      const preventDefault = vi.fn();
      const handled = handleViewerKeyDown({ key, preventDefault }, actions);
      return { handled, preventDefault };
    };

    // ← Chuyển frame trước
    expect(press("ArrowLeft").handled).toBe(true);
    expect(actions.onPrev).toHaveBeenCalledTimes(1);

    // → Chuyển frame kế tiếp
    expect(press("ArrowRight").handled).toBe(true);
    expect(actions.onNext).toHaveBeenCalledTimes(1);

    // Esc Đóng
    expect(press("Escape").handled).toBe(true);
    expect(actions.onClose).toHaveBeenCalledTimes(1);

    // 0 Chế độ Surround
    expect(press("0").handled).toBe(true);
    expect(actions.setMode).toHaveBeenCalledWith("surround");

    // 1-6 Focus các camera
    expect(press("1").handled).toBe(true);
    expect(actions.setMode).toHaveBeenCalledWith("focus");
    expect(actions.setFocusTarget).toHaveBeenCalledWith("CAM_FRONT_LEFT");

    expect(press("2").handled).toBe(true);
    expect(actions.setFocusTarget).toHaveBeenCalledWith("CAM_FRONT");

    expect(press("3").handled).toBe(true);
    expect(actions.setFocusTarget).toHaveBeenCalledWith("CAM_FRONT_RIGHT");

    expect(press("4").handled).toBe(true);
    expect(actions.setFocusTarget).toHaveBeenCalledWith("CAM_BACK_LEFT");

    expect(press("5").handled).toBe(true);
    expect(actions.setFocusTarget).toHaveBeenCalledWith("CAM_BACK");

    expect(press("6").handled).toBe(true);
    expect(actions.setFocusTarget).toHaveBeenCalledWith("CAM_BACK_RIGHT");

    // 7 hoặc L: Focus LiDAR
    expect(press("7").handled).toBe(true);
    expect(actions.setFocusTarget).toHaveBeenCalledWith("lidar");

    expect(press("l").handled).toBe(true);
    expect(actions.setFocusTarget).toHaveBeenCalledWith("lidar");

    expect(press("L").handled).toBe(true);
    expect(actions.setFocusTarget).toHaveBeenCalledWith("lidar");

    // B: bật/tắt hộp 3D
    expect(press("b").handled).toBe(true);
    expect(actions.toggleBoxes).toHaveBeenCalledTimes(1);

    // P: bật/tắt LiDAR overlay trên ảnh
    expect(press("p").handled).toBe(true);
    expect(actions.toggleLidarOverlay).toHaveBeenCalledTimes(1);

    // I: bật/tắt info panel
    expect(press("i").handled).toBe(true);
    expect(actions.toggleInfoPanel).toHaveBeenCalledTimes(1);

    // R: đặt lại góc nhìn 3D
    expect(press("r").handled).toBe(true);
    expect(actions.reset3dView).toHaveBeenCalledTimes(1);

    // Phím khác không xử lý
    expect(press("x").handled).toBe(false);
  });
});
