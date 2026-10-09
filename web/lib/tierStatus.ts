import type { JobStatus, Tier1State } from "@/lib/api/types";

/** Plan 09 D4: chỉ còn stage `t1` đang chạy (t0 đã xong) ⇒ kết quả Tầng 0 vẫn dùng được. */
export function isT1OnlyRunning(job?: JobStatus | null): boolean {
  return (
    !!job &&
    job.pipeline === "lidar" &&
    (job.state === "queued" || job.state === "running") &&
    job.stage === "t1" &&
    job.stages.some((s) => s.name === "t0" && s.state === "done")
  );
}

/** Kết quả đã xem được: job xong, hoặc chỉ còn Tầng 1 chạy nền. */
export function isAnalysisReady(job?: JobStatus | null): boolean {
  return job?.state === "done" || isT1OnlyRunning(job);
}

export const TIER1_LABEL: Record<Tier1State, string> = {
  ready: "Sẵn sàng",
  queued: "Đang chờ chạy",
  running: "Đang chạy",
  done: "Đã có",
  skipped: "Chưa chạy",
  failed: "Lỗi",
};

export function formatSeconds(sec?: number | null): string | null {
  if (sec == null || !Number.isFinite(sec)) return null;
  return sec < 60 ? `${sec.toLocaleString("vi-VN", { maximumFractionDigits: 1 })} s` : `${Math.round(sec / 60)} phút`;
}
