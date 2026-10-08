import { expect, test } from "@playwright/test";
import paramsSchema from "../mocks/params-schema.json";
import selection from "../mocks/selection-lidar.json";

const EVIDENCE = process.env.E2E_EVIDENCE_DIR ?? "test-results";
const JOB = "aaaaaaaaaaaa";

const tier0Schema = () => {
  const s = JSON.parse(JSON.stringify(paramsSchema));
  s.tierAvailable = [0];
  s.fields.find((f: { key: string }) => f.key === "tier").options[1].disabledReason = "Chưa có model seed cho job này";
  return s;
};

test("A1-A4, A5, A7: params panel without tier1 model, run tier1 on Colab", async ({ page }) => {
  const selectBodies: Record<string, unknown>[] = [];
  let postCalls = 0;
  const task = (state: string) => ({
    taskId: "t1_abcdef123456", jobId: JOB, datasetId: "ds1", state,
    params: { epochs: 20, sweeps: 1, batch: 4 }, createdAt: "2026-10-08T10:00:00", attempts: 0, error: null,
  });
  await page.route("**/api/jobs", (route) => route.fulfill({ json: { items: [{
    jobId: JOB, datasetId: "ds1", pipeline: "lidar", state: "done", createdAt: "2026-10-08T10:00:00",
    finishedAt: "2026-10-08T10:05:00", scenes: 3, frames: 120, version: "v1.0-mini", lastSelectionId: null }] } }));
  await page.route("**/api/datasets/ds1", (route) => route.fulfill({ json: {
    datasetId: "ds1", ok: true, scenes: 3, frames: 120, imagesByCam: {}, hasLidar: true, hasAnnotations: true,
    version: "v1.0-mini", errors: [], warnings: [] } }));
  await page.route(`**/api/jobs/${JOB}`, (route) => route.fulfill({ json: { jobId: JOB, state: "done", pipeline: "lidar", stages: [] } }));
  await page.route(`**/api/jobs/${JOB}/selections`, (route) => route.fulfill({ json: { items: [] } }));
  await page.route(`**/api/jobs/${JOB}/params-schema`, (route) => route.fulfill({ json: tier0Schema() }));
  await page.route(`**/api/jobs/${JOB}/select`, (route) => {
    selectBodies.push(route.request().postDataJSON());
    return route.fulfill({ json: { ...selection, tierAvailable: [0] } });
  });
  await page.route(`**/api/jobs/${JOB}/selections/**`, (route) => route.fulfill({ json: { items: [], total: 0, budgetB: 0 } }));
  await page.route(`**/api/jobs/${JOB}/t1-remote`, (route) => {
    if (route.request().method() === "POST") { postCalls++; return route.fulfill({ status: 201, json: task("queued") }); }
    return postCalls
      ? route.fulfill({ json: task("queued") })
      : route.fulfill({ status: 404, json: { error: { code: "not_found", message: "Job chưa có việc Tầng 1 từ xa." } } });
  });

  await page.goto("/");
  await page.getByRole("button", { name: "Mở", exact: true }).first().click();
  const panel = page.getByRole("button", { name: /Tham số nâng cao/ });
  await expect(panel).toBeVisible();
  if ((await panel.getAttribute("aria-expanded")) !== "true") await panel.click();
  const box = page.locator("#advanced-settings");

  // A1/A2: hiện đủ, Tầng 1 bị khoá kèm lý do
  await expect(box.getByText("Số frame giống nhất để so sánh độ hiếm")).toBeVisible();
  await expect(box.getByText("Chưa có model seed cho job này")).toBeVisible();
  await expect(box).not.toContainText(/undefined|NaN/);
  // A3: α 100%, β/γ khoá 0%
  const weight = (name: string) => box.locator("label", { hasText: name }).filter({ has: page.locator("input[type=range]") });
  await expect(weight("Hiếm trong dữ liệu").getByText("100%")).toBeVisible();
  for (const name of ["Lạ với model", "Model chưa chắc chắn"]) {
    await expect(weight(name).getByText("0%", { exact: true })).toBeVisible();
    await expect(weight(name).locator("input[type=range]")).toBeDisabled();
    await expect(weight(name)).toHaveAttribute("title", /Đã khoá/);
  }
  // A4: chiến lược khoá
  await expect(page.getByRole("button", { name: /Hiếm trước/ })).toBeDisabled();
  // A5: request select không có tầng 1
  await box.getByRole("button", { name: "Áp dụng" }).click();
  await expect.poll(() => selectBodies.length).toBeGreaterThan(0);
  for (const b of selectBodies) {
    expect(b.tier ?? 0).toBe(0);
    expect(b.beta ?? 0).toBe(0);
    expect(b.gamma ?? 0).toBe(0);
  }
  // A7: nút Colab -> queued
  await box.getByRole("button", { name: "Chạy Tầng 1 trên Colab" }).click();
  await expect(box.getByTestId("colab-status")).toContainText("Đang chờ Colab nhận việc");
  expect(postCalls).toBe(1);
  await page.screenshot({ path: `${EVIDENCE}/after_desktop_1440x900.png` });
});
