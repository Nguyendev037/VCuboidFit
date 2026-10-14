import type { FrameDetail, FrameSummary } from "@/lib/api/types";

/** Wrap once, skipping failed tokens; null terminates an exhausted run. */
export function chooseShowcaseFrame<T extends FrameSummary>(frames: T[], pick: number, failed: readonly string[] = []): T | null {
  if (!frames.length) return null;
  const start = Math.max(0, Math.min(pick, frames.length - 1));
  for (let offset = 0; offset < frames.length; offset++) {
    const frame = frames[(start + offset) % frames.length];
    if (!failed.includes(frame.sampleToken)) return frame;
  }
  return null;
}

/** Validate media before mounting the viewer; bounded failures advance the selection. */
export async function loadShowcaseDetail(load: () => Promise<FrameDetail>): Promise<FrameDetail> {
  const signal = AbortSignal.timeout(8_000);
  const timeout = new Promise<never>((_, reject) => {
    signal.addEventListener("abort", () => reject(new Error("Frame load timed out")), { once: true });
  });
  return Promise.race([timeout, (async () => {
    const detail = await load();
    const urls = [detail.thumbUrl, ...detail.cams.map(cam => cam.imageUrl), ...(detail.lidar ? [detail.lidar.url] : [])];
    await Promise.all(urls.map(async url => {
      const response = await fetch(url, { method: "HEAD", signal });
      if (!response.ok) throw new Error(`Media HTTP ${response.status}`);
    }));
    return detail;
  })()]);
}
