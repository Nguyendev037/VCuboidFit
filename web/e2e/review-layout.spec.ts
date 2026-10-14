import { expect, test, type Locator } from "@playwright/test";
import fs from "node:fs";
import path from "node:path";

const JOB = "full_mini";
const SEL = "b5be3fd2493b";
const EVIDENCE_DIR = path.resolve(process.cwd(), "..", "..", "..", "planning", "13_2026-10-14_viewer-3d-cvat", "evidence", "P05");

async function expectNonOverlapping(left: Locator, right: Locator) {
  const leftBox = await left.boundingBox();
  const rightBox = await right.boundingBox();
  expect(leftBox).not.toBeNull();
  expect(rightBox).not.toBeNull();
  expect(leftBox!.x + leftBox!.width).toBeLessThanOrEqual(rightBox!.x);
}

test("P05 review layout stays aligned and responsive", async ({ page }) => {
  fs.mkdirSync(EVIDENCE_DIR, { recursive: true });

  await page.setViewportSize({ width: 1440, height: 900 });
  await page.goto(`/review/${JOB}?sel=${SEL}`);
  await expect(page.getByTestId("frame-grid")).toBeVisible({ timeout: 20_000 });

  const toolbar = page.getByTestId("review-toolbar");
  const grid = page.getByTestId("frame-grid");
  const chips = page.getByTestId("review-filter-chips");
  const gateControls = page.getByTestId("review-gate-controls");
  const exportActions = page.getByTestId("review-export-actions");
  const toolbarBox = await toolbar.boundingBox();
  const gridBox = await grid.boundingBox();
  expect(toolbarBox).not.toBeNull();
  expect(gridBox).not.toBeNull();
  expect(Math.abs(toolbarBox!.x + 24 - gridBox!.x)).toBeLessThanOrEqual(2);
  expect(toolbarBox!.height).toBeLessThan(80);
  await expectNonOverlapping(chips, gateControls);
  const exportBox = await exportActions.boundingBox();
  expect(exportBox).not.toBeNull();
  expect(Math.abs(exportBox!.x + 24 - gridBox!.x)).toBeLessThanOrEqual(2);
  await page.screenshot({ path: path.join(EVIDENCE_DIR, "after-b-1440x900.png"), fullPage: true });

  await page.setViewportSize({ width: 1920, height: 1080 });
  await page.reload();
  await expect(page.getByTestId("frame-grid")).toBeVisible({ timeout: 20_000 });
  await expectNonOverlapping(page.getByTestId("review-filter-chips"), page.getByTestId("review-gate-controls"));
  await page.screenshot({ path: path.join(EVIDENCE_DIR, "after-b-1920x1080.png"), fullPage: true });

  await page.setViewportSize({ width: 390, height: 844 });
  await page.reload();
  await expect(page.getByTestId("frame-grid")).toBeVisible({ timeout: 20_000 });
  const mobileOverflow = await page.evaluate(() => document.documentElement.scrollWidth - window.innerWidth);
  expect(mobileOverflow).toBeLessThanOrEqual(0);
  await page.screenshot({ path: path.join(EVIDENCE_DIR, "after-b-390x844.png"), fullPage: true });
});
