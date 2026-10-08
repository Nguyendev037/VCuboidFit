import { expect, test } from "@playwright/test";

const EVIDENCE = process.env.E2E_EVIDENCE_DIR ?? "test-results";

const report = {
  datasetId: "ds1", ok: true, scenes: 3, frames: 36,
  imagesByCam: { CAM_FRONT: 36, CAM_FRONT_LEFT: 36, CAM_FRONT_RIGHT: 36, CAM_BACK: 36, CAM_BACK_LEFT: 36, CAM_BACK_RIGHT: 36 },
  hasLidar: true, hasAnnotations: true, version: "v1.0-mini", errors: [], warnings: [],
};
const prog = (phase: string, done: number, total: number, etaSec: number | null) => ({
  uploadId: "u1", phase, done, total, unit: "bytes", elapsedSec: 1, etaSec, updatedAt: "2026-10-08T10:00:00",
});

test("C1-C4 + ETA: collapse long upload list, show check progress bar", async ({ page }) => {
  const sizes = new Map<string, number>();
  const polls = [null, prog("extract", 40, 100, 90), prog("validate", 0, 1, 12)];
  let pollCount = 0;
  await page.route("**/api/uploads", (route) => route.fulfill({ json: { uploadId: "u1" } }));
  await page.route("**/api/uploads/u1", (route) => route.fulfill({ json: { files: [] } }));
  await page.route("**/api/uploads/u1/files/*", (route) => {
    const req = route.request();
    const name = decodeURIComponent(req.url().split("/").pop()!);
    const size = Number(req.headers()["x-file-size"]);
    sizes.set(name, size);
    return route.fulfill({ json: { received: size } });
  });
  await page.route("**/api/datasets/progress/u1", (route) => {
    const body = polls[Math.min(pollCount++, polls.length - 1)];
    return body ? route.fulfill({ json: body }) : route.fulfill({ status: 404, json: { error: { code: "not_found", message: "x" } } });
  });
  await page.route("**/api/uploads/u1/finalize", async (route) => {
    await new Promise((r) => setTimeout(r, 4500));
    return route.fulfill({ json: report });
  });

  await page.goto("/");
  await page.evaluate(() => localStorage.removeItem("vcf.uploadListCollapsed"));
  const files = ["a", "b", "c", "d"].map((n) => ({ name: `${n}.zip`, mimeType: "application/zip", buffer: Buffer.alloc(2048, 1) }));
  await page.getByTestId("file-input").setInputFiles(files);

  // ETA: lần poll đầu 404 ⇒ không xác định; sau đó có pha + thời gian còn lại
  const eta = page.getByTestId("check-eta");
  await expect(eta).toContainText("Đang xét tệp đầu vào");
  await expect(eta).toContainText("Giải nén · còn khoảng 01:30", { timeout: 6000 });
  await page.screenshot({ path: `${EVIDENCE}/eta_extract.png` });
  await expect(eta).toContainText("Kiểm tra cấu trúc nuScenes · còn khoảng 00:12", { timeout: 4000 });
  await expect(eta.locator("progress")).toHaveAttribute("value", "85");

  // C1/C2: 4 tệp ⇒ tự rút gọn; nút "Mở rộng"
  const toggle = page.getByRole("button", { name: "Mở rộng" });
  await expect(toggle).toHaveAttribute("aria-expanded", "false");
  await expect(page.getByTestId("upload-summary")).toContainText("4 tệp");
  await expect(page.getByTestId("upload-item")).toHaveCount(0);
  await page.screenshot({ path: `${EVIDENCE}/collapse_collapsed.png` });

  // C4 + C3: bàn phím mở rộng, nhớ trong localStorage
  await toggle.focus();
  await page.keyboard.press("Enter");
  await expect(page.getByTestId("upload-item")).toHaveCount(4);
  await expect(page.getByRole("button", { name: "Rút gọn" })).toHaveAttribute("aria-expanded", "true");
  expect(await page.evaluate(() => localStorage.getItem("vcf.uploadListCollapsed"))).toBe("0");
  await page.screenshot({ path: `${EVIDENCE}/collapse_expanded.png` });
});
