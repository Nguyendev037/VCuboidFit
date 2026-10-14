import React from "react";
import Link from "next/link";
import { ScanLine, Boxes, Camera, ListChecks, Archive } from "lucide-react";
import { Benchmark } from "@/components/home/Benchmark";
import { loadDemoBench } from "@/lib/server/demoBench";

// Re-read the static export on each request, including when it arrives after startup.
export const dynamic = "force-dynamic";

const steps = [
  { title: "LiDAR", icon: ScanLine, href: "/dashboard", body: "Nạp point cloud, ego pose và timestamp từ nuScenes." },
  { title: "Ứng viên RHCIO", icon: Boxes, href: "/review", body: "Engine rare_v24 chấm độ hiếm. Thẻ dự đoán cần người gán nhãn xác nhận." },
  { title: "Bối cảnh camera", icon: Camera, href: "/review/context", body: "OpenCLIP + OpenCV đọc chiếu sáng, chói, ống kính và thời tiết; ca chưa chắc cần người duyệt." },
  { title: "Chọn B", icon: ListChecks, href: "/dashboard", body: "Chọn đúng ngân sách từ frame đủ điều kiện." },
  { title: "Xuất ZIP", icon: Archive, href: "/review", body: "Xuất ảnh camera, LiDAR có sẵn và lý do chọn từ lô đang duyệt." },
] as const;

export default async function Home() {
  const { bench, figureUrl } = await loadDemoBench();
  return <main className="min-h-screen bg-vcf-bg text-vcf-text">
    <nav aria-label="Điều hướng chính" className="mx-auto flex max-w-6xl justify-between gap-4 p-6"><Link href="/" className="font-bold">VCuboidFIT</Link><Link href="/huong-dan" className="text-vcf-muted hover:text-vcf-accent">Hướng dẫn</Link></nav>
    <section className="mx-auto max-w-6xl px-6 py-16 sm:py-20">
      <p className="text-sm font-semibold uppercase tracking-widest text-vcf-accent-ink">LiDAR chưa gán nhãn · VRU · AEB</p>
      <h1 className="mt-5 max-w-4xl text-4xl font-bold leading-tight sm:text-6xl">Tìm tình huống VRU hiếm để gán nhãn cho phanh khẩn cấp</h1>
      <p className="mt-6 max-w-2xl text-lg text-vcf-muted">Từ point cloud đến lô frame đáng xem: ứng viên LiDAR, bối cảnh camera và quyết định cuối của người gán nhãn.</p>
      <Link href="/dashboard" className="mt-8 inline-block rounded-vcf-control bg-vcf-accent px-6 py-3 font-semibold text-vcf-on-accent hover:bg-vcf-accent-ink">Vào dashboard</Link>
      <Link href="/vi-sao" className="mt-4 block font-semibold text-vcf-accent-ink underline">Vì sao chọn chúng tôi</Link>
    </section>
    <section aria-labelledby="pipeline-title" className="mx-auto max-w-6xl px-6 pb-16">
      <h2 id="pipeline-title" className="mb-6 text-2xl font-bold">Chuỗi xử lý</h2>
      <ol className="grid gap-5 sm:grid-cols-2 lg:grid-cols-5">{steps.map(({ title, icon: Icon, href, body }, index) => <li key={title}>
        <Link href={href} className="block h-full rounded-vcf-card border border-vcf-border bg-vcf-surface p-5 hover:border-vcf-accent">
          <div className="flex items-center justify-between text-vcf-accent-ink"><Icon aria-hidden="true" size={24} /><span className="text-sm tabular-nums">0{index + 1}</span></div>
          <h3 className="my-3 text-lg font-semibold">{title}</h3><p className="text-sm leading-relaxed text-vcf-muted">{body}</p>
        </Link>
      </li>)}</ol>
    </section>
    <section aria-labelledby="benchmark-title" className="mx-auto max-w-6xl px-6 pb-16"><h2 id="benchmark-title" className="text-2xl font-bold">Số đo</h2><Benchmark bench={bench} figureUrl={figureUrl} /></section>
  </main>;
}
