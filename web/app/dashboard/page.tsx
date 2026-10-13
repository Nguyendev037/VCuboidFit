"use client";

import { DashboardHeader } from '@/components/dashboard/DashboardHeader';
import { JobPicker } from '@/components/dashboard/JobPicker';
import { UploadPanel } from '@/components/dashboard/UploadPanel';
import { RunStatus } from '@/components/dashboard/RunStatus';
import { SelectionPlaceholder } from '@/components/dashboard/SelectionPlaceholder';
import { SelectionTable } from '@/components/dashboard/SelectionTable';
import { FilterBar } from '@/components/dashboard/FilterBar';
import { useDashboard } from '@/components/dashboard/useDashboard';

export default function Home() {
  const state = useDashboard();
  const { done, error, setError } = state;

  return (
    <div className="min-h-screen bg-[#F7F8FA] text-[#0F172A] flex flex-col font-sans">
      {/* 1. Header ứng dụng theo Figma (Screens 01 & 02) */}
      <DashboardHeader {...state} />

      {/* Thông báo lỗi nếu có */}
      {error && (
        <div className="max-w-[1440px] mx-auto px-4 sm:px-8 pt-4 w-full">
          <div role="alert" data-testid="error" className="p-3 bg-rose-50 border border-rose-200 text-rose-800 rounded-xl text-xs font-medium flex items-center justify-between gap-3">
            <span>{error}</span>
            <button type="button" aria-label="Đóng thông báo lỗi" onClick={() => setError("")} className="min-h-9 min-w-9 rounded text-rose-700 hover:bg-rose-100 font-bold focus-visible:outline focus-visible:outline-2 focus-visible:outline-rose-700">✕</button>
          </div>
        </div>
      )}

      {/* 2. Nội dung 2 cột: Cột trái (Quy trình 3 bước / Kết quả) & Cột phải (Panel Tinh chỉnh) */}
      <main className="max-w-[1440px] mx-auto p-4 sm:p-6 md:p-8 w-full grid grid-cols-1 lg:grid-cols-12 gap-6 flex-1 items-start">
        {/* ================= CỘT TRÁI (8 CỘT) ================= */}
        <div className="lg:col-span-8 flex flex-col gap-6">
          <JobPicker {...state} />
          {!done ? (
            // ============ GIAO DIỆN CHƯA CÓ KẾT QUẢ (FIGMA 01) ============
            <>
              {/* Bước 1: Nạp dữ liệu */}
              <UploadPanel {...state} />

              {/* Bước 2: Phân tích */}
              <RunStatus {...state} />

              {/* Bước 3: Kết quả placeholder */}
              <SelectionPlaceholder {...state} />
            </>
          ) : (
            // ============ GIAO DIỆN ĐÃ CÓ KẾT QUẢ (FIGMA 02) ============
            <SelectionTable {...state} />
          )}
        </div>

        {/* ================= CỘT PHẢI: BẢNG TINH CHỈNH (4 CỘT) ================= */}
        <FilterBar {...state} />
      </main>
    </div>
  );
}
