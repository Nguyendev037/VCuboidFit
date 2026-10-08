import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  // KHÔNG bật cacheComponents / partialPrefetching (mặc định của create-next-app):
  // cacheComponents xoá `export const dynamic`, mà SPEC-P01 Task 3 bắt buộc dynamic = "force-dynamic".
  // Xem plan.md "Câu hỏi mở" Q1.
  experimental: {
    // proxy.ts (mật khẩu demo) đệm body request tối đa 10 MB mặc định rồi CẮT phần dư;
    // chunk upload là 50 MB nên phải nâng trần lên 60 MB (SPEC-P01 Task 5).
    proxyClientMaxBodySize: "60mb",
  },
  turbopack: {
    rules: {
      "*.css": {
        loaders: ["@tailwindcss/turbopack"],
        as: "*.css",
      },
    },
  },
};

export default nextConfig;
