import React from "react";
import Link from "next/link";
export default function Home() {
 return <main className="min-h-screen bg-slate-50 text-slate-900">
 <nav className="mx-auto flex max-w-6xl justify-between p-6"><Link href="/" className="font-bold">VCuboidFIT</Link><Link href="/huong-dan">Hướng dẫn</Link></nav>
 <section className="mx-auto max-w-6xl px-6 py-20"><p className="text-sm font-semibold uppercase tracking-widest text-blue-700">LiDAR chưa gán nhãn · VRU · AEB</p><h1 className="mt-5 max-w-4xl text-4xl font-bold leading-tight sm:text-6xl">Tìm tình huống VRU hiếm để gán nhãn cho phanh khẩn cấp</h1><p className="mt-6 max-w-2xl text-lg text-slate-600">Từ point cloud đến lô frame đáng xem: ứng viên LiDAR, bối cảnh camera và quyết định cuối của người gán nhãn.</p><Link href="/dashboard" className="mt-8 inline-block rounded-lg bg-blue-600 px-6 py-3 font-semibold text-white">Vào dashboard</Link></section>
 <section className="mx-auto max-w-6xl px-6 pb-16"><h2 className="mb-6 text-2xl font-bold">Cách hoạt động v2</h2><div className="grid gap-5 md:grid-cols-3">{[
 ["01", "Ứng viên LiDAR", "Engine rare_v24 tìm ứng viên và chấm độ hiếm RHCIO. Thẻ dự đoán cần người gán nhãn xác nhận."],
 ["02", "Bối cảnh camera", "OpenCLIP + OpenCV đọc bốn trục: chiếu sáng, chói, ống kính, thời tiết. Ca chưa chắc vào hàng đợi người duyệt."],
 ["03", "Chọn đúng B và xuất ảnh hiếm", "Chọn lô theo ngân sách từ frame đủ điều kiện; xuất ZIP ảnh camera, LiDAR có sẵn và lý do chọn."],
 ].map(([n,title,body])=><article key={n} className="rounded-xl border border-slate-200 bg-white p-6"><p className="font-mono text-blue-700">{n}</p><h3 className="my-3 text-lg font-semibold">{title}</h3><p className="text-sm leading-relaxed text-slate-600">{body}</p></article>)}</div></section>
 <section className="mx-auto max-w-6xl px-6 pb-16"><h2 className="text-2xl font-bold">Số đo</h2><p className="mt-3 text-slate-600">Đang đo. Capture B là số đo chính, A là số đo phụ. Số mini chỉ minh hoạ; kết quả phụ thuộc pool dữ liệu.</p></section></main>;
}
