# Lưu ý: ảnh/LiDAR khi deploy lên Azure

> **Trạng thái: ĐÃ CHỐT — lưu theo phiên.** Hồ sơ 20 (D11) giữ đủ dữ liệu để Review/viewer/xuất ZIP trong phiên, sau đó xoá khi người dùng kết thúc hoặc TTL 24 giờ.

## Định hướng của người dùng

Trên Azure, ảnh camera và LiDAR sống trong phiên người dùng trên Azure Files Standard; không có dữ liệu nào sống quá TTL cộng một giờ.

## Đã làm theo hướng này

Worker xoá file nén trong `uploads/<id>/` sau khi xét tệp thành công, chỉ giữ `progress.json`; xét lỗi thì giữ để xét lại ([datasets.py](../model/worker/service/datasets.py), hàm `_drop_upload_files`). Trước đây mỗi dataset tốn gấp đôi dung lượng (file nén + bản giải nén).

Bản giải nén trong `datasets/<id>/data` **vẫn còn**, vì các chức năng dưới đây cần nó.

## Vấn đề: các chức năng đang đọc media từ `datasets/`

| Chức năng | Cần gì | Nếu xoá media sau khi phân tích |
|---|---|---|
| Review / Deep Review | Ảnh 6 camera + point cloud của frame | Không xem được frame |
| Viewer 3D | LiDAR + box 3D | Trống point cloud |
| Xuất ZIP lô đã chọn | File gốc của frame được chọn | Không xuất được |
| Chạy lại job (đổi tham số, profile `multisensor`) | Toàn bộ dữ liệu | Phải upload lại |

## Phương án đã chọn

| # | Phương án | Ưu | Nhược |
|---|---|---|---|
| A | Giữ media tạm theo phiên, TTL 24 giờ, rồi xoá tự động | Review vẫn đủ trong phiên làm việc | Cần job dọn định kỳ; tốn Azure Files trong thời hạn |
| B | Sau khi chọn xong chỉ giữ media của lô ~5% được chọn | Giảm ~95% dung lượng, Review/xuất ZIP của lô chọn vẫn chạy | Không xem được frame bị loại; không chạy lại job |
| C | Không lưu media trên cloud; chỉ trả kết quả (danh sách frame, điểm, lý do) | Rẻ và đơn giản nhất | Mất Review/viewer/xuất ZIP trên cloud; người duyệt xem ở local |

Đã chốt: **A với TTL 24 giờ** cho toàn bộ dữ liệu trong lúc job chạy. Azure Files được mount tại `/data/workspace`; worker thread và Container Apps Job cùng quét.

## Việc phải làm khi bắt đầu deploy Azure

- [x] Chốt phương án A, lưu theo phiên và TTL 24 giờ (hồ sơ 20, D11).
- [x] Lập hồ sơ SPEC image, Azure Files, dọn phiên và runbook trong `planning/20_2026-10-15_azure-deploy-lite/`.
- [x] Worker xoá uploads/datasets/jobs theo phiên; job sweep xử lý orphan/TTL.
- [x] Cập nhật bảng hiện trạng trong [README](README.md).
