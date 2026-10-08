import { mkdirSync, mkdtempSync, rmSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import path from "node:path";
import { afterEach, beforeEach, describe, expect, it } from "vitest";

import { GET } from "./media/[jobId]/[...path]/route";

let ws: string;
const THUMB = Buffer.from("RIFF....WEBPthumbnail-bytes-0123456789");
const LIDAR = Buffer.from(Array.from({ length: 64 }, (_, i) => i));
const JPG = Buffer.from([0xff, 0xd8, 0xff, ...Buffer.from("jpeg-bytes-of-a-camera-image")]);
const PNG = Buffer.from([0x89, 0x50, 0x4e, 0x47, ...Buffer.from("png-fixture-bytes")]);

beforeEach(() => {
  ws = mkdtempSync(path.join(tmpdir(), "vcf-media-ws-"));
  process.env.WORKSPACE = ws;
  const media = path.join(ws, "jobs", "j1", "media");
  mkdirSync(path.join(media, "thumbs"), { recursive: true });
  mkdirSync(path.join(media, "lidar"), { recursive: true });
  mkdirSync(path.join(media, "bev"), { recursive: true });
  writeFileSync(path.join(media, "thumbs", "t1.webp"), THUMB);
  writeFileSync(path.join(media, "thumbs", "t2.jpg"), JPG);
  writeFileSync(path.join(media, "lidar", "f1.bin"), LIDAR);
  writeFileSync(path.join(media, "bev", "f1.png"), PNG);
  writeFileSync(path.join(ws, "jobs", "j1", "job.json"), JSON.stringify({ datasetId: "ds1" }));
  const cam = path.join(ws, "datasets", "ds1", "data", "samples", "CAM_FRONT");
  mkdirSync(cam, { recursive: true });
  writeFileSync(path.join(cam, "a.jpg"), JPG);
  writeFileSync(path.join(ws, "datasets", "ds1", "data", "secret.json"), "{}");
  writeFileSync(path.join(ws, ".env"), "SECRET=1");
  // mồi có đuôi ảnh HỢP LỆ nằm ngoài thư mục gốc: chỉ guard resolve/startsWith mới chặn được
  writeFileSync(path.join(ws, "secret.jpg"), JPG);
  mkdirSync(path.join(media, "thumbsx"), { recursive: true }); // thư mục anh em trùng tiền tố
  writeFileSync(path.join(media, "thumbsx", "a.jpg"), JPG);
  mkdirSync(path.join(ws, "jobs", "j2"), { recursive: true }); // job không có job.json
});
afterEach(() => {
  rmSync(ws, { recursive: true, force: true });
  delete process.env.WORKSPACE;
});

const get = (jobId: string, p: string[], headers: Record<string, string> = {}) =>
  GET(new Request("http://x/api/media/" + jobId, { headers }), { params: Promise.resolve({ jobId, path: p }) });
const bytes = async (r: Response) => Buffer.from(await r.arrayBuffer());

describe("media route", () => {
  it("serves a thumbnail with the right type, length and immutable cache header", async () => {
    const r = await get("j1", ["thumbs", "t1.webp"]);
    expect(r.status).toBe(200);
    expect(r.headers.get("content-type")).toBe("image/webp");
    expect(r.headers.get("cache-control")).toBe("public, max-age=31536000, immutable");
    expect(r.headers.get("accept-ranges")).toBe("bytes");
    expect(r.headers.get("content-length")).toBe(String(THUMB.length));
    expect((await bytes(r)).equals(THUMB)).toBe(true);
  });

  it("serves lidar under .f16 with a non-download content type (download managers grab .bin)", async () => {
    const lidar = await get("j1", ["lidar", "f1.f16"]);
    expect(lidar.status).toBe(200);
    expect(lidar.headers.get("content-type")).toBe("application/x-vcf-lidar-f16");
    expect((await bytes(lidar)).equals(LIDAR)).toBe(true);
    expect((await get("j1", ["lidar", "missing.f16"])).status).toBe(404);
  });

  it("serves jpeg thumbs, lidar .bin and dataset images with their content types", async () => {
    expect((await get("j1", ["thumbs", "t2.jpg"])).headers.get("content-type")).toBe("image/jpeg");
    const lidar = await get("j1", ["lidar", "f1.bin"]);
    expect(lidar.headers.get("content-type")).toBe("application/octet-stream");
    expect((await bytes(lidar)).equals(LIDAR)).toBe(true);
    const img = await get("j1", ["images", "samples", "CAM_FRONT", "a.jpg"]);
    expect(img.status).toBe(200);
    expect(img.headers.get("content-type")).toBe("image/jpeg");
    expect((await bytes(img)).equals(JPG)).toBe(true);
  });

  it("serves a BEV PNG fixture", async () => {
    const r = await get("j1", ["bev", "f1.png"]);
    expect(r.status).toBe(200);
    expect(r.headers.get("content-type")).toBe("image/png");
    expect((await bytes(r)).equals(PNG)).toBe(true);
  });

  it("Range: bytes=0-9 → 206 with exactly 10 bytes and Content-Range", async () => {
    const r = await get("j1", ["thumbs", "t1.webp"], { range: "bytes=0-9" });
    expect(r.status).toBe(206);
    expect(r.headers.get("content-range")).toBe(`bytes 0-9/${THUMB.length}`);
    expect(r.headers.get("content-length")).toBe("10");
    expect(r.headers.get("cache-control")).toBe("public, max-age=31536000, immutable");
    const body = await bytes(r);
    expect(body).toHaveLength(10);
    expect(body.equals(THUMB.subarray(0, 10))).toBe(true);
  });

  it("supports open-ended and suffix ranges and clamps the end", async () => {
    let r = await get("j1", ["lidar", "f1.bin"], { range: "bytes=60-" });
    expect(r.status).toBe(206);
    expect((await bytes(r)).equals(LIDAR.subarray(60))).toBe(true);
    r = await get("j1", ["lidar", "f1.bin"], { range: "bytes=-4" });
    expect((await bytes(r)).equals(LIDAR.subarray(60))).toBe(true);
    r = await get("j1", ["lidar", "f1.bin"], { range: "bytes=62-9999" });
    expect(r.headers.get("content-range")).toBe("bytes 62-63/64");
  });

  it("unsatisfiable or malformed ranges → 416 with Content-Range */size", async () => {
    for (const range of ["bytes=100-200", "bytes=5-2", "bytes=0-1,4-5", "items=0-3"]) {
      const r = await get("j1", ["lidar", "f1.bin"], { range });
      expect(r.status, range).toBe(416);
      expect(r.headers.get("content-range")).toBe("bytes */64");
    }
  });

  it("traversal, absolute and drive-letter paths → 400 and nothing is read (ca 3)", async () => {
    const bad: string[][] = [
      ["thumbs", "..", "..", "job.json"],
      ["thumbs", "../../job.json"], // %2F trong một segment
      ["images", "..", "..", "..", ".env"],
      ["images", "samples", "..", "..", "..", "..", ".env"],
      ["images", "/etc/passwd"],
      ["", "etc", "passwd"],
      ["images", "C:", "Windows", "win.ini"],
      ["images", "C:\\Windows\\win.ini"],
      ["thumbs", "..\\..\\job.json"],
      ["thumbs", "t1.webp\0"],
      ["thumbs", "."],
    ];
    // segment đơn lẻ vẫn bị chặn dù đuôi hợp lệ
    bad.push(["thumbs", "..", "..", "..", "..", "secret.jpg"], ["images", "..", "..", "..", "secret.jpg"], ["thumbs", "..", "thumbsx", "a.jpg"]);
    for (const p of bad) {
      const r = await get("j1", p);
      expect(r.status, JSON.stringify(p)).toBe(400);
      expect(r.headers.get("content-type")).toMatch(/json/);
    }
  });

  it("unknown kind or a non-media file type → 400 (dataset json is not downloadable)", async () => {
    for (const p of [["secret"], ["images", "secret.json"], ["thumbs", "t1.txt"], ["lidar", "f1.webp"], ["images"], []]) {
      const r = await get("j1", p);
      expect(r.status, JSON.stringify(p)).toBe(400);
    }
  });

  it("a hostile jobId is 400", async () => {
    for (const id of ["..", "a/b", "../x", "j1\0", ""]) {
      expect((await get(id, ["thumbs", "t1.webp"])).status, JSON.stringify(id)).toBe(400);
    }
  });

  it("unknown job → 404; job without job.json cannot serve images; missing file → 404", async () => {
    expect((await get("nope", ["thumbs", "t1.webp"])).status).toBe(404);
    expect((await get("j2", ["images", "samples", "CAM_FRONT", "a.jpg"])).status).toBe(404);
    expect((await get("j1", ["thumbs", "missing.webp"])).status).toBe(404);
    expect((await get("j1", ["images", "samples", "CAM_FRONT", "missing.jpg"])).status).toBe(404);
  });

  it("a directory is never served", async () => {
    expect((await get("j1", ["images", "samples"])).status).toBe(400); // không có đuôi ảnh
    mkdirSync(path.join(ws, "datasets", "ds1", "data", "dir.jpg"));
    expect((await get("j1", ["images", "dir.jpg"])).status).toBe(404);
  });
});
