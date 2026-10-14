# Website VCuboidFIT

Đợt docs 0.6.8, 14/10/2026. Hướng dẫn tính năng bên dưới mô tả code; snapshot runtime/test có thời điểm đo riêng, không đi kèm clone. Báo cáo đã làm/giới hạn/bước tiếp ở [project-status](project-status.md).

## Trang và nguồn dữ liệu

| Route | Mục đích | Nguồn |
|---|---|---|
| `/` | Giới thiệu đề tài, mô phỏng 3D, quy trình và góc nhìn sử dụng | `web/lib/topic.ts`, `web/components/landing/`, job hoàn tất gần nhất hoặc sáu fixture `mock-f01..06` |
| `/vi-sao` | Chi phí, phương pháp M0–M3, số đo T, tính minh bạch và giới hạn | `web/components/why/`, `web/lib/server/demoBench.ts`, `web/public/demo/bench_pitch.json` |
| `/dashboard` | Nạp dữ liệu và chọn lô theo ngân sách | Worker qua `/api/**` |
| `/review/**` | Deep Review, phân tích và xem frame 3D | Job/selection từ worker |
| `/huong-dan` | Hướng dẫn và thuật ngữ | Nội dung tĩnh |

`/vi-sao#phuong-phap` giải thích M0 Random, M1 Legacy Tầng 0, M2 `rare_v24` LiDAR và M3 đa cảm biến. Phần này mô tả giá trị vận hành: lý do chọn đi cùng frame, người gán nhãn đối chiếu 3D/camera rồi xuất lô đã kiểm tra. Phép kiểm chứng dùng cùng pool/ngân sách B, IY theo capture B và khoảng tin cậy CI95 từ bootstrap theo scene.

`/vi-sao#bang-chung` hiển thị số nguồn và kết luận chính. Kết quả T hiện tại **chưa chứng minh lợi ích hơn baseline**; không suy diễn giá trị vận hành thành thắng benchmark. JSON thiếu/hỏng hiển thị trạng thái rỗng; hình không có thì bỏ hình. Không gõ cứng lại các số T trong component.

Trang chủ dùng `ReviewPerspective` thay khối benchmark. Ba góc nhìn là **tiêu chí đánh giá trải nghiệm**, chưa phải lời chứng thực. Không thêm tên khách hàng, điểm sao hoặc lời khen chưa có nguồn.

## Font và bố cục

Next.js 16 App Router, React 19, Tailwind 4 qua loader Turbopack. Font Be Vietnam Pro cho phần giới thiệu, Newsreader cho tiêu đề mục, Inter cho giao diện ứng dụng; khai báo ở `web/app/layout.tsx`. Chữ trong các thẻ `/vi-sao` 16–18 px, tiêu đề thẻ khoảng 20 px, tiêu đề mục 30–48 px theo viewport. Nhãn phụ và hash nhỏ hơn; hash dài phải ngắt được trên mobile.

`MethodsSection` dùng nền tối và khối nhấn xanh nhạt để phân biệt mốc đối chiếu với hướng tiếp cận VCuboidFIT. Typography/layout đã kiểm ở 1440 px và 390 px, không tràn ngang.

## Media mẫu sau clone

Hotfix 0.6.9: mô phỏng **trang chủ** dùng bộ media được commit tại `web/public/demo/showcase/` (46 ảnh/thumbnail/cloud, khoảng 3,3 MB), kèm manifest SHA256 và ghi nguồn nuScenes/Motional CC BY-NC-SA 4.0. `LiveShowcase` đổi URL fixture sang bộ này; clone mới không còn phụ thuộc `public/mock-media/` để xem mô phỏng. Điểm số/hộp từ fixture chỉ minh hoạ, không phải kết quả benchmark. Mọi job thật vẫn dùng media của worker như trước.

Ảnh hero và dữ liệu benchmark/figure được commit. `web/public/mock-media/` được gitignore và **không commit** theo quy định repo; sáu fixture tham chiếu ảnh camera, thumbnail và LiDAR trong thư mục đó. Muốn mô phỏng mẫu đầy đủ, dựng media trước từ dữ liệu nuScenes trên máy:

```powershell
cd web
node scripts/fetch-mock-media.mjs --from H:/ --frames 6
```

Thay `H:/` bằng thư mục có dữ liệu nuScenes. Script chỉ đọc nguồn và ghi vào `public/mock-media/`. Nếu không tìm thấy dữ liệu thật, script tạo ảnh xám/point cloud tổng hợp: chỉ dùng để kiểm giao diện, không dùng làm minh chứng dữ liệu thật. Dữ liệu nuScenes thuộc Motional, CC BY-NC-SA 4.0; giữ nguồn và giới hạn phi thương mại.

`LiveShowcase` ưu tiên job đã hoàn tất từ worker, kiểm media bằng HEAD trước khi mở frame thật và giới hạn nạp 8 giây. Thiếu worker thì dùng fixture cùng media showcase đóng gói sẵn. Media thiếu ở job thật thì thử frame tiếp theo; không còn frame hợp lệ thì hiển thị trạng thái rỗng.

## Chạy và kiểm tra

## Panel Tinh chỉnh và tải dữ liệu

Panel **Tinh chỉnh** chỉ hỏi ba lựa chọn chính: **Lấy bao nhiêu**, **Ưu tiên tìm
gì** và **Trải đều nhiều cảnh**. Các tham số kỹ thuật như engine, profile, tầng,
`k`, `lambda`, số frame tối đa mỗi cảnh và trọng số nằm trong **Chế độ chuyên
gia**, đóng mặc định. Thanh Công thức chỉ hiển thị trọng số do `params-schema`
trả về; các tooltip và nhãn lấy từ `web/lib/glossary.ts`.

Ở Bước 1, người dùng có thể chọn một file nén lớn hoặc nhiều file part. Web
gọi `GET /api/uploads/limits` để hiển thị trần tổng theo cấu hình máy chủ và
dung lượng trống (nếu máy chủ cung cấp được). Vượt trần tổng bị chặn trước khi
gửi; cảnh báo dung lượng giải nén chỉ là cảnh báo. Việc chia nhỏ thành các
chunk 50 MB vẫn là cơ chế truyền nội bộ để hỗ trợ resume và proxy, không phải
yêu cầu người dùng phải chia file.

Xoá lịch sử v0.6.7: backend chấp nhận cả ID tự sinh và tên job hợp lệ như `night_v24`, `m2_mini`, `full_mini` (1–128 ký tự ASCII chữ/số/`_`/`-`, bắt đầu bằng chữ/số). Bản cũ chỉ chấp nhận hex 12 ký tự khi xoá, nên ba job có tên còn lại sau “Xoá tất cả”. Kiểm đường dẫn được resolve nằm trực tiếp dưới `jobs/`, không nhận symlink/đường dẫn thoát. Job queued/running vẫn được bảo vệ; chỉ xoá thư mục kết quả của job, giữ dataset và trọng số. Sau xoá, frontend refetch danh sách; demo/review cần tạo lại job nếu lịch sử demo đã bị người dùng xoá. Đã kiểm 15 test backend xoá lịch sử và thao tác browser thật: 3 job xoá, 0 còn lại.

```powershell
cd web
node node_modules/next/dist/bin/next dev
# Các lệnh kiểm, chạy ở web/ sau npm ci và dựng media mẫu:
node node_modules/typescript/bin/tsc --noEmit
node node_modules/eslint/bin/eslint.js
node node_modules/vitest/vitest.mjs run
node node_modules/next/dist/bin/next build
```

Test `LiveShowcase.test.ts` kiểm các media **được Git theo dõi** và tồn tại dưới `demo/showcase`, ngăn lỗi chỉ pass trên máy tác giả. Không cần dựng mock-media để chạy test showcase. Không cần worker cho unit test; e2e job thật cần worker và dữ liệu local. Không chạy `demo-flow` A6 trong khi cần giữ worker: phép thử đó chủ động dừng worker 8001.

Build mặc định dùng Turbopack. Không đổi sang `--webpack`: repo chưa có pipeline PostCSS tương đương, build có thể thành công nhưng thiếu utility CSS. Nếu build hiển thị route cũ, kiểm HTML/computed styles; dừng preview của mình, chuyển `.next/cache/turbopack` sang thư mục dự phòng rồi build lại. Không đụng dữ liệu hoặc tiến trình của phiên khác.

Kiểm local 2026-10-14: Vitest **235 pass / 0 fail / 0 skip**; typecheck, lint, build exit 0; `/` và `/vi-sao` tại 1440/390 px có `scrollWidth = clientWidth`. Bằng chứng máy nằm ở hồ sơ quản trị 13 `evidence/P04-refinement/` ngoài repo sản phẩm. Đây là cổng frontend; không thay thế nghiệm thu engine, Colab hoặc demo thực tế.

## Bàn giao agent

Root sản phẩm duy nhất là repo này; không dùng worktree cũ hoặc script đóng gói cũ. Luật/brain/planning nằm ở workspace BuildLab. Khi sửa giao diện, đọc tài liệu này, `web/AGENTS.md` và hướng dẫn Next.js được cài trong `web/node_modules/next/dist/docs/`; kiểm code hiện hành. Không chạy build song song trên cùng thư mục `.next`, không stash chung khi agent khác đang sửa.

Đọc tiếp: [bắt đầu](getting-started.md), [chạy local](run-local.md), [tình trạng dự án](project-status.md).
