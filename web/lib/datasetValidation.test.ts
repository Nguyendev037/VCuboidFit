import { describe, expect, it } from "vitest";
import type { DatasetReport } from "@/lib/api/types";
import { datasetValidationMessage, isDatasetUsable } from "./datasetValidation";

const report = (overrides: Partial<DatasetReport> = {}): DatasetReport => ({
  datasetId: "dataset-1",
  ok: true,
  scenes: 1,
  frames: 1,
  imagesByCam: {
    CAM_FRONT_LEFT: 0,
    CAM_FRONT: 0,
    CAM_FRONT_RIGHT: 0,
    CAM_BACK_LEFT: 0,
    CAM_BACK: 0,
    CAM_BACK_RIGHT: 0,
  },
  hasLidar: false,
  hasAnnotations: false,
  version: "test",
  errors: [],
  warnings: [],
  ...overrides,
});

describe("dataset validation", () => {
  it("requires a valid report with at least one scene before enabling analysis", () => {
    expect(isDatasetUsable(report())).toBe(true);
    expect(isDatasetUsable(report({ ok: false }))).toBe(false);
    expect(isDatasetUsable(report({ scenes: 0 }))).toBe(false);
    expect(isDatasetUsable(null)).toBe(false);
  });

  it("uses worker errors and provides a fallback message for empty reports", () => {
    expect(datasetValidationMessage(report({ ok: false, errors: ["Không tìm thấy manifest"] })))
      .toBe("Không tìm thấy manifest");
    expect(datasetValidationMessage(report({ scenes: 0 })))
      .toBe("Không tìm thấy cảnh hợp lệ trong gói dữ liệu.");
  });
});
