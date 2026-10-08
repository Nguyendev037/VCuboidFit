import type { DatasetReport } from "@/lib/api/types";

export function isDatasetUsable(
  report: Pick<DatasetReport, "ok" | "scenes"> | null | undefined,
): boolean {
  return report?.ok === true && Number.isFinite(report.scenes) && report.scenes > 0;
}

export function datasetValidationMessage(report: DatasetReport): string {
  const errors = report.errors.filter((message) => message.trim().length > 0);
  if (errors.length > 0) return errors.join(" ");
  if (report.scenes < 1) return "Không tìm thấy cảnh hợp lệ trong gói dữ liệu.";
  return "Gói dữ liệu không hợp lệ. Hãy kiểm tra lại các tệp đã tải lên.";
}
