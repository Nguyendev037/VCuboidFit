# Tiến độ VCuboidFIT và bằng chứng

Cập nhật **14/10/2026** · phiên bản cấu hình **0.6.8** (đợt rà tài liệu) · tag gần nhất `v0.6.5`. Nguồn hiện trạng là code trong repo và JSON benchmark được commit; các hồ sơ kế hoạch/evidence quản trị nằm ngoài repo sản phẩm. Không coi việc push code là nghiệm thu toàn bộ nghiên cứu.

## 1. Nội dung dùng để báo cáo tiến độ

**Đã hoàn thành về triển khai:** pipeline LiDAR trên CPU, Tầng 1 PointPillars local, engine `rare_v24` hai profile, backend FastAPI, frontend Next.js, Deep Review/viewer 3D cùng sáu camera, xuất ZIP, trang giải thích phương pháp và số đo. Đợt mới sửa hệ toạ độ box PointPillars, loại ứng viên trên thân xe, lọc score thấp, cải thiện viewer/review/trang chủ và xoá được lịch sử job có tên.

**Đã có thực nghiệm:** benchmark T prereg `pitch-v2` trên Colab A100; kết quả và khoảng tin cậy được công khai. **Chưa chứng minh engine mới vượt baseline.** Thay đổi PointPillars sau benchmark đã chạy local nhưng chưa được xác nhận bằng phép đánh giá hiệu quả mới.

**Việc tiếp theo:** chuẩn bị lại job demo sau khi người dùng xoá lịch sử, tập dượt và đóng băng demo; thẩm định tổng thể hồ sơ UI/engine; lập phép thử mới cho cải thiện bắt ứng viên, bổ sung dữ liệu đêm/mưa và kiểm chứng cầu nối Tầng 1 Colab thật. Không mở lại T cũ hoặc sửa kết luận âm để trình bày tiến độ.

## 2. Sản phẩm và các commit đã đưa lên GitHub

| Thành phần | Hiện trạng | Giới hạn |
|---|---|---|
| `c4_legacy` | Mặc định của service; Tầng 0 hình học CPU, PointPillars tùy chọn | Hiệu quả hybrid phụ thuộc chất lượng seed |
| `rare_v24` | Candidates → track/gate → điểm object/frame → chọn ngân sách/MMR | Không chứng minh hơn M1 trên T hiện có |
| Profile `lidar_only` | Không cần camera cho chấm rare; bộ cụm hình học chạy CPU | Detector PointPillars vẫn cần chuẩn bị tín hiệu GPU khi dùng |
| Profile `multisensor` | OpenCV/OpenCLIP bổ sung chất lượng và bối cảnh ảnh, không VLM | Cần ảnh, cache và trọng số; không tự có sau clone |
| Backend | Jobs/datasets/select/media/export, queue và xoá lịch sử | File-based; dữ liệu chạy local không nằm trong Git |
| Frontend | `/`, `/dashboard`, `/vi-sao`, `/huong-dan`, `/review/**`, viewer 3D | Mock media phải dựng local; Review cần job đã chạy |
| GPU local | PointPillars mini-e80 và OpenCLIP đã chạy trên RTX 4060 8 GB | Kết quả local không thay benchmark T đã freeze |
| Colab | T đã chạy trên A100; notebook Drive và bridge đã có code | Bridge Tầng 1 từ xa và GPU tùy chọn của notebook Drive còn gate môi trường thật |

| Commit | Nội dung |
|---|---|
| `1d2a13a` | PointPillars sensor → ego, loại ứng viên ego, ngưỡng score; cấu hình tách `candidates_v1.yaml` |
| `b8eca3e` | Viewer kiểu CVAT: vùng LiDAR lớn, layer toggle, dải camera thu gọn, hộp ego đúng kích thước |
| `87389ef` | Căn toolbar, lưới và panel Deep Review |
| `519af50` | Trang chủ và `/vi-sao`, typography, giải thích phương pháp, docs/web và hướng dẫn agent |
| `d6639f9` | Sửa xoá named job ID, bảo vệ đường dẫn/active job, cập nhật v0.6.7 |

Trang chủ hiện dùng góc nhìn sử dụng; số T nằm ở `/vi-sao#bang-chung`, phần phương pháp ở `/vi-sao#phuong-phap`. Review là tiêu chí đánh giá trải nghiệm, không phải testimonial có nguồn từ khách hàng.

## 3. Kết quả thực nghiệm

Nguồn công khai: [bench_pitch.json](../web/public/demo/bench_pitch.json). Run `20261013-192329-49de1480`, code thử nghiệm `78ed904` + vá `dd5989d`, prereg `pitch-v2`. T được mở và hoàn tất trong phiên đêm 13–14/10/2026 trên A100; timestamp run không đồng nghĩa ngày hoàn tất theo giờ Việt Nam.

Pool T **1.389 frame / 35 scene**, B = **70**, capture chính **B (`rare_form`)**, **42 instance đích**, bootstrap theo scene 1.000 lần. Random lấy trung bình 100 lần. JSON/report có mã băm để đối chiếu.

| Phương pháp | IY | CI95 | NY | Reach trong 1 m |
|---|---:|---|---:|---|
| M0 Random | 0,073 | [0,020; 0,156] | 0,000 | — |
| M1 Legacy | 0,114 | [0,000; 0,291] | 0,079 | — |
| M2 `lidar_only` | 0,100 | [0,000; 0,257] | 0,052 | 14/42 |
| M3 `multisensor` | 0,057 | [0,000; 0,171] | −0,030 | 14/42 |

Phép so sánh chính **M2 − M1 = −0,014; CI95 [−0,164; 0,084] → `not shown / underpowered`**. Khoảng của chênh lệch chứa 0, chưa xác nhận lợi ích. Không nhầm CI95 của từng phương pháp với CI95 của chênh lệch.

Trần reach 14/42 (33,3%) chỉ ra vấn đề bắt ứng viên của cấu hình thử nghiệm cụm hình học. Đây là chẩn đoán cho lần thử đó, không phải số hiệu quả đã đo của PointPillars mới. Pool T này không có ca đêm/mưa để kết luận về những bối cảnh đó.

Report gốc SHA256: `0df8bd669634704a885324fe0156ab2267a248647933c4a8043540eb0ea52007`. JSON cũng lưu SHA prereg và final config. Ảnh nguồn: [IY theo ngân sách](../web/public/demo/fig_iy_budget.png), [context](../web/public/demo/fig_context.png), [ví dụ](../web/public/demo/fig_examples.png).

Các số bổ sung từ evidence quản trị: M2 ~140 s, M3 ~1.035 s, toàn lượt ~1.236 s trên A100. Camera `night_v24` từng có đêm macro-F1 0,968 / mưa 0,48 trên job minh hoạ và ngưỡng fit V; **không phải kết quả T**, không chứng minh tổng quát mọi thời tiết. Job này đã bị xoá khỏi máy local; số lịch sử không bị thay đổi.

### Số đo legacy/hiệu năng tham khảo

| Đã đo trước đây | Số đo | Phạm vi |
|---|---|---|
| Tầng 0 | ~15 s | nuScenes-mini, máy dev |
| PointPillars train seed | ~350 s / 20 epoch; ~1.340 s / 80 epoch | mini, GPU local |
| Infer Tầng 1 | ~3,5 phút / 404 frame | mini |
| Rare recall legacy | T0 MMR 0,133; hybrid mini-e80 0,067 | V 120 frame, B=7; nhiễu lớn, không dùng khẳng định hơn/kém tổng quát |
| Descriptor/MMR quy mô 28.130 | rarity 11,7 s; MMR 0,6 s | dữ liệu giả lập, không phải trainval thật |

## 4. Kiểm thử và trạng thái chạy

| Phép đo | Kết quả gần nhất có bằng chứng | Ghi chú |
|---|---|---|
| Vitest frontend | 235 pass / 0 fail / 0 skip | 24 file, phiên frontend 14/10; mock media local đã dựng |
| Typecheck/build frontend | Exit 0 | Build mặc định Turbopack |
| ESLint | Exit 0, 0 lỗi / 1 cảnh báo `FrameGrid useVirtualizer` | Cảnh báo React Compiler ở code đã có |
| Test backend xoá lịch sử | 15 pass / 0 fail / 0 skip | Gồm named IDs, active và đường dẫn thoát; 4 regression từng đỏ trước sửa |
| E2E thật | A2/A3/A4/A5/A7: 5 pass | Trước khi xoá job: Dashboard, LiDAR + 6 camera, context, ZIP, present |
| Browser xoá lịch sử | Xoá 3 named job, skipped 0, còn 0 | Sau e2e; dataset/model giữ nguyên |
| Toàn bộ pytest worker ở snapshot lượt 1 | 488 pass / 3 fail / 3 skip | Số lịch sử do điều phối đo; có lỗi nền, không công bố là toàn bộ test xanh |

Ba fail của snapshot cũ: `test_perf` dao động khi máy bận, `test_make_mocks` mismatch 31/15 endpoint và test runner rerun LiDAR; hai lỗi sau được ghi nhận đỏ cả trên code gốc khi môi trường có torch. Không che lỗi bằng đổi test hoặc lấy số của snapshot khác.

Backend local có health HTTP 200, GPU true, profile `local-4060`, seed `mini-e80`; frontend 3000/proxy API đã hoạt động. **Đây là trạng thái máy dev tại lúc kiểm**, không phải thứ đi kèm clone. `night_v24`, `m2_mini`, `full_mini` đã được người dùng xoá; muốn demo Review/e2e dựa vào chúng phải tạo lại.

## 5. Việc còn lại và cổng nghiệm thu

| Việc | Trạng thái / điều kiện |
|---|---|
| Thẩm định tổng thể hồ sơ 13 | Còn gate độc lập; code đã push không tự đóng hồ sơ |
| Chuẩn bị demo 15:00 ngày 15/10/2026 | Tạo lại job demo, kiểm media, tập dượt; freeze dự kiến 13:00 |
| Hồ sơ 11/12 và mốc 0.7.0/0.8.0 | Chưa sign-off toàn bộ; đây là mốc kế hoạch, không mô tả là đã phát hành |
| PointPillars trong rare_v24 | Code/local đã có; cần kế hoạch đánh giá mới trên dữ liệu đủ lớn |
| Bridge Tầng 1 Colab | Cần kiểm end-to-end môi trường thật riêng; T A100 không thay gate bridge |
| Đêm/mưa và tính tổng quát | Cần đủ dữ liệu/ca kiểm; không suy từ T ban ngày hoặc mini |
| Lỗi nền pytest | Xử lý riêng và đo lại trước khi tuyên bố toàn repo xanh |

Không mở lại T cũ, không đổi freeze/prereg để cải thiện số báo cáo. Không tự chạy lại benchmark hoặc tải dataset trong đợt rà docs.

## 6. Cách kiểm lại

Đọc [getting-started](getting-started.md) để cài môi trường, [web](web.md) để dựng mock media. Từ root repo:

```powershell
model\worker\.venv\Scripts\python -m pytest -q model/worker/tests/service/test_jobs_delete.py
model\worker\.venv\Scripts\python -m ruff check model/worker/service/jobs.py model/worker/tests/service/test_jobs_delete.py
cd web
node node_modules/typescript/bin/tsc --noEmit
node node_modules/eslint/bin/eslint.js
node node_modules/vitest/vitest.mjs run
node node_modules/next/dist/bin/next build
```

E2E job thật cần backend và job phù hợp. `demo-flow` A6 chủ động dừng worker; không chạy khi cần giữ dịch vụ. Không dùng test có fixture route để khẳng định GPU/model thật đã đạt hiệu quả.

Đọc tiếp: [README](../README.md), [model-workflow](model-workflow.md), [Colab](colab-dev-setup.md), [GPU thuê](gpu-rental.md).
