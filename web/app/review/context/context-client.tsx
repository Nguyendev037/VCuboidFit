"use client";
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
 const queue=useQuery({queryKey:["context-review",job,offset],enabled:!!job,queryFn:async():Promise<ReviewQueue>=>{
   if(process.env.NEXT_PUBLIC_MOCK === "1" || window.sessionStorage.getItem("vcf-demo") === "1") return {items:[]};
   const response=await fetch(`/api/jobs/${encodeURIComponent(job!)}/review-queue?kind=context&offset=${offset}&limit=${LIMIT}`);
   if(!response.ok) throw new Error("Không tải được hàng đợi bối cảnh");
   return response.json();
 }});
 const detail=useQuery({queryKey:["context-review-frame",job,sid,active?.sampleToken],enabled:!!job&&!!sid&&!!active,queryFn:()=>getFrame(job!,active!.sampleToken,sid!)});
 const camera=detail.data?.cams.find(c=>c.cam===active?.cam);
 return <main className="mx-auto min-h-screen max-w-6xl space-y-5 bg-slate-50 p-6 text-slate-900"><Link href={job&&sid ? `/review/${encodeURIComponent(job)}?sel=${encodeURIComponent(sid)}` : "/dashboard"} className="text-blue-700">← Quay lại</Link><h1 className="text-2xl font-bold">Hàng đợi duyệt bối cảnh</h1><p className="text-sm">Xem ảnh, tín hiệu và lý do cần duyệt. Thẻ bối cảnh là dự đoán.</p>
 {!job && <p role="alert">Thiếu mã job. Mở hàng đợi từ dashboard.</p>}
 {queue.isPending&&job&&<p>Đang tải…</p>}{queue.isError&&<p role="alert">{queue.error.message}<button className="ml-3 underline" onClick={()=>void queue.refetch()}>Thử lại</button></p>}
 {queue.data?.items.length===0&&<p>Không có ảnh cần duyệt ở trang này.</p>}
 <div className="grid gap-6 md:grid-cols-2"><section className="space-y-2">{queue.data?.items.map(item=><button key={`${item.sampleToken}-${item.cam}`} className="block w-full rounded-lg border bg-white p-3 text-left text-sm" onClick={()=>setActive(item)}><strong>{item.cam} · {item.sampleToken.slice(0,8)}</strong>{item.reviewReasons.map(r=><p key={r}>{reviewReasonLabel(r)}</p>)}</button>)}</section><section>
 {active&&!sid&&<p role="alert">Thiếu selection để xem chi tiết.</p>}{detail.isFetching&&<p>Đang tải ảnh…</p>}{detail.isError&&<p role="alert">Không tải được chi tiết frame.</p>}
 {/* eslint-disable-next-line @next/next/no-img-element */}
 {camera&&<img src={camera.imageUrl} alt={`Ảnh ${active?.cam} cần duyệt`} className="mb-3 w-full rounded-lg"/>}
 {detail.data&&!camera&&<p>Ảnh camera không có trong job.</p>}
 <ContextPanel context={detail.data?.context} cam={active?.cam??"CAM_FRONT"}/></section></div>
 <div className="flex gap-4 text-sm"><button disabled={offset===0} onClick={()=>{setOffset(v=>Math.max(0,v-LIMIT));setActive(null);}}>Trang trước</button><span>Trang {offset/LIMIT+1}</span><button disabled={!queue.data||queue.data.items.length<LIMIT} onClick={()=>{setOffset(v=>v+LIMIT);setActive(null);}}>Trang sau</button></div>
 </main>;
}
