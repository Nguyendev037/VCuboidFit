// E2E luồng demo 15 phút (SPEC-P03 §2–§7) với worker THẬT: job `m2_mini` + `night_v24`
// đã đăng ký trong `model/workspace/jobs/` (docs/run-local.md §2b, cổng worker 8001, web 3000).
//
// A6 cần worker TẮT thật nên nó được khai CUỐI file và tự dừng tiến trình đang giữ cổng 8001.
// Chạy lại đỏ để chứng minh bộ đo: `E2E_BROKEN=1` đổi mục tiêu sang job/route không tồn tại
// (xem `evidence/E2E/red.txt`), chạy xanh: bỏ biến đó.
import { execFileSync } from "node:child_process";
import fs from "node:fs";
import path from "node:path";
import { expect, test, type Page } from "@playwright/test";

const EV = process.env.E2E_EVIDENCE_DIR
  ? process.env.E2E_EVIDENCE_DIR
  : path.resolve(process.cwd(), "..", "..", "planning", "12_2026-10-14_demo-ui-thursday", "evidence", "E2E");

// Chế độ "hệ cố tình hỏng": trỏ vào job không tồn tại / thoát chế độ present ⇒ mọi bộ đo phải ĐỎ.
const BROKEN = process.env.E2E_BROKEN === "1";
const JOB = BROKEN ? "m2_mini_broken" : "m2_mini";
const NIGHT_JOB = BROKEN ? "night_v24_broken" : "night_v24";
const PRESENT_URL = BROKEN ? "/?present=0" : "/?present=1";

const REPO = path.resolve(process.cwd(), "..");
const VENV_PY = path.join(REPO, "model", "worker", ".venv", "Scripts", "python.exe");
const NIGHT_INDEX = path.join(REPO, "model", "workspace", "jobs", "night_v24", "index", "frames.parquet");

const shot = (page: Page, name: string) => page.screenshot({ path: path.join(EV, name), fullPage: true });

test.beforeAll(() => {
  fs.mkdirSync(EV, { recursive: true });
});

async function openRun(page: Page, jobId: string) {
  await page.goto("/dashboard");
  const row = page.getByRole("listitem").filter({ hasText: jobId });
  await expect(row, `hàng "Lần chạy gần đây" của job ${jobId}`).toHaveCount(1, { timeout: 20_000 });
  await row.getByRole("button", { name: "Mở" }).click();
  await expect(page.getByTestId("metric-selected"), `dashboard ${jobId} mở xong`).toHaveText(/\d+ \/ \d+/, { timeout: 20_000 });
}

/** `img_path` của ca đầu hàng đợi: đọc index của job (chỉ đọc), vì `night_v24` chưa có selection để UI lấy ảnh. */
function nightImagePath(token: string, cam: string): string {
  const code =
    "import pandas as pd,sys;df=pd.read_parquet(sys.argv[1]);" +
    "r=df[(df['sample_token']==sys.argv[2])&(df['cam']==sys.argv[3])];" +
    "print('' if r.empty else r['img_path'].iloc[0])";
  const out = execFileSync(VENV_PY, ["-c", code, NIGHT_INDEX, token, cam], { encoding: "utf8" }).trim();
  expect(out, `index night_v24 có img_path cho ${token}/${cam}`).not.toBe("");
  return out;
}

/** Dừng tiến trình đang giữ cổng 8001 (worker thật) rồi chờ proxy web trả 503. */
async function stopWorkerOnPort8001(page: Page) {
  const list = execFileSync(
    "powershell",
    ["-NoProfile", "-Command", "(Get-NetTCPConnection -LocalPort 8001 -State Listen -ErrorAction SilentlyContinue).OwningProcess"],
    { encoding: "utf8" },
  )
    .split(/\s+/)
    .filter(Boolean);
  const pids = [...new Set(list)];
  expect(pids.length, "có tiến trình worker đang giữ cổng 8001").toBeGreaterThan(0);
  for (const pid of pids) {
    execFileSync("powershell", ["-NoProfile", "-Command", `Stop-Process -Id ${pid} -Force`], { encoding: "utf8" });
  }
  await expect
    .poll(async () => (await page.request.get("/api/jobs")).status(), { timeout: 20_000, message: "web proxy trả 503 khi worker tắt" })
    .toBe(503);
}

test("A2 dashboard m2_mini hiện lô B=21", async ({ page }) => {
  await openRun(page, JOB);
  await expect(page.getByTestId("metric-selected")).toContainText("21 / 404");
  await shot(page, "a2-dashboard-m2-mini.png");
});

test("A3 mở 1 frame: canvas LiDAR + 6 ảnh camera tải 200", async ({ page }) => {
  const media: { url: string; status: number; ct: string }[] = [];
  page.on("response", (res) => {
    const url = res.url();
    if (url.includes(`/api/media/${JOB}/`)) media.push({ url, status: res.status(), ct: res.headers()["content-type"] ?? "" });
  });
  await openRun(page, JOB);
  const thumb = page.getByTestId("thumb").first();
  await expect(thumb).toBeVisible({ timeout: 20_000 });
  await thumb.click();

  await expect(page.getByTestId("frame-overlay"), "Frame Viewer mở từ thumb").toBeVisible({ timeout: 20_000 });
  await expect(page.locator('[data-testid^="camera-"]'), "6 khung camera (surround)").toHaveCount(6, { timeout: 20_000 });
  await expect(page.getByTestId("lidar-scene").locator("canvas").first(), "canvas LiDAR 3D").toBeVisible({ timeout: 20_000 });
  await expect
    .poll(() => media.filter((m) => m.url.includes("/images/") && m.status === 200).length, { timeout: 20_000, message: "≥6 ảnh camera HTTP 200" })
    .toBeGreaterThanOrEqual(6);
  await expect
    .poll(() => media.filter((m) => m.url.includes("/lidar/") && m.status === 200).length, { timeout: 20_000, message: "point cloud LiDAR HTTP 200" })
    .toBeGreaterThanOrEqual(1);
  await expect
    .poll(
      () =>
        page
          .locator('[data-testid="cam-image"]')
          .evaluateAll((imgs) => imgs.filter((i) => (i as HTMLImageElement).complete && (i as HTMLImageElement).naturalWidth > 0).length),
      { timeout: 20_000, message: "≥6 ảnh camera giải mã xong" },
    )
    .toBeGreaterThanOrEqual(6);
  await shot(page, "a3-frame-viewer.png");
});

test("A4 /review/context night_v24 ≥ 20 ca + ảnh ca đầu 200", async ({ page, request }) => {
  const queue = await request.get(`/api/jobs/${NIGHT_JOB}/review-queue?kind=context&offset=0&limit=50`);
  expect(queue.status()).toBe(200);
  const items = ((await queue.json()) as { items?: { sampleToken: string; cam: string }[] }).items ?? [];
  expect(items.length, "số ca bối cảnh trang đầu (≤50)").toBeGreaterThanOrEqual(20);

  await page.goto(`/review/context?job=${NIGHT_JOB}`);
  const cases = page.locator("button").filter({ hasText: /^CAM_(FRONT|BACK)/ });
  await expect(cases.first(), "ca bối cảnh đầu tiên").toBeVisible({ timeout: 20_000 });
  expect(await cases.count(), "số ca hiện trên UI").toBeGreaterThanOrEqual(20);
  await shot(page, "a4-review-context.png");

  const first = items[0];
  const imgPath = nightImagePath(first.sampleToken, first.cam);
  const img = await request.get(`/api/media/${NIGHT_JOB}/images/${imgPath}`);
  expect(img.status(), `GET /api/media/${NIGHT_JOB}/images/${imgPath}`).toBe(200);
  expect(img.headers()["content-type"] ?? "").toContain("image/");
  fs.writeFileSync(
    path.join(EV, "a4-context.json"),
    JSON.stringify({ queueFirstPage: items.length, first: { token: first.sampleToken, cam: first.cam, imgPath, status: img.status() } }, null, 2),
  );
});

test("A5 export ZIP m2_mini HTTP 200", async ({ page }) => {
  await openRun(page, JOB);
  const button = page.getByRole("button", { name: "Xuất ảnh hiếm (ZIP)" });
  await expect(button).toBeVisible({ timeout: 20_000 });
  const [response] = await Promise.all([
    page.waitForResponse((res) => res.url().includes("/export-images.zip"), { timeout: 120_000 }),
    button.click(),
  ]);
  expect(response.status()).toBe(200);
  expect(response.headers()["content-type"] ?? "").toContain("zip");
  await expect(page.getByText(/Xuất ZIP lỗi/)).toHaveCount(0);
  await shot(page, "a5-export-zip.png");
});

test("A7 ?present=1 ẩn link /dev + font 18px", async ({ page }) => {
  await page.goto(PRESENT_URL);
  await page.waitForFunction(() => document.documentElement.dataset.present === "1");
  expect(await page.evaluate(() => getComputedStyle(document.documentElement).fontSize)).toBe("18px");
  expect(await page.locator('a[href^="/dev/"]:visible').count(), "link /dev hiện").toBe(0);
  await page.evaluate(() => {
    const probe = document.createElement("a");
    probe.id = "e2e-dev-probe";
    probe.setAttribute("href", "/dev/viewer");
    probe.textContent = "dev";
    document.body.appendChild(probe);
  });
  expect(await page.locator("#e2e-dev-probe").isVisible(), "link /dev bị CSS ẩn ở present").toBe(false);
  await page.evaluate(() => document.getElementById("e2e-dev-probe")?.remove());
  await shot(page, "a7-present-home.png");
});

test("A6 tắt worker ⇒ thẻ 'Worker chưa chạy'", async ({ page }) => {
  if (!BROKEN) await stopWorkerOnPort8001(page);
  await page.goto("/dashboard");
  await expect(page.getByText("Worker chưa chạy", { exact: true })).toBeVisible({ timeout: 20_000 });
  await expect(page.getByRole("button", { name: "Thử lại" }).first()).toBeVisible();
  await shot(page, "a6-worker-off.png");
});
