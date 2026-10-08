import { Suspense } from "react";
import ReviewClient from "./review-client";

export default async function ReviewPage({
  params,
}: {
  params: Promise<{ jobId: string }>;
}) {
  const { jobId } = await params;
  return (
    <Suspense
      fallback={
        <div className="min-h-screen bg-[#F7F8FA] flex items-center justify-center p-8">
          <div className="text-center text-xs text-slate-500 flex flex-col items-center gap-2">
            <div className="w-6 h-6 border-2 border-blue-600 border-t-transparent rounded-full animate-spin" />
            <p>Đang tải Deep Review...</p>
          </div>
        </div>
      }
    >
      <ReviewClient jobId={jobId} />
    </Suspense>
  );
}
