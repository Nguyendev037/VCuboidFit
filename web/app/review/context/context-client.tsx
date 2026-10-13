"use client";
import { DataError, EmptyState, LoadingState } from "@/components/ui/DataState";
import { toApiError } from "@/lib/api/errors";
import React, { useState } from "react";
import Link from "next/link";
import { useSearchParams } from "next/navigation";
import { useQuery } from "@tanstack/react-query";
import { getFrame } from "@/lib/api/client";
import type { ReviewQueue } from "@/lib/api/types";
import { ContextPanel, reviewReasonLabel } from "@/components/context/ContextPanel";
const LIMIT = 50;
export function ContextReview() {
 const params=useSearchParams(); const job=params.get("job"); const sid=params.get("sel");
 const [offset,setOffset]=useState(0);
 const [active,setActive]=useState<{sampleToken:string;cam:string}|null>(null);
 const [failedImage,setFailedImage]=useState<string|null>(null);
 const queue=useQuery({queryKey:["context-review",job,offset],enabled:!!job,queryFn:async():Promise<ReviewQueue>=>{
   if(process.env.NEXT_PUBLIC_MOCK === "1" || window.sessionStorage.getItem("vcf-demo") === "1") return {items:[]};
   const response=await fetch(`/api/jobs/${encodeURIComponent(job!)}/review-queue?kind=context&offset=${offset}&limit=${LIMIT}`);
   if(!response.ok) throw await toApiError(response);
   return response.json();
 }});
 const detail=useQuery({queryKey:["context-review-frame",job,sid,active?.sampleToken],enabled:!!job&&!!sid&&!!active,queryFn:()=>getFrame(job!,active!.sampleToken,sid!)});
 const camera=detail.data?.cams.find(c=>c.cam===active?.cam);
 return <main className="mx-auto min-h-screen max-w-6xl space-y-5 bg-vcf-bg p-6 text-vcf-text"><Link href={job&&sid ? `/review/${encodeURIComponent(job)}?sel=${encodeURIComponent(sid)}` : "/dashboard"} className="text-vcf-accent-ink">← Quay lại</Link><h1 className="text-2xl font-bold">Hàng đợi duyệt bối cảnh</h1><p className="text-sm">Xem ảnh, tín hiệu và lý do cần duyệt. Thẻ bối cảnh là dự đoán.</p>
 {!job && <p role="alert">Thiếu mã job. Mở hàng đợi từ dashboard.</p>}
 {queue.isPending&&job&&<LoadingState />}{queue.isError&&<DataError error={queue.error} onRetry={()=>void queue.refetch()} />}
 {queue.data?.items.length===0&&<EmptyState message="Không có ảnh cần duyệt ở trang này." />}
 <div className="grid gap-6 md:grid-cols-2"><section className="space-y-2">{queue.data?.items.map(item=><button key={`${item.sampleToken}-${item.cam}`} className="block w-full rounded-vcf-control border bg-vcf-surface p-3 text-left text-sm" onClick={()=>setActive(item)}><strong>{item.cam} · {item.sampleToken.slice(0,8)}</strong>{item.reviewReasons.map(r=><p key={r}>{reviewReasonLabel(r)}</p>)}</button>)}</section><section>
 {active&&!sid&&<p role="alert">Thiếu selection để xem chi tiết.</p>}{detail.isFetching&&<LoadingState />}{detail.isError&&<DataError error={detail.error} onRetry={()=>void detail.refetch()} />}
 {/* eslint-disable-next-line @next/next/no-img-element */}
 {camera&&<img src={camera.imageUrl} alt={`Ảnh ${active?.cam} cần duyệt`} className="mb-3 w-full rounded-vcf-control" onError={()=>setFailedImage(camera.imageUrl)} onLoad={()=>setFailedImage(null)}/>}
 {camera&&failedImage===camera.imageUrl&&<p role="status">Thiếu ảnh: {camera.imageUrl.split("/").pop()}</p>}
 {detail.data&&!camera&&<p>Ảnh camera không có trong job.</p>}
 <ContextPanel context={detail.data?.context} cam={active?.cam??"CAM_FRONT"}/></section></div>
 <div className="flex gap-4 text-sm"><button disabled={offset===0} onClick={()=>{setOffset(v=>Math.max(0,v-LIMIT));setActive(null);}}>Trang trước</button><span>Trang {offset/LIMIT+1}</span><button disabled={!queue.data||queue.data.items.length<LIMIT} onClick={()=>{setOffset(v=>v+LIMIT);setActive(null);}}>Trang sau</button></div>
 </main>;
}
