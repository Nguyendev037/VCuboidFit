import React from "react";
import Link from "next/link";
import { ArrowRight, Check, MessageSquare } from "lucide-react";

const CRITERIA = [
  { role: "Người gán nhãn", title: "Biết vì sao frame được chọn", text: "Đọc lý do chọn, xem hộp 3D và đối chiếu camera trước khi xác nhận." },
  { role: "Nhóm phát triển", title: "Đưa kết quả vào công việc", text: "Chọn theo ngân sách, kiểm tra lô frame và xuất ZIP để tiếp tục quy trình gán nhãn." },
  { role: "Người đánh giá", title: "Có số liệu để kiểm tra lại", text: "Xem phương pháp, dữ liệu nguồn và khoảng tin cậy để hiểu cả kết quả lẫn giới hạn." },
] as const;

export function ReviewPerspective() {
  return (
    <section aria-labelledby="review-title" className="mx-auto w-full max-w-6xl">
      <div className="grid overflow-hidden rounded-3xl border border-slate-200 bg-white shadow-sm lg:grid-cols-[0.9fr_1.1fr]">
        <div className="flex flex-col justify-between gap-8 bg-sky-50 p-7 sm:p-10">
          <div>
            <MessageSquare className="h-9 w-9 text-sky-700" aria-hidden="true" />
            <p className="mt-6 text-sm font-semibold uppercase tracking-widest text-sky-800">Góc nhìn người sử dụng</p>
            <h2 id="review-title" className="mt-4 font-[family-name:var(--font-landing-serif)] text-4xl leading-tight text-slate-900 sm:text-5xl">Chất lượng nằm ở từng quyết định dễ kiểm tra.</h2>
            <p className="mt-5 text-lg leading-8 text-slate-700">Một lô frame hữu ích cần giúp bạn hiểu, kiểm tra và tiếp tục công việc gán nhãn.</p>
          </div>
          <p className="text-sm leading-6 text-slate-600">Đây là các tiêu chí đánh giá trải nghiệm; chưa phải lời chứng thực từ người dùng.</p>
        </div>
        <div className="p-7 sm:p-10">
          <ul className="divide-y divide-slate-200">
            {CRITERIA.map(({ role, title, text }) => (
              <li key={role} className="py-6 first:pt-0">
                <p className="text-sm font-semibold text-sky-800">{role}</p>
                <h3 className="mt-2 flex items-start gap-3 text-xl font-semibold leading-snug text-slate-900"><Check className="mt-1 h-5 w-5 shrink-0 text-emerald-700" aria-hidden="true" />{title}</h3>
                <p className="mt-3 text-base leading-7 text-slate-600">{text}</p>
              </li>
            ))}
          </ul>
          <Link href="/vi-sao#phuong-phap" className="inline-flex min-h-12 items-center gap-2 text-base font-semibold text-sky-800 underline underline-offset-4">Xem cách chúng tôi kiểm chứng<ArrowRight className="h-4 w-4" aria-hidden="true" /></Link>
        </div>
      </div>
    </section>
  );
}
