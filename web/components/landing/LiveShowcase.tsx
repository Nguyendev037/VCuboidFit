"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { Camera, Loader2, PlayCircle } from "lucide-react";
import { getFrame, listFrames, listJobs, listSelections } from "@/lib/api/client";
import type { Cam, FrameDetail, FrameSummary } from "@/lib/api/types";
import dynamic from "next/dynamic";
import sample1 from "@/mocks/frame-detail-mock-f01.json";
import sample2 from "@/mocks/frame-detail-mock-f02.json";
import sample3 from "@/mocks/frame-detail-mock-f03.json";
import sample4 from "@/mocks/frame-detail-mock-f04.json";
import sample5 from "@/mocks/frame-detail-mock-f05.json";
import sample6 from "@/mocks/frame-detail-mock-f06.json";
import { chooseShowcaseFrame, loadShowcaseDetail } from "./showcaseFrames";
// The landing demo must work on a clean clone without generated mock-media.
const showcaseUrl = (url: string) => url.replace(/^\/mock-media\//, "/demo/showcase/");
export const SAMPLES = ([sample1, sample2, sample3, sample4, sample5, sample6] as FrameDetail[]).map(frame => ({
  ...frame,
  thumbUrl: showcaseUrl(frame.thumbUrl),
  bevUrl: frame.bevUrl ? showcaseUrl(frame.bevUrl) : frame.bevUrl,
  cams: frame.cams.map(cam => ({ ...cam, imageUrl: showcaseUrl(cam.imageUrl) })),
  lidar: frame.lidar ? { ...frame.lidar, url: showcaseUrl(frame.lidar.url) } : frame.lidar,
}));
const SAMPLE_RUN = { jobId: "nuScenes-mau", sid: "minh-hoa", frames: SAMPLES, sample: true };

// three.js chỉ nạp phía client, và chỉ khi trang giới thiệu thật sự cần
const LidarScene = dynamic(() => import("@/components/viewer/LidarScene").then((m) => m.LidarScene), {
  ssr: false,
  loading: () => <div className="h-full min-h-[18rem] animate-pulse rounded-lg bg-[#080d15]" />,
});

const RING: { key: string; label: string }[] = [
  { key: "CAM_FRONT_LEFT", label: "Trước trái" },
  { key: "CAM_FRONT", label: "Trước" },
  { key: "CAM_FRONT_RIGHT", label: "Trước phải" },
  { key: "CAM_BACK_LEFT", label: "Sau trái" },
  { key: "CAM_BACK", label: "Sau" },
  { key: "CAM_BACK_RIGHT", label: "Sau phải" },
];

/** Lấy các frame đã chọn của lần chạy hoàn tất gần nhất (chỉ đọc, không tạo job mới). */
export async function loadLatest(): Promise<{ jobId: string; sid: string; frames: FrameSummary[] } | null> {
  const jobs = await listJobs();
  // The mock API lists legacy scene fixtures whose media is unavailable.
  if (jobs.some(job => job.jobId === "mock-job")) return null;
  const job = jobs.find((j) => j.state === "done" && j.pipeline === "lidar") ?? jobs.find((j) => j.state === "done");
  if (!job) return null;
  const sels = await listSelections(job.jobId);
  const sid = job.lastSelectionId ?? sels[0]?.selectionId;
  if (!sid) return null;
  const frames = await listFrames(job.jobId, sid);
  return frames.length ? { jobId: job.jobId, sid, frames: frames.slice(0, 6) } : null;
}

/** Mô phỏng 3D thật: point cloud LiDAR + hộp 3D + 6 camera của frame được chọn. */
export function LiveShowcase() {
  const latest = useQuery({ queryKey: ["landing-latest"], queryFn: loadLatest, retry: false, staleTime: 60_000 });
  const [pick, setPick] = useState(0);
  const [failedRuns, setFailedRuns] = useState<Record<string, string[]>>({});
  const data = latest.data ?? SAMPLE_RUN;
  const sample = data === SAMPLE_RUN;
  const runKey = `${data.jobId}/${data.sid}`;
  const failed = failedRuns[runKey] ?? [];
  const frame = chooseShowcaseFrame(data.frames, pick, failed);
  const rejectFrame = (token: string) => setFailedRuns(runs => ({
    ...runs, [runKey]: [...new Set([...(runs[runKey] ?? []), token])],
  }));

  const detail = useQuery<FrameDetail>({
    queryKey: ["landing-frame", data?.jobId, frame?.sampleToken],
    queryFn: () => loadShowcaseDetail(() => getFrame(data.jobId, frame!.sampleToken, data.sid)),
    initialData: sample ? frame as FrameDetail : undefined,
    enabled: !sample && !!frame,
    staleTime: 60_000,
    retry: false,
  });

  useEffect(() => {
    if (!sample && detail.isError && frame) {
      const token = frame.sampleToken;
      queueMicrotask(() => setFailedRuns(runs => ({
        ...runs, [runKey]: [...new Set([...(runs[runKey] ?? []), token])],
      })));
    }
  }, [sample, detail.isError, frame, runKey]);

  if (latest.isPending && !sample) {
    return (
      <div className="hud-card flex min-h-[22rem] items-center justify-center gap-3 text-sm text-slate-600" role="status">
        <Loader2 className="h-5 w-5 animate-spin text-blue-600" aria-hidden="true" />
        Đang nạp mô phỏng 3D từ lần chạy gần nhất…
      </div>
    );
  }

  if (!data || !frame) {
    return (
      <div className="hud-card relative flex min-h-[22rem] flex-col items-center justify-center gap-4 overflow-hidden p-8 text-center">
        <div aria-hidden className="hud-grid absolute inset-0 opacity-60" />
        <div className="relative flex flex-col items-center gap-3">
          <span className="flex h-12 w-12 items-center justify-center rounded-full bg-blue-50 text-blue-600 ring-1 ring-blue-500/30">
            <PlayCircle className="h-6 w-6" aria-hidden="true" />
          </span>
          <h3 className="font-display text-xl font-semibold text-slate-900">Chưa có kết quả để mô phỏng 3D</h3>
          <p className="max-w-md text-sm text-slate-600">
            Mô phỏng này dùng chính khung xem 3D của dự án với dữ liệu thật. Hãy nạp nuScenes và chạy phân tích (hoặc “Chạy thử dữ liệu mẫu”) trong Dashboard, rồi quay lại trang này.
          </p>
          <Link href="/dashboard" className="inline-flex min-h-10 items-center rounded bg-blue-600 px-4 text-sm font-semibold text-white hover:bg-blue-700">Mở Dashboard</Link>
        </div>
      </div>
    );
  }

  const d = sample ? frame as FrameDetail : detail.data;
  const camByKey = new Map<string, FrameDetail["cams"][number]>();
  d?.cams.forEach((c) => camByKey.set(String(c.cam), c));

  return (
    <div className="hud-card overflow-hidden" data-testid="live-showcase">
      <div className="font-data flex flex-wrap items-center justify-between gap-2 border-b border-slate-200 bg-slate-50 px-4 py-2 text-xs text-slate-500">
        <span className="flex items-center gap-2">
          <span className="h-1.5 w-1.5 animate-pulse rounded-full bg-emerald-500" />
          {sample ? "DỮ LIỆU nuScenes MẪU · minh hoạ, không phải benchmark" : `KẾT QUẢ THẬT · job ${data.jobId}`} · {frame.sceneName} · frame {frame.frameIdx}
        </span>
        <span>LIDAR_TOP · điểm S {frame.S.toFixed(2)}</span>
      </div>

      <div className="grid gap-px bg-slate-200/60 lg:grid-cols-[minmax(0,1fr)_17rem]">
        <div className="relative h-[24rem] bg-[#080d15] lg:h-[28rem]">
          {d?.lidar ? (
            <LidarScene lidarUrl={d.lidar.url} boxes3d={d.boxes3d} camPoses={d.camPoses} className="!rounded-none" />
          ) : (
            <div className="flex h-full items-center justify-center text-sm text-slate-500" role="status">
              {d ? "Frame này không có LiDAR." : detail.isError ? "Đang chuyển sang frame kế tiếp…" : "Đang nạp point cloud…"}
            </div>
          )}
          <div aria-hidden className="hud-scan pointer-events-none absolute inset-x-0 z-[6]" />
        </div>

        <div className="flex flex-col gap-3 bg-white p-4">
          <div>
            <p className="font-data text-xs uppercase tracking-wider text-slate-500">Chọn frame đã tuyển</p>
            <div className="mt-2 grid grid-cols-3 gap-2">
              {data.frames.map((f, i) => (
                <button
                  key={f.sampleToken}
                  type="button"
                  onClick={() => setPick(i)}
                  aria-pressed={frame.sampleToken === f.sampleToken}
                  disabled={failed.includes(f.sampleToken)}
                  aria-label={`Frame hạng ${f.rank}, ${f.sceneName}`}
                  className={`group relative aspect-video overflow-hidden rounded-md ring-1 transition active:scale-[0.97] disabled:opacity-40 ${frame.sampleToken === f.sampleToken ? "ring-2 ring-blue-500" : "ring-slate-300/40 hover:ring-blue-400"}`}
                >
                  {/* eslint-disable-next-line @next/next/no-img-element */}
                  {!failed.includes(f.sampleToken) && <img src={f.thumbUrl} alt="" onError={() => rejectFrame(f.sampleToken)} className="h-full w-full object-cover transition-transform duration-300 group-hover:scale-110" />}
                  <span className="font-data absolute left-1 top-1 rounded bg-black/70 px-1 text-xs text-[#e1e2ec]">#{f.rank}</span>
                </button>
              ))}
            </div>
          </div>
          <div className="rounded-lg bg-slate-50 p-3">
            <p className="font-data text-xs uppercase tracking-wider text-slate-500">Dữ liệu frame</p>
            <dl className="font-data mt-2 space-y-1 text-xs text-slate-700">
              <div className="flex justify-between"><dt>Điểm LiDAR</dt><dd>{d?.lidar ? d.lidar.numPoints.toLocaleString("vi-VN") : "—"}</dd></div>
              <div className="flex justify-between"><dt>Hộp 3D</dt><dd>{d ? d.boxes3d.length : "—"}</dd></div>
              <div className="flex justify-between"><dt>Điểm S</dt><dd className="text-emerald-600">{frame.S.toFixed(2)}</dd></div>
            </dl>
          </div>
          <Link
            href={sample ? "/dashboard" : `/review/${data.jobId}?sel=${data.sid}&frame=${frame.sampleToken}`}
            className="mt-auto inline-flex min-h-10 items-center justify-center rounded bg-slate-100 px-4 text-sm font-semibold text-slate-800 transition hover:bg-slate-200 hover:text-blue-700 active:scale-[0.98]"
          >
            {sample ? "Mở Dashboard để phân tích dữ liệu" : "Mở Deep Review frame này"}
          </Link>
        </div>
      </div>

      <div className="border-t border-slate-200 p-4">
        <p className="font-data mb-2 flex items-center gap-2 text-xs uppercase tracking-wider text-slate-500">
          <Camera className="h-3.5 w-3.5" aria-hidden="true" />
          Vòng 6 camera nuScenes của frame đang xem
        </p>
        <div className="grid grid-cols-2 gap-2 sm:grid-cols-3 lg:grid-cols-6">
          {RING.map(({ key, label }) => {
            const cam = camByKey.get(key) as { imageUrl: string } | undefined;
            return (
              <figure key={key} className="group relative aspect-video overflow-hidden rounded-lg bg-slate-50 ring-1 ring-slate-300/30">
                {cam ? (
                  // eslint-disable-next-line @next/next/no-img-element
                  <img src={cam.imageUrl} alt={`${label} (${key})`} loading="lazy" className="h-full w-full object-cover transition-transform duration-500 group-hover:scale-105" />
                ) : (
                  <div className="flex h-full items-center justify-center"><Camera className="h-5 w-5 text-slate-400" aria-hidden="true" /></div>
                )}
                <figcaption className="font-data absolute inset-x-0 bottom-0 bg-black/65 px-2 py-0.5 text-xs text-[#e1e2ec] backdrop-blur-sm">{key}</figcaption>
              </figure>
            );
          })}
        </div>
      </div>
    </div>
  );
}

export type { Cam };

/** Ảnh nền mờ của frame hạng 1 phía sau hero (không có dữ liệu thì không hiển thị gì). */
export function HeroBackdrop() {
  const latest = useQuery({ queryKey: ["landing-latest"], queryFn: loadLatest, retry: false, staleTime: 60_000 });
  const f = latest.data?.frames[0];
  if (!f) return null;
  return (
    <div aria-hidden className="pointer-events-none absolute inset-x-0 top-0 -z-0 h-[34rem] overflow-hidden">
      <div className="hud-bg-photo absolute inset-0 opacity-30" style={{ backgroundImage: `url(${f.thumbUrl})` }} />
      <div className="absolute inset-0 bg-gradient-to-b from-white/30 via-white/80 to-[#f4f7fb]" />
    </div>
  );
}
