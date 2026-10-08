# VCuboidFIT Design System

Nguồn thiết kế chủ đạo cho P03b khi Figma MCP hết hạn mức. Antigravity triển khai UI theo file này, `tokens.css`, và 5 mockup HTML trong `web/design/mock/`.

## 1. Nguyên tắc

- Giao diện demo doanh nghiệp: sáng, gọn, đọc nhanh, đủ dữ liệu để pitching nhưng không trang trí dư.
- Một màu nhấn duy nhất: `--vcf-accent #2563EB`. Màu xanh lá và cam chỉ dùng cho trạng thái số liệu.
- Không dùng gradient. Không dùng palette nhiều màu. Frame Viewer dùng nền tối `--vcf-viewer-bg`.
- Font: Inter hoặc system fallback. Mọi số liệu dùng `font-variant-numeric: tabular-nums`.
- Card bo `--vcf-radius-card` 12px, control bo `--vcf-radius-control` 8px, bóng nhẹ `--vcf-shadow-card`.

## 2. Lưới và kích thước

- Mockup chuẩn: `1440x900`, class `.mockup-frame`.
- Màn chọn 5% dùng lưới `8/4`: trái `920px`, phải `448px`, gap `24px`, padding `24px`.
- Deep Review dùng lưới `9/3`: trái `1038px`, phải `330px`, gap `24px`, padding `24px`.
- Header cao `72px`; toolbar Review cao `68px`; toolbar Viewer cao `56px`.
- Nội dung trong card dùng padding `20px`; cụm nhỏ dùng gap `12px` hoặc `16px`.

## 3. Nhóm component

### 3.1 App Header

- Kích thước: cao 72px, full width, nền `--vcf-surface`, border dưới `--vcf-border`.
- Gồm logo chữ VCuboidFIT, dataset hiện tại, chip trạng thái job, hành động phụ.
- Hover: button/chip tăng border sang `--vcf-border-strong`.
- Active: primary action dùng `--vcf-accent`.
- Disabled: opacity 45%.

### 3.2 Button

- Kích thước: cao 40px, padding ngang 14px, radius 8px.
- Variant: `primary`, `secondary` mặc định, `ghost`.
- Hover: primary giữ nền accent, secondary nền `--vcf-surface-muted`.
- Active: dùng border `--vcf-accent`.
- Disabled: opacity 45%, không đổi layout.

### 3.3 Chip và Query Tag

- Kích thước: cao tối thiểu 28px, radius pill, font 12px bold.
- Tone: neutral, accent, good, warn.
- Query tag có thể kèm nút đóng 16px, không làm đổi chiều cao.
- Error: border `--vcf-danger`, nền `--vcf-danger-soft`.

### 3.4 Stat Card lớn/nhỏ

- Lớn: 4 cột ở màn Result, padding 16px, value 32px.
- Nhỏ: panel Review, padding 12px, value 20px.
- Token: nền `--vcf-surface`, border `--vcf-border`, label `--vcf-subtle`.
- Good/warn chỉ tô chip hoặc caption phụ, không đổi toàn card.

### 3.5 Stepper 5 stage

- 5 cột bằng nhau: Index, DINOv2, YOLO, CLIP, Gộp.
- Idle: nền surface, border border.
- Running: nền `--vcf-accent-soft`, border accent.
- Done: nền `--vcf-good-soft`, border xanh lá nhạt.
- Error: nền `--vcf-danger-soft`, border danger, giữ kích thước.

### 3.6 Thumbnail Card

- Tỷ lệ ảnh 16:9, card radius 12px, body 12px.
- Hiển thị rank, reason, tag, số camera.
- Hover: border accent, không phóng to card.
- Active/selected: border accent + nền body `--vcf-accent-soft`.
- Disabled/missing media: visual nền `--vcf-surface-muted`, label "Thiếu camera".

### 3.7 Settings Panel

- Sticky ở cột phải, gồm budget slider, 4 preset, diversity segmented 3 mức, query tags, advanced collapsed.
- Field cao 40px, label 13px bold, gap 8px.
- Slider budget mặc định 5%, range 1-10%.
- Preset: `balanced`, `rare_first`, `hard_for_model`, `safety_scenarios`.
- Error: warning banner vàng ngay dưới field, không toast.

### 3.8 Banner Warning và Notice Data Folder

- Banner warning: nền `--vcf-warn-soft`, border vàng nhạt, text nâu đậm.
- Notice `data/`: nền `--vcf-surface-muted`, border `--vcf-border`, font 13px, line-height 1.55.
- Nội dung notice phải giữ nguyên: file nén có thư mục `data/` ở gốc, hỗ trợ vcf-pack chia 50 MB.

## 4. Quy tắc từng màn

### 4.1 `01-chon-5pct-empty`

- Bước 1 nổi bật: dropzone lớn, notice `data/`, danh sách file mẫu.
- Bước 2 và Bước 3 bị mờ bằng `.muted-card`, chỉ mô tả ngắn để màn không trống.
- Cột phải vẫn hiện option tinh chỉnh nhưng các control disabled.

### 4.2 `02-chon-5pct-result`

- Header báo job hoàn tất.
- Bước 3 gồm 4 stat: `21/404`, Recall `38%`, Uplift `7.6x`, Redundancy `0.12`.
- Có chart 6 method, 12 thumbnail đầu, nút chính Deep Review, nút phụ Xuất CSV.
- Cột phải đang active, có banner cảnh báo vàng nếu đổi ngân sách sẽ chạy select lại.

### 4.3 `03-deep-review`

- Toolbar có back, dataset, chip budget/strategy, search scene, filters, sort, grid/list switch.
- Vùng trái là grid thumbnail 3 cột, đủ thông tin rank/reason/tag.
- Vùng phải là bảng phân tích: 6 stat nhỏ, histogram, recall theo A/B/C, phân bố lý do.
- Selected thumbnail dùng border accent.

### 4.4 `04-frame-viewer-surround`

- Fullscreen nền tối.
- Bố cục 3 camera trước, LiDAR 3D giữa, 3 camera sau.
- Panel phải có rank, scene, frame, timestamp, score bars, reason, tag, điểm camera.
- Phím tắt nằm dưới panel bằng `.kbd`, không che ảnh.

### 4.5 `05-frame-viewer-focus`

- Fullscreen nền tối.
- Một stage lớn chiếm màn hình, source strip 7 nguồn ở dưới.
- Focus có thể là ảnh hoặc LiDAR, vẫn giữ box overlay và gợi ý zoom/pan.
- Panel thông tin có thể thu gọn trong code thật; mockup thể hiện trạng thái mở.

### 4.6 Cảnh LiDAR 3D

- Dùng nền tối, point cloud vertex-color theo độ cao (mặc định) hoặc intensity; hai chế độ chỉ đổi thuộc tính `color`, không dựng lại `BufferGeometry` vị trí. Mặc định theo hướng CVAT: điểm mảnh `1.25px`, opacity `0.72`, giảm sáng `0.82` để tránh ô vuông/nhiễu; thanh trượt chỉ cho `0.5–4px`.
- Camera chính hỗ trợ orbit, pan và zoom; góc nhìn có preset tự do/trên/sau và lệnh đặt lại. Ba viewport top/side/front hiển thị cùng frame, point cloud và cuboid trên một bố cục phụ.
- Lưới mặt đất, trục ego, thân xe và frustum sáu camera định hướng cảnh. Cuboid tô nhẹ, viền và nhãn hover theo lớp; màu cyan cho xe, cam cho xe máy/xe đạp, vàng cho người đi bộ, tím cho vật thể tĩnh.
- Màu lớp là ngoại lệ cục bộ của công cụ 3D; không đổi màu nhấn giao diện chung. Tương quan tham chiếu CVAT và bằng chứng tại `planning/02_2026-10-07_website-figma-ui/evidence/P04c/`.

## 5. Chuyển giao code

- `globals.css` ánh xạ token từ `tokens.css` thành tiện ích Tailwind semantic (`vcf-accent`, `vcf-accent-soft`, `vcf-accent-ink`, `vcf-border`, `vcf-good`, `vcf-warn`, `vcf-danger`). Component dùng các utility này cho trạng thái thiết kế; không tạo màu accent riêng.
- Deep Review dùng lưới `9/3` ở desktop, tương ứng vùng danh sách `1038px`, bảng phân tích `330px` và gap `24px` trong khung chuẩn 1440px. Ở màn nhỏ, hai vùng xếp dọc và dùng toàn chiều rộng.
- AnalysisPanel dùng một accent xanh cho thẻ lọc và chuỗi phân rã điểm; các sắc thái xanh chỉ phân biệt chuỗi trong biểu đồ. Xanh lá/cam dành cho trạng thái kết quả.
- Các trang dùng padding co giãn, không khóa chiều rộng viewport. Frame Viewer xếp điều khiển thành nhiều hàng và đặt panel thông tin dưới vùng xem ở điện thoại.
- Trạng thái tải dùng `role="status"`/`aria-live`; lỗi dùng `role="alert"` và có hành động thử lại khi có thể. Nút chỉ biểu tượng có `aria-label`, trạng thái chọn dùng `aria-pressed`, toàn bộ điều khiển có focus-visible rõ.
- Không đổi tên route đã nêu trong SPEC: `/`, `/review/[jobId]`, overlay viewer bằng query `?frame=<token>`.
- Nếu code thật lệch mockup vì dữ liệu/API, ghi vào `planning/02_2026-10-07_website-figma-ui/evidence/P04a/gaps.txt` thay vì tự đổi thiết kế.
