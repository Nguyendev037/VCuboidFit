import React from "react";
import Link from "next/link";
import { GT_GROUPS, METRICS, SETTINGS, RARITY_CONCEPTS } from "@/lib/glossary";
import { ArrowLeft } from "lucide-react";

export default function GuidePage() {
  return (
    <div className="min-h-screen bg-[#F7F8FA] text-[#0F172A] flex flex-col font-sans">
      <header className="w-full bg-white border-b border-[#E2E8F0] px-4 sm:px-8 py-3.5 flex flex-wrap items-center justify-between gap-3 shadow-xs sticky top-0 z-40">
        <div className="flex items-center gap-6">
          <Link href="/" className="flex items-center gap-2.5 font-bold text-sm text-slate-600 hover:text-blue-600 transition-colors">
            <ArrowLeft size={18} />
            <span>Về trang chủ</span>
          </Link>
          <div className="hidden sm:block border-l border-slate-200 h-6" />
          <div className="flex items-center gap-2.5 font-bold text-lg text-slate-900 tracking-tight">
            <div className="w-7 h-7 rounded-lg bg-blue-600 flex items-center justify-center text-white shadow-xs">
              <svg className="w-4 h-4" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5">
                <path d="M21 16V8a2 2 0 0 0-1-1.73l-7-4a2 2 0 0 0-2 0l-7 4A2 2 0 0 0 3 8v8a2 2 0 0 0 1 1.73l7 4a2 2 0 0 0 2 0l7-4A2 2 0 0 0 21 16z" />
                <polyline points="3.27 6.96 12 12.01 20.73 6.96" />
                <line x1="12" y1="22.08" x2="12" y2="12" />
              </svg>
            </div>
            <span>VCuboidFIT Hướng Dẫn</span>
          </div>
        </div>
      </header>

      <main className="max-w-[1440px] mx-auto p-4 sm:p-6 md:p-8 w-full flex flex-col md:flex-row gap-6 lg:gap-12 flex-1 items-start">
        {/* TOC Sidebar */}
        <aside className="w-full md:w-64 lg:w-72 shrink-0 md:sticky md:top-[100px] bg-white rounded-xl border border-[#E2E8F0] shadow-xs p-4">
          <h3 className="font-bold text-slate-900 mb-3 text-sm">Nội dung hướng dẫn</h3>
          <nav className="flex flex-col gap-2 text-sm">
            <a href="#tong-quan" className="text-slate-600 hover:text-blue-600 font-medium transition-colors">1. VCuboidFIT làm gì?</a>
            <a href="#hai-loai-hiem" className="text-slate-600 hover:text-blue-600 font-medium transition-colors">2. Hai loại hiếm</a>
            <a href="#nhom-gt" className="text-slate-600 hover:text-blue-600 font-medium transition-colors">3. Nhóm hiếm theo nhãn</a>
            <a href="#chi-so" className="text-slate-600 hover:text-blue-600 font-medium transition-colors">4. Chỉ số đánh giá</a>
            <a href="#tham-so" className="text-slate-600 hover:text-blue-600 font-medium transition-colors">5. Tham số nâng cao</a>
            <a href="#faq" className="text-slate-600 hover:text-blue-600 font-medium transition-colors">6. FAQ</a>
          </nav>
        </aside>

        {/* Content */}
        <div className="flex-1 max-w-4xl flex flex-col gap-10 pb-20">
          <div>
            <h1 className="text-3xl font-bold text-slate-900 tracking-tight">Cẩm nang & Bảng thuật ngữ</h1>
            <p className="text-slate-500 mt-2 text-sm">Tài liệu chi tiết giúp bạn hiểu rõ các chỉ số đánh giá và cơ chế lọc frame của VCuboidFIT.</p>
          </div>

          <section id="tong-quan" className="scroll-mt-24">
            <h2 className="text-xl font-bold text-slate-900 border-b border-slate-200 pb-2 mb-4">1. VCuboidFIT làm gì?</h2>
            <div className="grid grid-cols-1 sm:grid-cols-3 gap-4">
              <div className="bg-white p-5 rounded-xl border border-slate-200 shadow-xs flex flex-col items-center text-center">
                <div className="w-12 h-12 rounded-full bg-blue-50 text-blue-600 flex items-center justify-center mb-4">
                  <svg className="w-6 h-6" fill="none" stroke="currentColor" viewBox="0 0 24 24" strokeWidth="2"><path d="M4 7v10c0 2.21 3.58 4 8 4s8-1.79 8-4V7M4 7c0 2.21 3.58 4 8 4s8-1.79 8-4M4 7c0-2.21 3.58-4 8-4s8 1.79 8 4" strokeLinecap="round" strokeLinejoin="round"/></svg>
                </div>
                <h3 className="font-bold text-slate-800 text-sm mb-2">1. Nạp dữ liệu</h3>
                <p className="text-xs text-slate-500">Đọc hàng vạn frame từ dataset chưa được gán nhãn.</p>
              </div>
              <div className="bg-white p-5 rounded-xl border border-slate-200 shadow-xs flex flex-col items-center text-center">
                <div className="w-12 h-12 rounded-full bg-indigo-50 text-indigo-600 flex items-center justify-center mb-4">
                  <svg className="w-6 h-6" fill="none" stroke="currentColor" viewBox="0 0 24 24" strokeWidth="2"><path d="M2 12h4l3-9 5 18 3-9h5" strokeLinecap="round" strokeLinejoin="round"/></svg>
                </div>
                <h3 className="font-bold text-slate-800 text-sm mb-2">2. Đánh giá độ hiếm</h3>
                <p className="text-xs text-slate-500">So sánh hình dạng 3D để tìm ra các frame bất thường nhất.</p>
              </div>
              <div className="bg-white p-5 rounded-xl border border-slate-200 shadow-xs flex flex-col items-center text-center">
                <div className="w-12 h-12 rounded-full bg-emerald-50 text-emerald-600 flex items-center justify-center mb-4">
                  <svg className="w-6 h-6" fill="none" stroke="currentColor" viewBox="0 0 24 24" strokeWidth="2"><path d="M5 13l4 4L19 7" strokeLinecap="round" strokeLinejoin="round"/></svg>
                </div>
                <h3 className="font-bold text-slate-800 text-sm mb-2">3. Trích xuất 5%</h3>
                <p className="text-xs text-slate-500">Chọn 5% frame giá trị nhất để bạn gửi đi gán nhãn.</p>
              </div>
            </div>
          </section>

          <section id="hai-loai-hiem" className="scroll-mt-24">
            <h2 className="text-xl font-bold text-slate-900 border-b border-slate-200 pb-2 mb-4">2. Hai loại &quot;hiếm&quot; — Đừng nhầm lẫn</h2>
            <div className="bg-amber-50 border border-amber-200 rounded-xl p-5 mb-4">
              <p className="text-sm text-amber-900 font-medium">
                Thông điệp cốt lõi: <strong>Model chọn bằng &quot;độ hiếm ước lượng&quot;; hệ thống đánh giá bằng &quot;hiếm thật theo nhãn&quot;.</strong>
              </p>
            </div>
            <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
              <div className="bg-white p-5 rounded-xl border border-slate-200 shadow-xs">
                <div className="flex items-center gap-2 mb-3">
                  <span className="w-3 h-3 rounded-full bg-blue-500"></span>
                  <h3 className="font-bold text-slate-800">{RARITY_CONCEPTS.rare_est.label}</h3>
                </div>
                <p className="text-sm text-slate-600 mb-2">{RARITY_CONCEPTS.rare_est.tooltip}</p>
                <p className="text-xs text-slate-500 bg-slate-50 p-3 rounded-lg">{RARITY_CONCEPTS.rare_est.detail}</p>
              </div>
              <div className="bg-white p-5 rounded-xl border border-slate-200 shadow-xs">
                <div className="flex items-center gap-2 mb-3">
                  <span className="w-3 h-3 rounded-full bg-emerald-500"></span>
                  <h3 className="font-bold text-slate-800">{RARITY_CONCEPTS["rare (cell)"].label}</h3>
                </div>
                <p className="text-sm text-slate-600 mb-2">{RARITY_CONCEPTS["rare (cell)"].tooltip}</p>
                <p className="text-xs text-slate-500 bg-slate-50 p-3 rounded-lg">{RARITY_CONCEPTS["rare (cell)"].detail}</p>
              </div>
            </div>
          </section>

          <section id="nhom-gt" className="scroll-mt-24">
            <h2 className="text-xl font-bold text-slate-900 border-b border-slate-200 pb-2 mb-4">3. Nhóm hiếm theo nhãn (Ground Truth)</h2>
            <div className="bg-white rounded-xl border border-slate-200 shadow-xs overflow-hidden">
              <table className="w-full text-left text-sm">
                <thead className="bg-slate-50 text-slate-600 text-xs uppercase font-bold">
                  <tr>
                    <th className="px-5 py-3 w-1/3">Tên nhóm</th>
                    <th className="px-5 py-3">Chi tiết & Đối tượng</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-slate-100">
                  {Object.entries(GT_GROUPS).map(([key, item]) => (
                    <tr key={key} className="hover:bg-slate-50/50">
                      <td className="px-5 py-4 font-semibold text-slate-800 align-top">
                        {item.label}
                        <div className="font-mono text-xs text-slate-400 mt-1 font-normal">{key}</div>
                      </td>
                      <td className="px-5 py-4 text-slate-600 leading-relaxed">
                        {item.tooltip}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </section>

          <section id="chi-so" className="scroll-mt-24">
            <h2 className="text-xl font-bold text-slate-900 border-b border-slate-200 pb-2 mb-4">4. Các chỉ số đánh giá (Metrics)</h2>
            <p className="text-sm text-slate-600 mb-4">Các chỉ số này chỉ có khi dataset được cung cấp kèm nhãn 3D. Chúng dùng để đánh giá độ hiệu quả của phương pháp so với lấy mẫu ngẫu nhiên.</p>
            <div className="bg-white rounded-xl border border-slate-200 shadow-xs overflow-hidden">
              <table className="w-full text-left text-sm">
                <thead className="bg-slate-50 text-slate-600 text-xs uppercase font-bold">
                  <tr>
                    <th className="px-4 py-3">Chỉ số</th>
                    <th className="px-4 py-3">Ý nghĩa</th>
                    <th className="px-4 py-3">Cách đọc & Đánh giá</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-slate-100">
                  {Object.entries(METRICS).map(([key, item]) => (
                    <tr key={key} className="hover:bg-slate-50/50">
                      <td className="px-4 py-3 font-semibold text-slate-800 align-top">
                        {item.label}
                      </td>
                      <td className="px-4 py-3 text-slate-600 align-top">
                        {item.tooltip}
                      </td>
                      <td className="px-4 py-3 text-slate-500 align-top bg-slate-50/30 text-xs">
                        {item.howToRead || "—"}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
            <div className="mt-4 p-4 bg-blue-50 border border-blue-100 rounded-lg text-sm text-blue-900">
              <strong>Ví dụ thực tế:</strong> Nếu bộ dữ liệu có 10,000 frame, budget 5% nghĩa là chọn 500 frame. 
              Nếu trong 10,000 frame đó có tổng cộng 1,000 frame hiếm thật (is_rare=True), và trong 500 frame bạn chọn được 200 frame hiếm:
              <ul className="list-disc pl-5 mt-2 space-y-1">
                <li><strong>Recall</strong> = 200 / 1,000 = 20%</li>
                <li><strong>Ngẫu nhiên kỳ vọng</strong> = 5% (hoặc ~50 frame)</li>
                <li><strong>Uplift</strong> = 20% / 5% = 4x (Tốt gấp 4 lần chọn ngẫu nhiên)</li>
                <li><strong>Precision</strong> = 200 / 500 = 40%</li>
              </ul>
            </div>
          </section>

          <section id="tham-so" className="scroll-mt-24">
            <h2 className="text-xl font-bold text-slate-900 border-b border-slate-200 pb-2 mb-4">5. Tham số Nâng cao</h2>
            <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
              {Object.entries(SETTINGS).map(([key, item]) => (
                <div key={key} className="bg-white p-4 rounded-xl border border-slate-200 shadow-xs">
                  <h3 className="font-bold text-slate-800 mb-1">{item.label}</h3>
                  <div className="font-mono text-xs text-slate-400 mb-2">{key}</div>
                  <p className="text-sm text-slate-600 leading-relaxed">{item.tooltip}</p>
                </div>
              ))}
            </div>
          </section>

          <section id="faq" className="scroll-mt-24">
            <h2 className="text-xl font-bold text-slate-900 border-b border-slate-200 pb-2 mb-4">6. Câu hỏi thường gặp (FAQ)</h2>
            <div className="space-y-4">
              <div className="bg-white p-5 rounded-xl border border-slate-200 shadow-xs">
                <h3 className="font-bold text-slate-800 mb-2">Vì sao Recall lại bằng 0% dù có frame hiếm?</h3>
                <p className="text-sm text-slate-600">Nếu Recall = 0%, có nghĩa là tập 5% frame bạn trích xuất được hoàn toàn không &quot;trúng&quot; frame nào chứa vật thể hiếm theo nhãn. Điều này thường do chiến lược chọn quá tập trung vào các đặc trưng hình học khác, hoặc frame hiếm quá ít. Lời khuyên: Hãy thử đổi tham số <strong className="font-medium text-slate-900">Ưu tiên khi chọn (lam)</strong> thiên về &quot;Đa dạng nhất&quot;.</p>
              </div>
              <div className="bg-white p-5 rounded-xl border border-slate-200 shadow-xs">
                <h3 className="font-bold text-slate-800 mb-2">Vì sao Nhóm C (Khó nhìn bằng cảm biến) lại rất rộng?</h3>
                <p className="text-sm text-slate-600">Nhóm C bao gồm các vật ở xa (&gt; 40 m) với rất ít điểm LiDAR. Trên thực tế, hầu như cảnh nào cũng có một vài vật thể ở xa rìa lọt vào tầm quét, do đó nhóm C chiếm tỉ lệ rất cao trong bộ dữ liệu, khiến việc đánh giá &quot;độ hiếm&quot; của nhóm này trở nên không còn ý nghĩa. Hiện nhóm này đang được lên kế hoạch tinh chỉnh lại định nghĩa.</p>
              </div>
              <div className="bg-white p-5 rounded-xl border border-slate-200 shadow-xs">
                <h3 className="font-bold text-slate-800 mb-2">Điều gì xảy ra nếu dataset không có nhãn 3D?</h3>
                <p className="text-sm text-slate-600">VCuboidFIT vẫn phân tích độ hiếm bằng điểm hình học của LiDAR (thuật toán không giám sát). Tuy nhiên, các chỉ số đánh giá bằng nhãn như Recall, Uplift hay Coverage sẽ bị ẩn đi, vì hệ thống không có cách nào biết đâu là &quot;hiếm thật&quot; để chấm điểm.</p>
              </div>
            </div>
          </section>
        </div>
      </main>
    </div>
  );
}
