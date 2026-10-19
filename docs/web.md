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

`/vi-sao#phuong-phap` (0.11.2, hồ sơ 23) trình bày benchmark giám khảo độc lập trên Argoverse 2 VAL theo deck "Benchmark model giám khảo độc lập" bản `_3`: cách đo 4 bước, chia CAL/POOL/EVAL, 6 bước của P_our (`rare_v24 multisensor`), hai giám khảo JA Faster R-CNN v2 / JB RT-DETR và bảng kiểm hợp lệ, 6 cách chọn đối chứng, biểu đồ vật bị bỏ sót dựng bằng HTML, ba câu hỏi – ba câu trả lời và bốn khoá chống tự chấm. Số liệu nằm ở `components/why/copy.ts` khối `methods`, chép đúng slide, giữ nhãn thăm dò và câu "Chưa chứng minh vượt bên thứ 3 ở cỡ mẫu này". Chi tiết: `docs/judge-bench.md`.

Chế độ chuyên gia ở dashboard (0.11.2) chỉ còn cấu hình đầy đủ: Rare v2.4 · LiDAR + camera · PointPillars tự dùng khi Tầng 1 xong; không còn bộ chọn engine/cảm biến/Cơ bản–Nâng cao, và các thanh trượt Rare v2.4 không dùng bị ẩn. State cũ được ép về `rare_v24`/`multisensor`. Job chưa có cache camera (`cache/context_frame.parquet` + crop) thì worker chạy `lidar_only` và ghi mã `CAMERA_CACHE_MISSING` vào `warnings` của API (`service/engines.py::_run_rare_with_fallback`); dashboard không hiện mã này (`visibleWarnings` trong `web/lib/glossary.ts`, chủ sản phẩm chốt 19/10).

`/vi-sao#bang-chung` hiển thị số nguồn và kết luận chính. Kết quả T hiện tại **chưa chứng minh lợi ích hơn baseline**; không suy diễn giá trị vận hành thành thắng benchmark. JSON thiếu/hỏng hiển thị trạng thái rỗng; hình không có thì bỏ hình. Không gõ cứng lại các số T trong component.

Trang chủ dùng `ReviewPerspective` thay khối benchmark. Ba góc nhìn là **tiêu chí đánh giá trải nghiệm**, chưa phải lời chứng thực. Không thêm tên khách hàng, điểm sao hoặc lời khen chưa có nguồn.

## Font và bố cục

PATCH 0.11.1: bỏ thanh “Demo · dữ liệu nuScenes” ở layout và Frame Viewer. Chế độ `?present=1` vẫn phóng chữ và ẩn tham số nâng cao.

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

### Route server gọi worker phải mang theo phiên (bản cloud)

Trên Azure bật `VCF_SESSIONS=1`: mỗi người dùng có cookie `vcf_sid` (32 ký tự hex, do
`web/proxy.ts` cấp) và worker chỉ trả dữ liệu của đúng phiên đó. Vì vậy **mọi route server
của Next gọi worker phải chép `vcf_sid` sang header `x-vcf-session`**. Thiếu header, worker
trả `404 not_found` ("Không tìm thấy tài nguyên") dù tài nguyên có thật. Bản local tắt phiên
nên lỗi chỉ lộ ra trên cloud. Ba route đang gọi worker: `app/api/[...path]` (proxy chung),
`app/api/media/[jobId]/[...path]` (kiểm quyền), `app/api/uploads/[id]/finalize`
(`POST /datasets`). Thêm route mới thì thêm test kiểm header.

Sự cố 17/10/2026: route `finalize` quên header ⇒ mọi lần tải dữ liệu lên Azure dừng ở
"100% đã tải" (log worker `POST /datasets 404`). Sửa ở `f97bcf8`. Cách chẩn đoán và các sự
cố API/GPU khác: [deploy/azure/README.md](../deploy/azure/README.md).

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
