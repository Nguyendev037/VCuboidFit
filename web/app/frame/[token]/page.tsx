import { Suspense } from "react";
import FrameClient from "./frame-client";

export default async function FrameViewerPage({
  params,
}: {
  params: Promise<{ token: string }>;
}) {
  const { token } = await params;
  return (
    <Suspense
      fallback={
        <div className="fixed inset-0 bg-[#0B0F17] flex items-center justify-center text-slate-400">
          <div className="flex flex-col items-center gap-3">
            <div className="w-8 h-8 border-2 border-blue-500 border-t-transparent rounded-full animate-spin" />
            <p className="text-xs">Đang nạp Frame Viewer...</p>
          </div>
        </div>
      }
    >
      <FrameClient token={token} />
    </Suspense>
  );
}
