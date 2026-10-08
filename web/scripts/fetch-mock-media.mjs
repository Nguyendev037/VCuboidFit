// Tạo public/mock-media/ cho chế độ mock (gitignore — ảnh nuScenes là CC BY-NC-SA, KHÔNG commit).
//   node scripts/fetch-mock-media.mjs --from H:/ --frames 24 [--out public/mock-media]
// Có nuScenes ở --from: chép ảnh camera (giảm 50 % → 800×450), sinh thumbnail 320×180,
// đổi LiDAR .pcd.bin (float32 ×5) → .bin float16 x,y,z,i. Không có: sinh ảnh xám + point cloud tổng hợp.
// Token, camera sẵn có, camera tốt nhất và frame không LiDAR đọc từ web/mocks/ (nguồn duy nhất).
// `--from` chỉ ĐỌC. Mọi cloud được chuẩn hoá về đúng LIDAR_POINTS điểm (mock-only) để khớp numPoints trong mock.
import { existsSync, mkdirSync, readFileSync, writeFileSync } from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";

import sharp from "sharp";

const HERE = path.dirname(fileURLToPath(import.meta.url));
const WEB = path.resolve(HERE, "..");
export const LIDAR_POINTS = 34720;
export const IMG = { w: 800, h: 450 };
export const THUMB = { w: 320, h: 180 };

// ---- float32 → float16 ----
const f32 = new Float32Array(1);
const u32 = new Uint32Array(f32.buffer);

export function f32ToF16Bits(val) {
  f32[0] = val;
  const x = u32[0];
  const sign = (x >>> 16) & 0x8000;
  let exp = (x >>> 23) & 0xff;
  let mant = x & 0x7fffff;
  if (exp === 0xff) return sign | 0x7c00 | (mant ? 0x200 : 0); // inf / nan
  exp = exp - 127 + 15;
  if (exp >= 0x1f) return sign | 0x7c00; // tràn → inf
  if (exp <= 0) {
    if (exp < -10) return sign; // quá nhỏ → 0
    mant |= 0x800000;
    const shift = 14 - exp;
    let h = mant >> shift;
    const rem = mant & ((1 << shift) - 1);
    const half = 1 << (shift - 1);
    if (rem > half || (rem === half && (h & 1))) h++;
    return sign | h;
  }
  let h = sign | (exp << 10) | (mant >> 13);
  const rem = mant & 0x1fff;
  if (rem > 0x1000 || (rem === 0x1000 && (h & 1))) h++; // nhớ có thể tràn sang exponent: đúng
  return h;
}

/** Float32Array(n×5: x,y,z,intensity,ring) → Buffer float16 (n×4: x,y,z,i), đúng `points` điểm. */
export function pcdToF16(buf, points = LIDAR_POINTS) {
  const src = new Float32Array(buf.buffer, buf.byteOffset, Math.floor(buf.byteLength / 20) * 5);
  const n = src.length / 5;
  if (n === 0) throw new Error("pcd.bin rỗng");
  const out = new Uint16Array(points * 4);
  for (let p = 0; p < points; p++) {
    const s = (p % n) * 5; // thiếu điểm thì lặp lại từ đầu
    for (let k = 0; k < 4; k++) out[p * 4 + k] = f32ToF16Bits(src[s + k]);
  }
  return Buffer.from(out.buffer);
}

/** Point cloud giả: mặt đường + vài cụm vật thể. Tất định theo `seed`. */
export function syntheticCloud(seed, points = LIDAR_POINTS) {
  let s = (seed * 2654435761) >>> 0 || 1;
  const rnd = () => ((s = (s * 1664525 + 1013904223) >>> 0) / 4294967296);
  const out = new Float32Array(points * 5);
  for (let p = 0; p < points; p++) {
    const cluster = p % 7 === 0;
    const ang = rnd() * Math.PI * 2;
    const r = cluster ? 6 + Math.floor(rnd() * 4) * 5 + rnd() * 1.5 : 2 + Math.sqrt(rnd()) * 48;
    out[p * 5] = Math.cos(ang) * r;
    out[p * 5 + 1] = Math.sin(ang) * r;
    out[p * 5 + 2] = cluster ? -1.8 + rnd() * 2.2 : -1.8 + rnd() * 0.15;
    out[p * 5 + 3] = Math.floor(rnd() * 255);
    out[p * 5 + 4] = p % 32;
  }
  return Buffer.from(out.buffer);
}

// ---- nuScenes thật (chỉ đọc) ----
const readJson = (p) => JSON.parse(readFileSync(p, "utf8"));

function realFrames(from, count) {
  const tdir = ["v1.0-mini", "v1.0-trainval"].map((v) => path.join(from, v)).find((d) => existsSync(path.join(d, "sample.json")));
  if (!tdir) return null;
  const samples = new Map(readJson(path.join(tdir, "sample.json")).map((s) => [s.token, s]));
  const byToken = new Map();
  for (const r of readJson(path.join(tdir, "sample_data.json"))) {
    if (!r.is_key_frame) continue;
    const ch = r.filename.split("/")[1];
    if (!byToken.has(r.sample_token)) byToken.set(r.sample_token, {});
    byToken.get(r.sample_token)[ch] = path.join(from, r.filename);
  }
  const out = [];
  for (const scene of readJson(path.join(tdir, "scene.json"))) {
    for (let t = scene.first_sample_token; t && samples.has(t); t = samples.get(t).next) {
      out.push(byToken.get(t) ?? {});
      if (out.length >= count) return out;
    }
  }
  return out;
}

async function grayJpeg(label, luma, w, h) {
  const base = sharp({ create: { width: w, height: h, channels: 3, background: { r: luma, g: luma, b: luma } } });
  const fs = Math.round(h / 12);
  const svg = `<svg xmlns="http://www.w3.org/2000/svg" width="${w}" height="${h}"><text x="${w / 2}" y="${h / 2}" font-size="${fs}" font-family="sans-serif" text-anchor="middle" fill="#ffffff">${label}</text></svg>`;
  try {
    return await base.composite([{ input: Buffer.from(svg) }]).jpeg({ quality: 70 }).toBuffer();
  } catch {
    return await sharp({ create: { width: w, height: h, channels: 3, background: { r: luma, g: luma, b: luma } } }).jpeg({ quality: 70 }).toBuffer();
  }
}

export async function build({ from, frames, out }) {
  const framesData = readJson(path.join(WEB, "mocks", "frames-page1.json"));
  const frameList = (Array.isArray(framesData) ? framesData : framesData.items).slice(0, frames);
  const noLidar = new Set();
  for (const f of frameList) {
    const p = path.join(WEB, "mocks", `frame-detail-${f.sampleToken}.json`);
    if (existsSync(p) && readJson(p).lidar === null) noLidar.add(f.sampleToken);
  }
  const real = from && existsSync(from) ? realFrames(from, frames) : null;
  console.log(real ? `nuScenes thật: ${real.length} frame từ ${from}` : "Không có nuScenes — sinh ảnh xám + point cloud tổng hợp");

  const pad = real && real.length < frameList.length ? frameList.slice(0, real.length) : frameList;
  mkdirSync(path.join(out, "thumbs"), { recursive: true });
  mkdirSync(path.join(out, "lidar"), { recursive: true });
  let nImg = 0;
  for (const [i, f] of pad.entries()) {
    const token = f.sampleToken;
    mkdirSync(path.join(out, "images", token), { recursive: true });
    const files = real?.[i] ?? {};
    const makeImg = async (cam, w, h) => {
      const src = files[cam];
      if (src && existsSync(src)) return sharp(src).resize(w, h).jpeg({ quality: 80 }).toBuffer();
      return grayJpeg(`${token} ${cam}`, 70 + ((i * 17 + cam.length * 9) % 90), w, h);
    };
    for (const cam of f.camsAvailable) {
      writeFileSync(path.join(out, "images", token, `${cam}.jpg`), await makeImg(cam, IMG.w, IMG.h));
      nImg++;
    }
    writeFileSync(path.join(out, "thumbs", `${token}.jpg`), await makeImg(f.bestCam, THUMB.w, THUMB.h));
    if (!noLidar.has(token)) {
      const lp = files.LIDAR_TOP;
      const raw = lp && existsSync(lp) ? readFileSync(lp) : syntheticCloud(i + 1);
      writeFileSync(path.join(out, "lidar", `${token}.f16`), pcdToF16(raw)); // .f16: IDM bắt URL .bin
    }
  }
  console.log(`Xong: ${pad.length} frame, ${nImg} ảnh camera, thumbnail + LiDAR → ${out}`);
}

function parseArgs(argv) {
  const a = { from: null, frames: 24, out: path.join(WEB, "public", "mock-media") };
  for (let i = 0; i < argv.length; i++) {
    if (argv[i] === "--from") a.from = argv[++i];
    else if (argv[i] === "--frames") a.frames = Number(argv[++i]);
    else if (argv[i] === "--out") a.out = path.resolve(argv[++i]);
    else throw new Error(`Tham số lạ: ${argv[i]}`);
  }
  if (!Number.isInteger(a.frames) || a.frames < 1) throw new Error("--frames phải là số nguyên ≥ 1");
  return a;
}

if (process.argv[1] && path.resolve(process.argv[1]) === fileURLToPath(import.meta.url)) {
  build(parseArgs(process.argv.slice(2))).catch((e) => {
    console.error(e.message);
    process.exit(1);
  });
}
