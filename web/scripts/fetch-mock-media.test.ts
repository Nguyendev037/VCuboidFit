import { spawnSync } from "node:child_process";
import { existsSync, mkdtempSync, readFileSync, readdirSync, rmSync, statSync } from "node:fs";
import { tmpdir } from "node:os";
import path from "node:path";
import { afterAll, describe, expect, it } from "vitest";

import sharp from "sharp";

import { LIDAR_POINTS, f32ToF16Bits, pcdToF16, syntheticCloud } from "./fetch-mock-media.mjs";

const SCRIPT = path.resolve(__dirname, "fetch-mock-media.mjs");
const tmp: string[] = [];
afterAll(() => tmp.forEach((d) => rmSync(d, { recursive: true, force: true })));

function f16ToF32(h: number): number {
  const s = h & 0x8000 ? -1 : 1;
  const e = (h >> 10) & 0x1f;
  const m = h & 0x3ff;
  if (e === 0) return s * m * 2 ** -24;
  if (e === 0x1f) return m ? NaN : s * Infinity;
  return s * (1 + m / 1024) * 2 ** (e - 15);
}

describe("float32 → float16", () => {
  it.each([
    [0, 0x0000],
    [1, 0x3c00],
    [-2, 0xc000],
    [0.5, 0x3800],
    [65504, 0x7bff],
    [70000, 0x7c00], // tràn → +inf
    [-70000, 0xfc00],
    [5.960464477539063e-8, 0x0001], // subnormal nhỏ nhất
    [1e-9, 0x0000],
    [0.1, 0x2e66],
    [3.14159, 0x4248],
  ])("%d → 0x%s", (v, bits) => {
    expect(f32ToF16Bits(v)).toBe(bits);
  });

  it("matches the engine's own Float16Array bit-for-bit (normal, subnormal, ties)", () => {
    const H = (globalThis as unknown as { Float16Array: new (n: number) => Uint16Array & { [i: number]: number } })
      .Float16Array;
    const ref = new H(1);
    const refBits = new Uint16Array((ref as unknown as { buffer: ArrayBuffer }).buffer);
    let seed = 99;
    const rnd = () => (seed = (seed * 1664525 + 1013904223) >>> 0) / 4294967296;
    const values = [0.1, 3.14159, 1 + 2 ** -11, 1 + 3 * 2 ** -11, 2 ** -24 * 1.5, 2 ** -24 * 2.5, 65519, 65520];
    for (let i = 0; i < 30000; i++) values.push((rnd() - 0.5) * 10 ** (Math.floor(rnd() * 12) - 7));
    for (const v of values) {
      ref[0] = Math.fround(v); // pcd.bin là float32: so cùng đầu vào float32, tránh làm tròn kép
      expect(f32ToF16Bits(v), `v=${v}`).toBe(refBits[0]);
    }
  });

  it("NaN stays NaN", () => {
    expect(Number.isNaN(f16ToF32(f32ToF16Bits(NaN)))).toBe(true);
  });

  it("round-trips within half-precision error over the LiDAR range", () => {
    let seed = 1;
    for (let i = 0; i < 5000; i++) {
      seed = (seed * 1664525 + 1013904223) >>> 0;
      const v = (seed / 4294967296 - 0.5) * 200; // ±100 m
      const back = f16ToF32(f32ToF16Bits(v));
      expect(Math.abs(back - v)).toBeLessThanOrEqual(Math.abs(v) * 2 ** -10 + 2 ** -24);
    }
  });
});

describe("pcdToF16", () => {
  it("drops the ring column and keeps x,y,z,i as float16", () => {
    const src = new Float32Array([1, 2, 3, 40, 7, -1.5, 0.25, 10, 255, 9]);
    const out = pcdToF16(Buffer.from(src.buffer), 2);
    const u16 = new Uint16Array(out.buffer, out.byteOffset, out.byteLength / 2);
    expect(Array.from(u16).map(f16ToF32)).toEqual([1, 2, 3, 40, -1.5, 0.25, 10, 255]);
  });

  it("normalises to the requested point count by repeating from the start", () => {
    const src = new Float32Array([1, 2, 3, 4, 0, 5, 6, 7, 8, 0]);
    const out = pcdToF16(Buffer.from(src.buffer), 5);
    expect(out.byteLength).toBe(5 * 4 * 2);
    const u16 = new Uint16Array(out.buffer, out.byteOffset, out.byteLength / 2);
    expect(f16ToF32(u16[16])).toBe(1); // điểm thứ 5 = điểm thứ 1
  });

  it("synthetic cloud is deterministic and converts to LIDAR_POINTS points", () => {
    expect(syntheticCloud(3).equals(syntheticCloud(3))).toBe(true);
    expect(pcdToF16(syntheticCloud(3)).byteLength).toBe(LIDAR_POINTS * 8);
  });
});

describe("script without nuScenes (no H:/)", () => {
  it("exits 0 and writes grey images, thumbnails and float16 clouds matching the mocks", async () => {
    const out = mkdtempSync(path.join(tmpdir(), "vcf-media-"));
    tmp.push(out);
    const r = spawnSync(process.execPath, [SCRIPT, "--from", path.join(out, "does-not-exist"), "--frames", "6", "--out", out], {
      encoding: "utf8",
    });
    expect(r.status, r.stderr).toBe(0);

    const framesJson = JSON.parse(readFileSync(path.resolve(__dirname, "../mocks/frames-page1.json"), "utf8"));
    const items = Array.isArray(framesJson) ? framesJson : framesJson.items;
    const firstToken = items[0].sampleToken;

    const f01 = path.join(out, "images", firstToken);
    expect(readdirSync(f01).length).toBeGreaterThanOrEqual(1);
    const firstCam = readdirSync(f01)[0];
    const meta = await sharp(path.join(f01, firstCam)).metadata();
    expect([meta.width, meta.height]).toEqual([800, 450]);
    const thumb = await sharp(path.join(out, "thumbs", `${firstToken}.jpg`)).metadata();
    expect([thumb.width, thumb.height]).toEqual([320, 180]);

    const lidarFile = path.join(out, "lidar", `${firstToken}.f16`);
    if (existsSync(lidarFile)) {
      expect(statSync(lidarFile).size).toBe(34720 * 4 * 2);
    }
  }, 60_000);

  it("rejects bad arguments with exit 1", () => {
    const r = spawnSync(process.execPath, [SCRIPT, "--frames", "0"], { encoding: "utf8" });
    expect(r.status).toBe(1);
  });
});
