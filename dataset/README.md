# dataset/ - bộ zip thử upload

Dữ liệu gốc: **nuScenes-mini** (CC BY-NC-SA 4.0, phi thương mại). Các file `.zip` **không** được commit
(gitignore); chỉ `vcf_manifest.json` và README nằm trong git.

| Thư mục | Nội dung | Dung lượng | Số part |
|---|---|---|---|
| `01_small_3scenes/` | 3 scene (2 ban ngày, 1 đêm), 121 keyframe, ảnh camera keyframe + sweeps LIDAR_TOP | ~912 MiB | 20 |
| `02_full_mini_10scenes/` | nuScenes-mini đủ 10 scene, 404 frame, kèm sweeps | ~5 GiB | 116 |

Mỗi part <= 50 MB, kèm `vcf_manifest.json` (tên part, kích thước, SHA-256), tạo bằng [`tools/vcf-pack`](../tools/vcf-pack/).

## Lấy dữ liệu

* Người trong nhóm: copy từ máy chủ dự án (thư mục `vcf_test_data` có hai bộ trên), hoặc chạy lại script
  đóng gói với `--with-data` (bộ nhỏ) / `--with-data full` (cả hai).
* Người ngoài nhóm: tải nuScenes-mini (v1.0-mini) tại <https://www.nuscenes.org/nuscenes#download>, giải nén
  thành `v1.0-mini/ samples/ sweeps/ maps/` rồi tạo part:
  `python -m vcf_pack <thư-mục-nuscenes> --out dataset/mini --scenes 3` (cài `pip install -e tools/vcf-pack`).

## Upload lên web

Ở **Bước 1 - Nạp dữ liệu**, chọn TẤT CẢ file `vcf_part_*.zip` cùng `vcf_manifest.json` của **một** thư mục
(Ctrl+A trong thư mục). Không trộn file của hai bộ. Server nhận theo chunk, giải nén về
`<WORKSPACE>/datasets/...` rồi kiểm cấu trúc nuScenes. Bộ nhỏ chạy nhanh; bộ 10 scene: `lidar_index` ~36 s,
Tầng 0 vài chục giây.

## Tầng 1 (tuỳ chọn)

Chép `signals.parquet` do Tầng 1 sinh vào `<job>/t1/`. Chỉ hợp lệ với **đúng bộ** đã dùng để chạy Tầng 1
(khớp `sample_token`), không dùng chéo giữa hai bộ.

## Lưu ý

Bộ nhỏ không có ảnh bản đồ `maps/` (không ảnh hưởng luồng LiDAR). Mini quá nhỏ: nhóm C đạt ~100 %
(bão hoà), đừng đọc đó là chất lượng tuyệt đối.
