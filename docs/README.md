# Hướng dẫn đọc tài liệu

Bộ tài liệu trong thư mục này là tài liệu vận hành và as-built của VCuboidFIT.
Đường dẫn trong bảng là tương đối từ thư mục `docs/guide/`.

## Thứ tự đọc gợi ý

1. [FAQ và xử lý sự cố](faq-troubleshooting.md) — nắm cách cài, chạy và xử lý lỗi thường gặp.
2. [Engine Tầng 0](engine-tier0.md) — hiểu pipeline LiDAR CPU và nguyên tắc không rò nhãn.
3. [Tầng 1 PointPillars](tier1-pointpillars.md) — đọc khi cần GPU, Docker hoặc model seed.
4. [API reference](api-reference.md) — tra contract endpoint, proxy, upload và media.
5. [UI components](ui-components.md) — tra component, màn hình và tương tác web.
6. [Glossary](glossary.md) — tra tên hiển thị và ý nghĩa chỉ số khi đọc các tài liệu khác.

## Mục lục

| Tài liệu | Mô tả một dòng | Đối tượng đọc |
|---|---|---|
| [glossary.md](glossary.md) | Tên hiển thị, tooltip và cách hiểu “Độ hiếm (ước lượng)”, “Hiếm thật (theo nhãn)” cùng các metrics. | Người dùng · Lập trình viên |
| [faq-troubleshooting.md](faq-troubleshooting.md) | Cài đặt, chạy dữ liệu `H:/vcf_test_data`, Docker, GPU/RAM, mã hóa, Recall và xử lý sự cố. | Người dùng · Vận hành |
| [engine-tier0.md](engine-tier0.md) | Luồng Tầng 0, descriptor, score, file đầu ra, tham số cố định/tune và chống rò nhãn. | Lập trình viên · Vận hành |
| [tier1-pointpillars.md](tier1-pointpillars.md) | PointPillars seed, GPU/VRAM, Docker, `--no-docker`, artifact `t1/` và lỗi đã gặp. | Vận hành · Lập trình viên |
| [api-reference.md](api-reference.md) | Endpoint worker, request/response/lỗi, proxy Next.js, upload chunk và media `.f16`. | Lập trình viên · Vận hành |
| [ui-components.md](ui-components.md) | Component UI/UX, màn hình Home/Review/Viewer, trạng thái, accessibility, phím tắt và test. | Lập trình viên · Người dùng |

## Chọn tài liệu theo câu hỏi

| Câu hỏi | Đọc trước |
|---|---|
| Tôi cài và chạy bộ dữ liệu nào? | [FAQ và xử lý sự cố](faq-troubleshooting.md) |
| Tầng 0 chọn frame bằng tín hiệu nào? | [Engine Tầng 0](engine-tier0.md) và [Glossary](glossary.md) |
| Vì sao Tầng 1 bị khóa hoặc CUDA OOM? | [Tầng 1 PointPillars](tier1-pointpillars.md) |
| Gọi endpoint nào để tạo job/chọn frame? | [API reference](api-reference.md) |
| Component nào hiển thị frame và phím tắt ra sao? | [UI components](ui-components.md) |
