// Xuất kết quả THẬT của một job thành bộ "Chạy thử dữ liệu mẫu" (đường LiDAR, rare_v24 multisensor).
//   node scripts/export-sample-run.mjs --job <jobId> [--api http://127.0.0.1:8001] [--web http://localhost:3000] [--frames 6]
// Cần worker (--api) và web dev (--web, phục vụ /api/media) cùng WORKSPACE. Ghi:
//   mocks/{dataset-report,job-done,selection-lidar,analysis-lidar,sample-frame-details}.json
//   public/demo/sample/** (ảnh camera thu về rộng 800 px, thumbnail, BEV, LiDAR .f16 của các frame xem trước).
// Ảnh nuScenes CC BY-NC-SA 4.0 — giấy phép ghi ở public/demo/sample/README.md.
import { mkdirSync, writeFileSync } from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";

import sharp from "sharp";

const WEB = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..");
const arg = (k, d) => { const i = process.argv.indexOf(`--${k}`); return i > 0 ? process.argv[i + 1] : d; };
const job = arg("job");
const api = arg("api", "http://127.0.0.1:8001");
const web = arg("web", "http://localhost:3000");
const nFrames = Number(arg("frames", "12"));
if (!job) throw new Error("thiếu --job");

async function json(method, url, body) {
  const r = await fetch(url, { method, headers: { "content-type": "application/json" }, body: body && JSON.stringify(body) });
  if (!r.ok) throw new Error(`${method} ${url} -> ${r.status} ${await r.text()}`);
  return r.json();
}

const status = await json("GET", `${api}/jobs/${job}`);
const summary = (await json("GET", `${api}/jobs`)).items.find((j) => j.jobId === job);  // JobStatus không mang datasetId
if (!summary) throw new Error(`không thấy job ${job} trong /jobs`);
const report = await json("GET", `${api}/datasets/${summary.datasetId}`);
const sel = await json("POST", `${api}/jobs/${job}/select`, { budget: 0.05, engineVersion: "rare_v24", profile: "multisensor" });
if (sel.engineVersion !== "rare_v24") throw new Error(`engine ${sel.engineVersion}`);
const analysis = await json("GET", `${api}/jobs/${job}/selections/${sel.selectionId}/analysis`);
sel.preview = sel.preview.slice(0, Math.max(nFrames, 1));  // mỗi frame xem trước đều có chi tiết (bấm vào không 404)
const details = {};
for (const p of sel.preview) {
  details[p.sampleToken] = await json("GET", `${api}/jobs/${job}/frames/${p.sampleToken}?sid=${sel.selectionId}`);
}

// Viết lại URL media của job → /demo/sample/..., gom danh sách file cần chép.
const MEDIA = new RegExp(`/api/media/${job}/([^"?]+)`, "g");
const files = new Set();
const rewrite = (obj) => JSON.parse(JSON.stringify(obj)
  .replace(MEDIA, (_, rel) => { files.add(rel); return `/demo/sample/${rel}`; })
  .replaceAll(sel.selectionId, "sel-lidar")
  .replaceAll(job, "mock-job"));

const out = (name, obj) => writeFileSync(path.join(WEB, "mocks", name), JSON.stringify(rewrite(obj), null, 2) + "\n");
out("dataset-report.json", report);
out("job-done.json", status);
out("selection-lidar.json", sel);
out("analysis-lidar.json", analysis);
out("sample-frame-details.json", details);

let bytes = 0;
for (const rel of files) {
  const r = await fetch(`${web}/api/media/${job}/${rel}`);
  if (!r.ok) { console.warn(`bỏ ${rel}: ${r.status}`); continue; }
  let buf = Buffer.from(await r.arrayBuffer());
  if (rel.startsWith("images/") && /\.(jpe?g|png|webp)$/i.test(rel)) {
    buf = await sharp(buf).resize({ width: 800, withoutEnlargement: true }).jpeg({ quality: 78 }).toBuffer();
  }
  const dst = path.join(WEB, "public", "demo", "sample", ...rel.split("/"));
  mkdirSync(path.dirname(dst), { recursive: true });
  writeFileSync(dst, buf);
  bytes += buf.length;
}
console.log(`sample: ${sel.preview.length} frame xem trước, ${Object.keys(details).length} chi tiết, ${files.size} media, ${(bytes / 1e6).toFixed(1)} MB`);
