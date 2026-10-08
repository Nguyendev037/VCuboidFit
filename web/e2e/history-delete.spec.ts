import { expect, test } from "@playwright/test";

const EVIDENCE = process.env.E2E_EVIDENCE_DIR ?? "test-results";

const job = (jobId: string, state: string) => ({
  jobId, datasetId: "ds1", pipeline: "lidar", state,
  createdAt: "2026-10-08T10:00:00", finishedAt: state === "done" ? "2026-10-08T10:05:00" : null,
  scenes: 3, frames: 120, version: "v1.0-mini", lastSelectionId: null,
});

test("H1-H4: delete one run through the confirm dialog", async ({ page }) => {
  let items = [job("aaaaaaaaaaaa", "done"), job("cccccccccccc", "running")];
  const deleteCalls: string[] = [];
  await page.route("**/api/jobs", (route) => route.fulfill({ json: { items } }));
  await page.route("**/api/jobs/*", (route) => {
    const req = route.request();
    if (req.method() !== "DELETE") return route.fallback();
    const id = req.url().split("/").pop()!;
    deleteCalls.push(id);
    items = items.filter((i) => i.jobId !== id);
    return route.fulfill({ json: { deleted: [id] } });
  });

  await page.goto("/");
  const rows = page.getByRole("button", { name: "Xoá lần chạy" });
  await expect(rows).toHaveCount(2);
  await expect(rows.nth(1)).toBeDisabled(); // job đang chạy
  await expect(page.getByRole("button", { name: "Xoá tất cả" })).toBeVisible();

  await rows.nth(0).click();
  const dialog = page.getByRole("dialog");
  await expect(dialog).toContainText("dữ liệu đã tải lên vẫn giữ");
  await page.screenshot({ path: `${EVIDENCE}/history_confirm.png` });
  await dialog.getByRole("button", { name: "Xoá", exact: true }).click();

  await expect(page.getByRole("button", { name: "Xoá lần chạy" })).toHaveCount(1);
  await expect(page.getByText("aaaaaaaaaaaa")).toHaveCount(0);
  expect(deleteCalls).toEqual(["aaaaaaaaaaaa"]);
  await page.screenshot({ path: `${EVIDENCE}/history_after_delete.png` });
});
