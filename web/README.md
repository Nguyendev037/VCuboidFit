# Web VCuboidFIT

Next.js 16 App Router, React 19, TypeScript, TanStack Query và three.js/react-three-fiber. Tailwind 4 được biên dịch qua Turbopack.

## Chạy từ thư mục web

```powershell
Copy-Item .env.example .env.local
npm ci
npm run dev
# Nếu npm shim lỗi: node node_modules/next/dist/bin/next dev
```

Web ở `http://localhost:3000`. Backend thật ở `http://127.0.0.1:8001`; chạy `model/scripts/dev_up.ps1` từ root repo trong terminal riêng. `.env.local` đặt `WORKER_URL=http://127.0.0.1:8001`, `WORKSPACE=../model/workspace`; workspace phải trùng backend.

## Các trang
- `/`: đề tài, mô phỏng 3D và góc nhìn sử dụng.
- `/dashboard`: dữ liệu, jobs, chọn lô và xuất kết quả.
- `/vi-sao`: phương pháp, số T có nguồn và giới hạn; không khẳng định hơn baseline.
- `/review/**`: Deep Review/viewer 3D và camera của job đã chạy.
- `/huong-dan`: hướng dẫn, thuật ngữ.

Không có worker vẫn xem nội dung giới thiệu/phương pháp/benchmark. `NEXT_PUBLIC_MOCK=1` chỉ để khám phá UI; media fixture phải dựng local vì `public/mock-media/` không commit. Script `node scripts/fetch-mock-media.mjs --from H:/ --frames 6` đọc dữ liệu nuScenes của bạn; không có nguồn thật thì chỉ sinh ảnh xám/cloud tổng hợp để kiểm UI.

## Kiểm tra

Sau khi dựng media mẫu:

```powershell
node node_modules/typescript/bin/tsc --noEmit
node node_modules/eslint/bin/eslint.js
node node_modules/vitest/vitest.mjs run
node node_modules/next/dist/bin/next build
```

Giữ build mặc định Turbopack; webpack chưa có pipeline Tailwind tương đương. E2E cần đúng job local và backend; job `full_mini/m2_mini/night_v24` đã bị người dùng xoá ngày 14/10/2026, không tự có sau clone. `demo-flow` A6 dừng backend, tránh chạy khi đang dùng dịch vụ.

Đọc [web docs](../docs/web.md), [chạy local](../docs/run-local.md), [tiến độ](../docs/project-status.md), [hướng dẫn agent](AGENTS.md).
