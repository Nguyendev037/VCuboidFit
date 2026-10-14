import { expect, test } from "@playwright/test";
import paramsSchema from "../mocks/params-schema.json";
import selection from "../mocks/selection-lidar.json";
import { PANEL_HELP } from "../lib/glossary";

const EVIDENCE = process.env.E2E_EVIDENCE_DIR ?? "test-results";
const JOB = "test_panel_simplify";

const tier0Schema = () => {
  const s = JSON.parse(JSON.stringify(paramsSchema));
  s.tierAvailable = [0];
  s.fields.find((f: { key: string }) => f.key === "tier").options[1].disabledReason = "Chưa có model seed cho job này";
  return s;
};

test("T-A4: simplified tuning panel has 6 controls, no #strategy-select, no Mức đa dạng, shows tierLock", async ({ page }) => {
  await page.route("**/api/jobs", (route) =>
    route.fulfill({
      json: {
        items: [
          {
            jobId: JOB,
            datasetId: "ds1",
            pipeline: "lidar",
            state: "done",
            createdAt: "2026-10-15T00:00:00",
            finishedAt: "2026-10-15T00:05:00",
            scenes: 3,
            frames: 120,
            version: "v1.0-mini",
            lastSelectionId: null,
          },
        ],
      },
    }),
  );
  await page.route("**/api/datasets/ds1", (route) =>
    route.fulfill({
      json: {
        datasetId: "ds1",
        ok: true,
        scenes: 3,
        frames: 120,
        imagesByCam: {},
        hasLidar: true,
        hasAnnotations: true,
        version: "v1.0-mini",
        errors: [],
        warnings: [],
      },
    }),
  );
  await page.route(`**/api/jobs/${JOB}`, (route) =>
    route.fulfill({ json: { jobId: JOB, state: "done", pipeline: "lidar", stages: [] } }),
  );
  await page.route(`**/api/jobs/${JOB}/selections`, (route) => route.fulfill({ json: { items: [] } }));
  await page.route(`**/api/jobs/${JOB}/params-schema`, (route) => route.fulfill({ json: tier0Schema() }));
  await page.route(`**/api/jobs/${JOB}/select`, (route) =>
    route.fulfill({ json: { ...selection, tierAvailable: [0] } }),
  );
  await page.route(`**/api/jobs/${JOB}/selections/**`, (route) =>
    route.fulfill({ json: { items: [], total: 0, budgetB: 0 } }),
  );
  await page.route(`**/api/jobs/${JOB}/t1-remote`, (route) =>
    route.fulfill({ status: 404, json: { error: { code: "not_found", message: "None" } } }),
  );

  await page.goto("/dashboard");
  await page.getByRole("button", { name: "Mở", exact: true }).first().click();

  const aside = page.locator("aside");
  await expect(aside.getByText("Tinh chỉnh")).toBeVisible();

  // T-A4: Ngoài [data-advanced-params], đếm input, select, [role=switch], button[aria-pressed] = 6
  const candidateLocators = aside.locator("input, select, [role=switch], button[aria-pressed]");
  const count = await candidateLocators.count();
  let outsideCount = 0;
  for (let i = 0; i < count; i++) {
    const el = candidateLocators.nth(i);
    const inside = await el.evaluate((node) => !!node.closest("[data-advanced-params]"));
    if (!inside) {
      outsideCount++;
    }
  }
  expect(outsideCount).toBe(6);

  // #strategy-select count 0
  await expect(page.locator("#strategy-select")).toHaveCount(0);

  // "Mức đa dạng" count 0
  await expect(page.getByText("Mức đa dạng")).toHaveCount(0);

  // khi noTier1 có chữ PANEL_HELP.tierLock.label hiển thị
  await expect(aside.getByText(PANEL_HELP.tierLock.label)).toBeVisible();

  // 4 thẻ hiển thị
  const cardBalanced = aside.locator("button[aria-pressed]").filter({ has: page.getByText(PANEL_HELP["preset.balanced"].label, { exact: true }) });
  const cardRare = aside.locator("button[aria-pressed]").filter({ has: page.getByText(PANEL_HELP["preset.rare_first"].label, { exact: true }) });
  const cardHard = aside.locator("button[aria-pressed]").filter({ has: page.getByText(PANEL_HELP["preset.hard_for_model"].label, { exact: true }) });
  const cardSafety = aside.locator("button[aria-pressed]").filter({ has: page.getByText(PANEL_HELP["preset.safety_scenarios"].label, { exact: true }) });

  await expect(cardBalanced).toBeVisible();
  await expect(cardRare).toBeVisible();
  await expect(cardHard).toBeVisible();
  await expect(cardSafety).toBeVisible();

  // Do noTier1, các thẻ đều disabled
  await expect(cardBalanced).toBeDisabled();
  await expect(cardRare).toBeDisabled();
  await expect(cardHard).toBeDisabled();
  await expect(cardSafety).toBeDisabled();

  // Công tắc Trải đều nhiều cảnh
  const spreadSwitch = aside.getByRole("switch", { name: "Trải đều nhiều cảnh" });
  await expect(spreadSwitch).toBeVisible();
  await expect(spreadSwitch).toHaveAttribute("aria-checked", "true");
  await expect(aside.getByText(/Ít nhất ~.* cảnh/)).toBeVisible();

  await spreadSwitch.click();
  await expect(spreadSwitch).toHaveAttribute("aria-checked", "false");
  await expect(aside.getByText("Có thể dồn vào ít cảnh")).toBeVisible();

  await page.screenshot({ path: `${EVIDENCE}/panel_simplify_6controls.png` });
});
