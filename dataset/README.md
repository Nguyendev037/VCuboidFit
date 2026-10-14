# dataset/ - bộ zip thử upload

Các bảng bên dưới là bộ dữ liệu từng có trên máy tác giả, không phải dữ liệu được clone. Xoá lịch sử job không xoá dataset/weights, nhưng cần chạy job mới để khôi phục Review; ba job demo đã bị người dùng xoá ngày 14/10/2026. Trạng thái/số đo xem [project-status](../docs/project-status.md).

Dữ liệu gốc: **nuScenes-mini** (CC BY-NC-SA 4.0, phi thương mại). Các file `.zip` **không** được commit
(gitignore); chỉ `01_small_3scenes/vcf_manifest.json` và README nằm trong git. **Clone xong thư mục này KHÔNG có zip nào**:
bạn phải tự tạo bộ part theo mục "Lấy dữ liệu" bên dưới. Manifest được commit chỉ mô tả bộ zip gốc của chủ dự án (SHA-256 của
chúng); zip bạn tự đóng gói có SHA-256 khác và đi kèm manifest riêng do `vcf-pack` sinh.

| Bộ (của chủ dự án) | Nội dung | Dung lượng | Số part |
|---|---|---|---|
| `01_small_3scenes/` | 3 scene (2 ban ngày, 1 đêm), 121 keyframe, ảnh camera keyframe + sweeps LIDAR_TOP | ~912 MiB | 20 |
| `02_full_mini_10scenes/` | nuScenes-mini đủ 10 scene, 404 frame, kèm sweeps | ~5 GiB | 116 |

Mỗi part <= 50 MB, kèm `vcf_manifest.json` (tên part, kích thước, SHA-256), tạo bằng [`tools/vcf-pack`](../tools/vcf-pack/).

## Lấy dữ liệu

Cách làm cho mọi người (kể cả người ngoài nhóm), không cần truy cập máy chủ dự án:

1. Tạo tài khoản miễn phí và tải **v1.0-mini** (~4 GB) tại <https://www.nuscenes.org/nuscenes#download>; giải nén
   (Windows 10+ có sẵn `tar`: `tar -xzf v1.0-mini.tgz -C D:\nuscenes`) thành `v1.0-mini/ samples/ sweeps/ maps/`.
2. Cài CLI đóng gói (dùng venv worker đã tạo theo [README gốc](../README.md)) và tạo part vào một thư mục KHÔNG phải
   `dataset/01_small_3scenes/` (để không ghi đè manifest đang được git theo dõi):

```powershell
model\worker\.venv\Scripts\pip install -e tools\vcf-pack
# bộ nhỏ: 3 scene đầu, kèm sweeps LIDAR_TOP
model\worker\.venv\Scripts\python -m vcf_pack D:\nuscenes --out dataset\mini --scenes 3 --include-sweeps
# bộ đủ 10 scene (~5 GiB, ~116 part)
model\worker\.venv\Scripts\python -m vcf_pack D:\nuscenes --out dataset\full --include-sweeps
```

   Cờ của `vcf_pack` (khớp `--help`): `nuscenes_root`, `--out`, `--part-size`, `--version`, `--scenes N`, `--include-sweeps`,
   `--include-maps`. Thiếu `--include-sweeps` thì part chỉ có keyframe (nhỏ hơn bảng trên). Con số 20 part / 121 frame
   của bộ nhỏ là của bộ zip gốc; bộ bạn tự đóng gói nên gần như vậy, dòng tổng kết `vcf_pack` in ra là số thật.
3. Upload thư mục vừa tạo lên web (mục dưới), hoặc dùng thẳng `--data-root D:\nuscenes` cho các lệnh CLI
   (`python -m c4.cli.lidar_index ...`, xem [docs/run-local.md](../docs/run-local.md) mục 4).

## Upload lên web

Ở **Bước 1 - Nạp dữ liệu**, chọn TẤT CẢ file `vcf_part_*.zip` cùng `vcf_manifest.json` của **một** thư mục
(Ctrl+A trong thư mục, ví dụ `dataset/mini/`). Không trộn file của hai bộ. Server nhận theo chunk, giải nén về
`<WORKSPACE>/datasets/...` rồi kiểm cấu trúc nuScenes. Bộ nhỏ chạy nhanh; bộ 10 scene: `lidar_index` ~36 s,
Tầng 0 vài chục giây.

## Tầng 1 (tuỳ chọn)

Chép `signals.parquet` do Tầng 1 sinh vào `<job>/t1/`. Chỉ hợp lệ với **đúng bộ** đã dùng để chạy Tầng 1
(khớp `sample_token`), không dùng chéo giữa hai bộ. Repo không kèm `signals.parquet` hay seed Tầng 1 cục bộ; cách có
Tầng 1: [docs/getting-started.md](../docs/getting-started.md) mục 0 và "Thêm Tầng 1".

## Lưu ý

Bộ nhỏ không có ảnh bản đồ `maps/` (không ảnh hưởng luồng LiDAR). Mini quá nhỏ: nhóm C đạt ~100 %
(bão hoà), đừng đọc đó là chất lượng tuyệt đối.
