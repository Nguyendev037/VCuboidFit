import { test, expect } from "@playwright/test";

test.describe("CVAT 3D Viewer (SPEC-P02)", () => {
  test.beforeEach(async ({ page }) => {
    // Đảm bảo không có cờ thu gọn ảnh trong localStorage trước mỗi test
    await page.addInitScript(() => {
      try {
        window.localStorage.removeItem("vcf.viewer.camsCollapsed");
      } catch {
        // ignore
      }
    });
  });

  test("T9: Khung LiDAR chiếm ≥ 70% vùng main ở viewport 1440×900", async ({ page }) => {
    await page.setViewportSize({ width: 1440, height: 900 });
    await page.goto("/review/full_mini?sel=9b139ff7f3c4");

    const cell = page.locator('[data-testid="frame-cell"]').first();
    await expect(cell).toBeVisible({ timeout: 20_000 });
    await cell.dblclick();

    await expect(page.getByTestId("frame-overlay")).toBeVisible({ timeout: 20_000 });
    await expect(page.getByTestId("lidar-scene")).toBeVisible({ timeout: 20_000 });

    const overlayMain = page.getByTestId("frame-overlay").locator("main");
    const mainBox = await overlayMain.boundingBox();
    const lidarBox = await page.getByTestId("lidar-scene").boundingBox();

    expect(mainBox, "vùng main phải có kích thước").not.toBeNull();
    expect(lidarBox, "khung lidar phải có kích thước").not.toBeNull();

    const ratio = lidarBox!.height / mainBox!.height;
    console.log(`[T9 RATIO] LiDAR / main = ${lidarBox!.height} / ${mainBox!.height} = ${ratio.toFixed(4)}`);
    expect(ratio).toBeGreaterThanOrEqual(0.70);
  });

  test("T10: Frustum mặc định TẮT, nhấn phím C bật/tắt frustum", async ({ page }) => {
    await page.setViewportSize({ width: 1440, height: 900 });
    await page.goto("/review/full_mini?sel=9b139ff7f3c4");

    const cell = page.locator('[data-testid="frame-cell"]').first();
    await expect(cell).toBeVisible({ timeout: 20_000 });
    await cell.dblclick();

    const lidarScene = page.getByTestId("lidar-scene");
    await expect(lidarScene).toBeVisible({ timeout: 20_000 });

    // Frustum mặc định TẮT (data-frustums="0")
    await expect(lidarScene).toHaveAttribute("data-frustums", "0");
    const camBtn = page.getByRole("button", { name: "Camera (C)" });
    await expect(camBtn).toHaveAttribute("aria-pressed", "false");

    // Nhấn phím 'c' -> Frustum BẬT
    await page.keyboard.press("c");
    await expect(lidarScene).toHaveAttribute("data-frustums", "1");
    await expect(camBtn).toHaveAttribute("aria-pressed", "true");

    // Nhấn phím 'c' lần nữa -> Frustum TẮT
    await page.keyboard.press("c");
    await expect(lidarScene).toHaveAttribute("data-frustums", "0");
    await expect(camBtn).toHaveAttribute("aria-pressed", "false");
  });

  test("Bố cục dải ảnh duy nhất và nút Thu gọn ảnh (phím I)", async ({ page }) => {
    await page.setViewportSize({ width: 1440, height: 900 });
    await page.goto("/review/full_mini?sel=9b139ff7f3c4");

    const cell = page.locator('[data-testid="frame-cell"]').first();
    await expect(cell).toBeVisible({ timeout: 20_000 });
    await cell.dblclick();

    await expect(page.getByTestId("frame-overlay")).toBeVisible({ timeout: 20_000 });

    // 1 dải duy nhất với 6 camera
    const strip = page.getByTestId("cams-strip");
    await expect(strip).toBeVisible({ timeout: 20_000 });
    const camImages = strip.locator('[data-testid^="camera-"]');
    await expect(camImages).toHaveCount(6);

    // Nút "Thu gọn ảnh (I)"
    const toggleBtn = page.getByTestId("toggle-collapse-cams");
    await expect(toggleBtn).toHaveText(/Thu gọn ảnh/);

    // Nhấn phím 'i' -> dải ảnh thu gọn (ẩn đi)
    await page.keyboard.press("i");
    await expect(strip).toBeHidden();
    await expect(toggleBtn).toHaveText(/Hiện ảnh/);

    // Nhấn phím 'i' lần nữa -> dải ảnh mở lại
    await page.keyboard.press("i");
    await expect(strip).toBeVisible();
    await expect(toggleBtn).toHaveText(/Thu gọn ảnh/);
  });

  test("Các nút chuyển đổi lớp: GT, Cụm LiDAR, PointPillars", async ({ page }) => {
    await page.setViewportSize({ width: 1440, height: 900 });
    await page.goto("/review/full_mini?sel=9b139ff7f3c4");

    const cell = page.locator('[data-testid="frame-cell"]').first();
    await expect(cell).toBeVisible({ timeout: 20_000 });
    await cell.dblclick();

    await expect(page.getByTestId("frame-overlay")).toBeVisible({ timeout: 20_000 });

    const gtBtn = page.getByRole("button", { name: "GT", exact: true });
    const clusterBtn = page.getByRole("button", { name: "Cụm LiDAR", exact: true });
    const ppBtn = page.getByRole("button", { name: "PointPillars", exact: true });

    await expect(gtBtn).toHaveAttribute("aria-pressed", "true");
    await expect(clusterBtn).toHaveAttribute("aria-pressed", "true");
    await expect(ppBtn).toHaveAttribute("aria-pressed", "true");

    // Toggle GT
    await gtBtn.click();
    await expect(gtBtn).toHaveAttribute("aria-pressed", "false");
    await gtBtn.click();
    await expect(gtBtn).toHaveAttribute("aria-pressed", "true");
  });

  test("Bộ lọc điểm thân xe (SPEC-P06): mặc định lọc bật (ẩn điểm), nhấn Điểm thân xe hiện lại", async ({ page }) => {
    await page.setViewportSize({ width: 1440, height: 900 });
    await page.goto("/review/full_mini?sel=fcd157331ab4");

    const cell = page.locator('[data-testid="frame-cell"]').first();
    await expect(cell).toBeVisible({ timeout: 20_000 });
    await cell.dblclick();

    const lidarScene = page.getByTestId("lidar-scene");
    await expect(lidarScene).toBeVisible({ timeout: 20_000 });

    // Bộ lọc mặc định BẬT (data-filter-ego="1", nút Điểm thân xe aria-pressed="false")
    await expect(lidarScene).toHaveAttribute("data-filter-ego", "1");
    const egoBtn = page.getByRole("button", { name: "Điểm thân xe", exact: true });
    await expect(egoBtn).toBeVisible();
    await expect(egoBtn).toHaveAttribute("aria-pressed", "false");

    // Nhấn "Điểm thân xe" -> tắt lọc, hiện lại điểm thân xe (data-filter-ego="0", aria-pressed="true")
    await egoBtn.click();
    await expect(lidarScene).toHaveAttribute("data-filter-ego", "0");
    await expect(egoBtn).toHaveAttribute("aria-pressed", "true");

    // Nhấn lần nữa -> bật lại lọc, ẩn điểm thân xe
    await egoBtn.click();
    await expect(lidarScene).toHaveAttribute("data-filter-ego", "1");
    await expect(egoBtn).toHaveAttribute("aria-pressed", "false");
  });
});
