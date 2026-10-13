"use client";
import React, { useState } from "react";
import { ApiError } from "@/lib/api/errors";

export const WORKER_COMMAND = '$env:WORKSPACE="model/workspace"; .\\model\\worker\\.venv\\Scripts\\python.exe -m uvicorn service.main:create_app --factory --app-dir model/worker --port 8001';

export function LoadingState({ label = "Đang tải…" }: { label?: string }) {
 return <div role="status" aria-live="polite" className="w-full space-y-3 p-4"><p>{label}</p>{[0,1,2].map(i=><div key={i} aria-hidden="true" className="h-12 animate-pulse rounded-vcf-control bg-vcf-border/40" />)}</div>;
}
export function EmptyState({ message }: { message: string }) {
 return <div role="status" className="rounded-vcf-card border border-vcf-border bg-vcf-surface p-5 text-vcf-text"><p>{message}</p><a href="/dashboard" className="mt-3 inline-block text-vcf-accent-ink underline">Về dashboard để chọn dữ liệu</a></div>;
}
export function DataError({ error, onRetry }: { error: unknown; onRetry: () => void }) {
 const [copied,setCopied]=useState(false);
 const [copyError,setCopyError]=useState(false);
 const status=error instanceof ApiError ? error.status : 0;
 const unavailable=status===0 || status===502 || status===503 || status===504;
 const message=error instanceof Error ? error.message : String(error);
 const copy=async()=>{try{await navigator.clipboard.writeText(WORKER_COMMAND);setCopied(true);setCopyError(false);}catch{setCopyError(true);}};
 return <div role="alert" className="w-full rounded-vcf-card border border-vcf-danger bg-vcf-surface p-4 text-sm text-vcf-text">
  <p className="font-semibold text-vcf-danger">{unavailable ? "Worker chưa chạy" : status===404 ? "Không tìm thấy job/selection/frame" : "Không tải được dữ liệu"}</p>
  <p className="mt-2 break-words">{message}</p>
  {unavailable&&<><p className="mt-3">Chạy lệnh từ root VCuboidFit (môi trường worker đã cài):</p><code className="mt-2 block select-text break-all rounded bg-vcf-bg p-2">{WORKER_COMMAND}</code><button type="button" className="mt-3 mr-3 underline" onClick={()=>void copy()}>{copied ? "Đã sao chép" : "Sao chép lệnh"}</button>{copyError&&<p>Không sao chép được. Chọn và sao chép lệnh ở trên.</p>}</>}
  <button type="button" onClick={onRetry} className="mt-3 mr-3 rounded-vcf-control bg-vcf-accent px-3 py-2 text-white">Thử lại</button>
  <a href="/dashboard" className="underline">Về dashboard</a>
 </div>;
}
