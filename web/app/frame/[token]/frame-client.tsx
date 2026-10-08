"use client";

import React, { useMemo } from "react";
import { useRouter, useSearchParams } from "next/navigation";
import { useQuery } from "@tanstack/react-query";
import { listFrames } from "@/lib/api/client";
import { FrameViewer } from "@/components/viewer/FrameViewer";

export interface FrameClientProps {
  token: string;
}

export default function FrameClient({ token }: FrameClientProps) {
  const router = useRouter();
  const searchParams = useSearchParams();

  const jobId = searchParams.get("jobId") || "mock-job";
  const sel = searchParams.get("sel") || "sel-balanced";
  const budget = Number(searchParams.get("budget") || 0.05);

  const framesQuery = useQuery({
    queryKey: ["frames", jobId, sel, budget],
    queryFn: () => listFrames(jobId, sel, { budget, page: 1, pageSize: 200 }),
  });

  const list = useMemo(() => framesQuery.data ?? [], [framesQuery.data]);
  const activeIdx = useMemo(() => list.findIndex((f) => f.sampleToken === token), [list, token]);

  const handlePrev =
    activeIdx > 0
      ? () => router.push(`/frame/${list[activeIdx - 1].sampleToken}?jobId=${jobId}&sel=${sel}&budget=${budget}`)
      : undefined;

  const handleNext =
    activeIdx >= 0 && activeIdx < list.length - 1
      ? () => router.push(`/frame/${list[activeIdx + 1].sampleToken}?jobId=${jobId}&sel=${sel}&budget=${budget}`)
      : undefined;

  const handleClose = () => {
    router.push(`/review/${jobId}?sel=${sel}&budget=${budget}`);
  };

  return (
    <FrameViewer
      jobId={jobId}
      token={token}
      sid={sel}
      onPrev={handlePrev}
      onNext={handleNext}
      onClose={handleClose}
    />
  );
}
