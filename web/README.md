# web/ - giao diện VCuboidFIT

Next.js 16 (App Router) + React 19, TanStack Query, three.js (xem LiDAR 3D), Tailwind 4 + shadcn.

```powershell
copy .env.example .env.local     # chỉnh WORKER_URL / WORKSPACE nếu cần
npm ci
npm run dev                      # http://localhost:3000
npx tsc --noEmit ; npx vitest run
```

Biến môi trường (đọc từ `lib/server/*.ts`, `lib/api/client.ts`): `WORKER_URL`, `WORKSPACE`,
`MAX_UPLOAD_GB`, `NEXT_PUBLIC_MOCK`. Hướng dẫn đầy đủ: [../docs/run-local.md](../docs/run-local.md).
