import React from "react";
import { ReviewPerspective } from "@/components/landing/ReviewPerspective";
import type { Metadata } from "next";
import { TOPIC_TITLE } from "@/lib/topic";
import Link from "next/link";
import type { CSSProperties } from "react";
import { ArrowRight, Camera, Layers, ScanLine, Waypoints } from "lucide-react";
import { LiveShowcase } from "@/components/landing/LiveShowcase";
import { LandingHero } from "@/components/landing/LandingHero";

export const metadata: Metadata = {
  title: "VCuboidFIT — Giới thiệu đề tài",
  description: TOPIC_TITLE,
};

const EYEBROW_TONE = { blue: "text-blue-700", emerald: "text-emerald-700" } as const;

function SectionHead({ id, eyebrow, title, tone }: { id: string; eyebrow: string; title: string; tone: keyof typeof EYEBROW_TONE }) {
  return (
    <div className="mx-auto flex max-w-3xl flex-col items-center gap-3 text-center">
      <p className={`font-data text-xs font-medium uppercase tracking-[0.14em] ${EYEBROW_TONE[tone]}`}>{eyebrow}</p>
      <h2 id={id} className="font-display text-balance text-3xl font-semibold leading-tight text-slate-900 sm:text-4xl">{title}</h2>
    </div>
  );
}

const STATS = [
  { value: "VRU", label: "Trọng tâm đề tài", text: "Người đi bộ, xe đạp, xe máy: nhóm dễ tổn thương khi xe phanh khẩn cấp (AEB)." },
  { value: "LiDAR", label: "Ứng viên từ point cloud", text: "Engine rare_v24 tìm ứng viên và chấm độ hiếm; nhãn dành riêng cho đánh giá." },
  { value: "CPU", label: "Bước chọn chạy local", text: "Chọn lô frame theo ngân sách trên CPU. Lưu dữ liệu dưới dạng file, không cần cơ sở dữ liệu." },
  { value: "CLIP", label: "Bối cảnh camera", text: "OpenCLIP pretrained kết hợp OpenCV để đọc bối cảnh; không dùng VLM." },
];
const FEATURES = [
  { icon: ScanLine, title: "Engine rare_v24", text: "Từ ứng viên LiDAR đến độ hiếm RHCIO và lô frame cần xem. Thẻ dự đoán là gợi ý, cần người gán nhãn xác nhận.", tag: "RHCIO · LiDAR", badge: "ỨNG VIÊN" },
  { icon: Waypoints, title: "Tầng 1: PointPillars đã train", text: "Detector 3D train trên nuScenes trainval, epoch 12/20: mAP 0,220 · NDS 0,343 trên 602 frame VAL. Chưa gắn vào benchmark T, nên benchmark T hiện tại vẫn chưa chứng minh vượt baseline.", tag: "PointPillars · e12", badge: "ĐÃ ĐO" },
  { icon: Layers, title: "Chọn lô theo ngân sách", text: "Chọn frame đủ điều kiện theo ngân sách và mức đa dạng; giữ lý do chọn để người gán nhãn kiểm tra trước khi xuất.", tag: "Ngân sách · đa dạng", badge: "NGƯỜI DUYỆT" },
  { icon: Camera, title: "Deep Review 3D & bối cảnh", text: "Xem point cloud, hộp 3D và sáu camera. OpenCLIP + OpenCV bổ sung bối cảnh chiếu sáng, chói, ống kính và thời tiết; ca chưa chắc cần người duyệt.", tag: "6 camera · LiDAR · OpenCLIP", badge: "KIỂM TRA TAY" },
];
const STEPS = [
  { n: "01", title: "Nạp dữ liệu nuScenes", text: "Nạp point cloud, ego pose, timestamp và ảnh camera. Kiểm tra cấu trúc dữ liệu trước khi phân tích; có dữ liệu mẫu để khám phá giao diện." },
  { n: "02", title: "Phân tích và chọn lô", text: "Engine rare_v24 tìm ứng viên, chấm độ hiếm và chọn theo ngân sách. OpenCLIP + OpenCV bổ sung bối cảnh camera, không dùng VLM." },
  { n: "03", title: "Kiểm tra và xuất ZIP", text: "Xem frame, đối chiếu LiDAR với camera và lý do chọn. Xuất ZIP ảnh camera, LiDAR có sẵn và lý do chọn từ lô đang duyệt." },
];

export const dynamic = "force-dynamic";

export default async function IntroPage() {
  return (
    <div className="vcf-hud relative flex min-h-screen flex-col font-sans [--font-space-grotesk:var(--font-landing-sans)]">
      <div className="hud-ambient" aria-hidden="true" />
      <div className="relative z-10 flex min-h-screen flex-col">
        <LandingHero />

        <main className="mx-auto flex w-full max-w-7xl flex-1 flex-col gap-28 px-4 pb-16 pt-16 sm:px-6">
          {/* Mô phỏng 3D thật (dùng LidarScene của dự án) */}
          <section id="mo-phong" aria-labelledby="sim-title" className="reveal flex scroll-mt-24 flex-col gap-4" style={{ "--d": "300ms" } as CSSProperties}>
            <div>
              <p className="font-data text-xs font-medium uppercase tracking-[0.14em] text-emerald-600">Mô phỏng 3D</p>
              <h2 id="sim-title" className="font-display mt-2 text-3xl font-semibold text-slate-900">Frame hiếm được chọn, nhìn trong không gian 3D</h2>
            </div>
            <LiveShowcase />
          </section>

          {/* Chỉ số: một dải bốn ô liền khối, ngăn cách bằng đường mảnh */}
          <section aria-labelledby="stats-title" className="mx-auto flex w-full max-w-6xl flex-col gap-10">
            <SectionHead id="stats-title" eyebrow="Điểm nhấn" title="Gọn, rõ và chạy được ngay trên máy thường" tone="blue" />
            <div className="hud-card overflow-hidden">
              <dl className="grid grid-cols-1 gap-px bg-slate-200 sm:grid-cols-2 lg:grid-cols-4">
                {STATS.map((st, i) => (
                  <div key={st.label} className={`flex flex-col gap-2 bg-white p-7 ${i === 0 ? "bg-gradient-to-b from-sky-50 to-white" : ""}`}>
                    <dd className="font-display order-1 text-5xl font-semibold leading-none text-slate-900">{st.value}</dd>
                    <dt className="font-display order-2 mt-1 text-base font-semibold text-slate-900">{st.label}</dt>
                    <p className="order-3 text-[15px] leading-7 text-slate-600">{st.text}</p>
                  </div>
                ))}
              </dl>
            </div>
          </section>

          {/* Tính năng: biểu tượng bên trái, nội dung bên phải, nhãn nằm dưới tiêu đề */}
          <section id="tinh-nang" aria-labelledby="feat-title" className="mx-auto flex w-full max-w-6xl scroll-mt-24 flex-col gap-10">
            <SectionHead id="feat-title" eyebrow="Công nghệ" title="Bộ công cụ tuyển chọn cho dữ liệu LiDAR" tone="emerald" />
            <div className="grid gap-6 md:grid-cols-2">
              {FEATURES.map(({ icon: Icon, title, text, badge }) => (
                <article key={title} className="hud-card hud-card-lift flex flex-col gap-4 p-6 sm:flex-row sm:gap-5 sm:p-7">
                  <span className="flex h-12 w-12 shrink-0 items-center justify-center rounded-xl bg-blue-50 text-blue-600 ring-1 ring-blue-500/25">
                    <Icon className="h-6 w-6" aria-hidden="true" />
                  </span>
                  <div className="flex min-w-0 flex-col gap-2">
                    <h3 className="font-display text-xl font-semibold leading-snug text-slate-900">{title}</h3>
                    <span className="font-data w-fit rounded bg-emerald-50 px-2 py-0.5 text-xs font-medium uppercase tracking-wider text-emerald-700">{badge}</span>
                    <p className="mt-1 text-[15px] leading-7 text-slate-600">{text}</p>
                  </div>
                </article>
              ))}
            </div>
          </section>

          {/* Quy trình: dòng thời gian có số thứ tự và đường nối */}
          <section id="quy-trinh" aria-labelledby="flow-title" className="mx-auto flex w-full max-w-6xl scroll-mt-24 flex-col gap-10">
            <SectionHead id="flow-title" eyebrow="Quy trình" title="Ba bước từ dữ liệu thô đến danh sách gán nhãn" tone="blue" />
            <ol className="relative grid gap-8 lg:grid-cols-3 lg:gap-6">
              <span aria-hidden className="absolute left-[16.66%] right-[16.66%] top-7 hidden h-0.5 rounded bg-gradient-to-r from-sky-300 via-sky-500 to-emerald-400 lg:block" />
              {STEPS.map((st) => (
                <li key={st.n} className="relative flex flex-col items-center">
                  <span className="font-display relative z-10 flex h-14 w-14 items-center justify-center rounded-full bg-blue-600 text-lg font-semibold text-white shadow-md ring-8 ring-[#f4f7fb]">{st.n}</span>
                  <div className="hud-card hud-card-lift mt-5 flex w-full flex-1 flex-col gap-2 p-6">
                    <h3 className="font-display text-xl font-semibold leading-snug text-slate-900">{st.title}</h3>
                    <p className="text-[15px] leading-7 text-slate-600">{st.text}</p>
                  </div>
                </li>
              ))}
            </ol>
          </section>

          <ReviewPerspective />

          {/* Kêu gọi hành động: dải tối, tương phản mạnh với phần còn lại */}
          <section aria-labelledby="cta-title" className="mx-auto w-full max-w-6xl">
            <div className="relative overflow-hidden rounded-2xl bg-gradient-to-br from-slate-900 via-slate-800 to-sky-900 px-6 py-14 text-center text-white shadow-xl sm:px-14 sm:py-16">
              <div aria-hidden className="pointer-events-none absolute -left-24 -top-24 h-72 w-72 rounded-full bg-sky-500/25 blur-3xl" />
              <div aria-hidden className="pointer-events-none absolute -bottom-24 -right-16 h-72 w-72 rounded-full bg-emerald-400/20 blur-3xl" />
              <div className="relative mx-auto flex max-w-2xl flex-col items-center gap-5">
                <p className="font-data text-xs font-medium uppercase tracking-[0.14em] text-sky-300">Bắt đầu</p>
                <h2 id="cta-title" className="font-display text-balance text-3xl font-semibold leading-tight sm:text-4xl">Sẵn sàng chọn frame đáng gán nhãn từ dữ liệu của bạn?</h2>
                <p className="text-balance text-base leading-7 text-slate-300">
                  Nạp bộ nuScenes, bấm chạy phân tích và nhận danh sách frame tiêu biểu. Chưa có dữ liệu? Mở bộ dữ liệu mẫu ngay trong Dashboard.
                </p>
                <div className="mt-2 flex flex-col items-stretch gap-3 sm:flex-row sm:items-center">
                  <Link href="/dashboard" className="inline-flex min-h-12 items-center justify-center gap-2 rounded-full bg-white px-8 text-base font-semibold text-slate-900 transition hover:bg-sky-50 active:scale-[0.98]">
                    Bắt đầu phân tích
                    <ArrowRight className="h-4 w-4" aria-hidden="true" />
                  </Link>
                  <Link href="/huong-dan" className="inline-flex min-h-12 items-center justify-center rounded-full px-8 text-base font-medium text-white ring-1 ring-white/35 transition hover:bg-white/10 active:scale-[0.98]">
                    Xem hướng dẫn và thuật ngữ
                  </Link>
                </div>
              </div>
            </div>
          </section>
        </main>

        <footer className="border-t border-slate-200 px-4 py-5 text-center text-xs text-slate-500">
          VCuboidFIT · Ảnh và LiDAR nuScenes / Motional · CC BY-NC-SA 4.0 · phi thương mại
        </footer>
      </div>
    </div>
  );
}
