# Tình trạng dự án và kế hoạch còn lại

Cập nhật 2026-10-09 · phiên bản hiện hành **v0.6.2** (tag `v0.6.2` = `d0d7eb3`, đã push; trước đó tag `v0.6.1` = `ccf2b84`).
Repo này là **ROOT duy nhất** của sản phẩm (xem [README](../README.md)): code, tài liệu, Docker, notebook đều sửa và push tại đây.

Nguồn các khẳng định: hồ sơ kế hoạch nội bộ 01–05 (ghi dạng "hồ sơ NN, mục X"; thư mục kế hoạch nằm ngoài repo này),
báo cáo R01–R09 của hồ sơ 05, `git log` của repo. Số đo chỉ lấy từ evidence/report đã có, không ước lượng thêm.

## 1. Tổng quan

**Mục tiêu**: từ một bộ nuScenes, chọn **5 % keyframe LiDAR đáng gán nhãn 3D nhất** (cảnh hiếm), chỉ dùng point cloud,
ego pose và timestamp (không camera, không nhãn lúc chọn). Có website Next.js (Chọn 5 %, Deep Review, Frame Viewer)
và engine Python `c4` (Tầng 0 hình học trên CPU, Tầng 1 PointPillars tuỳ chọn trên GPU).

| Thành phần | Trạng thái |
|---|---|
| Tầng 0 (CPU) | Chạy được toàn bộ, ~15 s trên nuScenes-mini; mặc định của sản phẩm |
| Tầng 1 local (Docker GPU) | Chạy thật trên RTX 4060 8 GB với mini (hồ sơ 04, P02) |
| Tầng 1 từ xa qua Colab | Code + test xong, **chưa chạy Colab thật** (G3/G3b, mục 4) |
| Website | Hoàn chỉnh trên mini, có khôi phục run, xoá lịch sử, hướng dẫn trong app |
| Dữ liệu trainval | **Chưa có** trên máy dev ⇒ mọi kết luận về chất lượng chọn chưa chốt |

Tài liệu liên quan: [run-local](run-local.md) · [model-workflow](model-workflow.md) · [glossary](glossary.md) ·
[gpu-rental](gpu-rental.md) · [kaggle-colab](kaggle-colab.md) · [colab-dev-setup](colab-dev-setup.md).

## 2. Đã làm

Trạng thái gate theo môi trường: ✅ đã đạt · ⬜ chưa đạt. "Local" = nuScenes-mini trên máy dev; "thật" = trainval / Colab / GPU thuê.

| Hồ sơ | Phạm vi | Kết quả chính | Mốc | Gate |
|---|---|---|---|---|
| 01 · Stage GPU S0–S4 + job runner | Pipeline camera ban đầu (nhãn media, extract, runner) | Đã hoàn thành về code và được hồ sơ 04 thay bằng engine LiDAR mặc định; camera giữ làm cấu hình phụ. Cột Exit Gates trong hồ sơ vẫn ghi ⬜ vì chưa ai đóng sổ | Plan 2 (nền cho v0.2.0) | local ⬜ (sổ) · thật ⬜ |
| 02 · Website + thiết kế Figma | Khung Next.js, 6 node Figma, UI code | Figma 6 node đã vẽ; PNG xuất bị chặn bởi hạn mức MCP nên thay bằng token + 5 mockup HTML trong `web/design/` | Plan 4 (nền cho v0.3.0) | W1–W4 trong hồ sơ vẫn ⬜ (chưa đóng sổ) |
| 03 · Worker FastAPI | Khung dataset, jobs/select, frames, mock | pytest 293 pass, ruff 0; `openapi.json` 12 endpoint, 765 043 byte, mock hợp lệ 100 % | Plan 3 (nền cho v0.4.0) | G1–G3 ✅ local · G4 thẩm định ⬜ · server ⬜ |
| 04 · Engine LiDAR (pivot theo PDF Final 2026-10-07) | Tầng 0 (descriptor, rarity, MMR + quota, baseline, eval), Tầng 1 PointPillars seed, service + web, gói GPU thuê, khôi phục run | Xem mục 3; thẩm định độc lập 0 P0 / 0 P1; kiểm tra rò rỉ nhãn xanh và từng đỏ khi đột biến | `57e24ac` (push), `27cc26e`, `481a937` | local ✅ (G-T0, G-T1, G-WEB, G-LEAK) · **server ⬜** (G1, G4, V/P, Tầng 1 GPU) |
| 05 · Image PointPillars + cầu nối Colab + UX | Image `vcuboidfit_pointpillars` (GPU) và `vcuboidfit_worker` (CPU, 7-Zip); hàng đợi Tầng 1 từ xa (`/remote/*`, `VCF_REMOTE_TOKEN`); `VCF_PORT` + `model/scripts/check_ports.py`; tham số không cần model; xoá lịch sử; rút gọn upload + ETA; notebook dev | Gate tổng local ✅ (xem mục 3); WP1–WP7 đều ✅ (R01–R07) | `eb4b68b` (v0.6.0), `ccf2b84` (v0.6.1, tag) | G1, G2, G4–G7 ✅ local · **G3, G3b ⬜ Colab thật** |
| 05b · Bản vá v0.6.1 | Thẩm định bảo mật cầu nối (R08), vá giới hạn upload (leaseId, chặn trước khi parse) | 14 probe pass, đột biến "bỏ per-file guard" làm detector đỏ (R08); WP9 phát hành (R09) | `ccf2b84` | local ✅ · máy thật ⬜ |
| v0.6.2 | Thông báo trạng thái tải "Lần chạy gần đây" (`role="status"`); rà a11y 5 điểm khác — đã có sẵn | ✅ tsc/lint/build 0, vitest 183/183, e2e 3/3 | v0.6.2 | `d0d7eb3` |

Các quyết định cần nhớ khi đọc code (hồ sơ 04, mục 6 và nhật ký quyết định):

| Quyết định | Nội dung |
|---|---|
| Đ15 / Q4 | MMR dùng Rar chuẩn hoá min-max (thay hạng phần trăm) vì hạng % nén biên độ, làm frame hiếm cùng kiểu bị coi là trùng. Đã đóng băng; **không đổi sau khi chấm P** |
| Đ16 / Q1 | Nhóm C (visibility "1" hoặc ≤ 5 điểm ở > 40 m) phủ ~100 % frame mini ⇒ định nghĩa theo **số lượng / tỉ lệ box khó**, chốt trên trainval |
| Đ17 / Q2 | τ tạm = 0.02 trên pool 120 frame (cell xuất hiện 1–2 frame là hiếm); chốt thật ở G1 trên trainval |
| Đ18 / Q3 | Seed S nằm **ngoài** ngân sách 5 % |
| Đ19 | Tầng 1 chạy trên GPU thuê/Colab ở bước cuối, sau khi trainval + freeze |
| Bất biến | Chỉ `c4/lidar/gt.py` đọc nhãn; chỉ `eval` đọc `gt_rare_lidar`; mining/extract không đọc `gt/`; một model GPU một process; `select` chạy CPU ≤ 3 s |

## 3. Số đo hiện có

Tất cả đo trên máy dev, nuScenes-mini (404 sample, 120 frame trong pool đánh giá V), trừ khi ghi khác.

### 3.1 Kiểm thử (R09, ngày 2026-10-09, cho v0.6.1)

| Bộ | Lệnh | Exit | Tổng / pass / fail / skip |
|---|---|---|---|
| pytest worker (CPU) | `pytest -q -m "not perf and not gpu" tests` | 0 | 311 / 306 / 0 / 5 (1 deselected) |
| vitest web | `npx vitest run` | 0 | 183 / 183 / 0 / 0 |
| Playwright e2e | `npx playwright test` | 0 | 3 / 3 / 0 / 0 |
| tsc, lint, build web | `npx tsc --noEmit`, `npm run lint`, `npm run build` | 0 cả ba | — |
| ruff | `python -m ruff check c4 service ../scripts/colab_agent.py` | 0 | — |
| Bất biến cổng | `python ../scripts/check_ports.py` | 0 | — |

v0.6.2 chỉ đổi web: đã chạy lại tsc/lint/build (exit 0), vitest 183/183, e2e 3/3; pytest giữ số của v0.6.1.

### 3.2 Hiệu năng

| Phép đo | Giá trị | Nguồn |
|---|---|---|
| Tầng 0 trên mini | ~15 s; descriptor ~20 ms/frame | hồ sơ 04, evidence P01 |
| Tầng 1 train seed, 20 epoch | ~350 s, ~5.4 GB VRAM | hồ sơ 04, P02 |
| Tầng 1 train seed, 80 epoch | ~1340 s | hồ sơ 04, P02 (bản mini-e80) |
| Tầng 1 infer 404 frame | ~3.5 phút | hồ sơ 04, P02 |
| Tầng 0 ở quy mô trainval (N = 28 130, dữ liệu giả lập) | rarity k = 10: 11.7 s · MMR B = 1407: 0.6 s · coreset: 8.5 s · PCA: 12.2 s | `benchmark_trainval_scale`, hồ sơ 04 |
| Bootstrap 200 lần ở trainval | ước lượng ~60–70 phút (chỉ là ước lượng) | cùng nguồn |

### 3.3 Recall hiếm trên mini — **chưa kết luận**

Pool V chỉ 120 frame, ngân sách chọn B = 7, tập hiếm khoảng 15 frame ⇒ mỗi frame trúng/trượt đổi recall ~0.067.
Khác biệt giữa các phương pháp dưới đây **nằm trong nhiễu**, chỉ dùng để kiểm đường ống, không dùng để so sánh phương pháp.

| Phương pháp (split V) | Recall hiếm | Ghi chú |
|---|---|---|
| `coreset_z0` (baseline) | 0.067 | evidence P01 `metrics_mini_V` |
| `t0_rar_topk` | 0.067 | cùng nguồn |
| `t0_rar_mmr` (Tầng 0) | 0.133 | cùng nguồn |
| `t1_rar_mmr` (model seed cold-start 20 epoch) | 0.200 | cùng nguồn; model chưa ra box ≥ 0.1 nên Unc hằng (đã xử bằng hạng 0) |
| `hybrid_mmr` (bản 80 epoch) | 0.067 | thấp hơn `t0_rar_mmr` 0.133; khớp rủi ro PDF "model seed quá yếu"; mAP 0.027 / NDS 0.103 trên T |

Kết luận duy nhất rút ra được: pipeline Tầng 0 + Tầng 1 chạy đầu-cuối và không rò nhãn. Độ hơn kém giữa Tầng 0 và hybrid
phải đo lại trên trainval (mục 4, phase C và D).

## 4. Kế hoạch còn lại theo phase

Cột "ai làm": **Người** = cần tay người (dữ liệu, tài khoản, quyết định); **Agent** = agent làm được khi có điều kiện.

| Phase | Việc | Ai làm | Phụ thuộc | Gate đóng |
|---|---|---|---|---|
| A. Colab thật | Chạy `colab_dev_setup.ipynb` trên Colab: ô 1–4 xanh (`SETUP OK` + pytest xanh) | Người | Tài khoản Colab; [colab-dev-setup](colab-dev-setup.md) | **G3b** hồ sơ 05 |
| A. Colab thật | Một vòng thật: máy không GPU tạo task, Colab chạy mini 20 epoch, web mở khoá Tầng 1; ghi thời gian train/infer thực | Người chạy, Agent ghi evidence | Tunnel tới worker, `VCF_REMOTE_TOKEN`; [run-local](run-local.md) mục 5c | **G3** hồ sơ 05 |
| B. Dữ liệu | Tải nuScenes trainval LiDAR, đóng gói bằng `tools/vcf-pack` rồi nạp qua web | Người | Dung lượng đĩa, giấy phép nuScenes | Điều kiện cho C, D, E |
| C. Đóng băng | Chạy `python -m c4.cli.lidar_g1` trên trainval; chốt τ, cell, định nghĩa nhóm C (Q1/Q2) | Người quyết, Agent chạy | B | **G1** hồ sơ 04 |
| C. Đóng băng | Tune α/β/γ, λ, m trên split val bằng lưới; ghi `configs/final.yaml`; tag `freeze-v1` | Agent chạy, Người duyệt | G1 | **G4** hồ sơ 04 |
| D. Chấm điểm | Chấm split V và P (P chấm **một lần** sau freeze); báo cáo recall, uplift, coverage, redundancy | Agent | G4 | G-T0 mức server |
| E. Tầng 1 GPU thật | Train seed trên trainval bằng GPU thuê/Colab ([gpu-rental](gpu-rental.md), [kaggle-colab](kaggle-colab.md)); infer; hybrid | Người thuê GPU, Agent chạy | B, G4 | G-T1 mức server |
| E. Tầng 1 GPU thật | Downstream PointPillars: S∪A so với S∪A_rand (script đã có, mini chỉ kiểm script với |A| = 7) | Agent | E trước | PDF §5.4 (stretch) |
| F. So sánh | Đo hybrid so với Tầng 0 thuần trên trainval, có khoảng tin cậy (bootstrap) | Agent | D, E | Kết luận chất lượng; mở khoá v0.5.0 của hồ sơ 04 |
| G. Đóng hồ sơ | Ký "✅ ĐÃ HOÀN THÀNH" kèm thời gian cho hồ sơ 04 và 05; đồng bộ não, changelog, roadmap | Agent | C–F và A | Đóng hồ sơ |
| H. Deploy | Hồ sơ 04 SPEC-P04 mới có **gói** GPU thuê (compose, bootstrap, pack); chưa có hồ sơ deploy production/hosting cho website | Người quyết | Chưa lập kế hoạch | Chưa có gate; cần hồ sơ mới nếu làm |

Ghi chú về phiên bản: hồ sơ 04 đóng ở v0.5.0 và hồ sơ 05 ở v0.6.0 theo kế hoạch ban đầu; thực tế mã đã vượt (v0.6.2)
vì hồ sơ 05 phát hành trước khi hồ sơ 04 đóng. Khi đóng cần thống nhất tên mốc trong changelog, không đánh số lùi.

### Idea Vault đáng làm (chưa lên lịch)

| Ý tưởng | Giá trị | Ghi chú |
|---|---|---|
| Xử lý `npm audit` cho phụ thuộc | Giảm rủi ro bản phát hành | Hồ sơ 04 ghi `npm audit --omit=dev` = 0 lỗ hổng sau khi chuyển shadcn sang devDependencies; trước đó 9 mức high, cần kiểm lại. Không dùng `audit fix --force` |
| Dùng [z0, z1] cho đa dạng MMR khi có Tầng 1 | Có thể tăng chất lượng hybrid | Hiện chỉ z0 (Đ6 hồ sơ 04); đo ở phase F, không đổi sau freeze |
| Overlay box dự đoán seed trên BEV | Dễ giải thích kết quả khi demo | Ảnh BEV đã có ở `media/bev/` |
| Kiểm tra chéo trên Waymo | Chứng minh tổng quát | Ngoài phạm vi hiện tại |
| Sinh ảnh mưa/đêm | — | **Đã loại** khỏi phạm vi (yêu cầu gốc: không quan tâm phần sinh ảnh) |

## 5. Rủi ro và việc bỏ ngỏ

| # | Rủi ro / việc bỏ ngỏ | Mức | Hành vi hiện tại | Việc nên làm |
|---|---|---|---|---|
| 1 | Cầu nối Colab chưa được thử với Colab thật | Cao | Chỉ có dry-run e2e và test; R08 thẩm định bằng probe cục bộ | Phase A trước khi quảng bá tính năng |
| 2 | Lease hết hạn: theo SPEC-P02 mục 3 hồ sơ 05, `leased → queued` khi hết lease; nhánh này không thấy trần số lần ở mô tả máy trạng thái (trần `attempts ≥ 3` ghi cho nhánh `fail`) ⇒ một task có thể quay vòng không giới hạn nếu agent chết | Trung bình | Chấp nhận theo SPEC, chưa có cảnh báo | Người xác nhận; nếu muốn chặn, cần sửa SPEC trước rồi mới sửa code (không "sửa cho tốt hơn" ngoài SPEC) |
| 3 | 5 test CPU bị skip (cần torch/GPU, môi trường test không cài) | Thấp | Giữ nguyên skip, không sửa test để né | Chạy bộ này trên máy có torch trước khi phát hành lớn. Hồ sơ 04 ghi một mốc "1 skip" cũ; số hiện hành là 5 (R09) |
| 4 | Model seed mini quá yếu (mAP 0.027, cold-start 0 box ở 20 epoch) | Trung bình | Unc hằng được xử bằng hạng 0, chỉ có nghĩa trên trainval | Đánh giá lại ở phase E; PDF đã nêu đây là rủi ro |
| 5 | Nhóm C phủ ~100 % frame mini | Trung bình | Định nghĩa còn thô | Phase C (Q1) |
| 6 | Chọn hiếm đổi contract chấm điểm sau khi chấm P | Cao nếu xảy ra | Cấm theo hồ sơ 04 (Đ15, freeze) | Giữ nguyên `freeze-v1` |
| 7 | Hạn mức Figma MCP làm thiếu PNG thiết kế | Thấp | Đã thay bằng mockup HTML trong `web/design/` | Không cần |
| 8 | Luồng worktree cũ (`plan2-gpu-stages`, `web-ui`, `web-ux-lidar`) và script đóng gói cũ đã **ngừng dùng** | Trung bình | Chỉ làm việc tại repo này | Không chạy lại script cũ: có thể ghi đè bản mới bằng bản cũ |
| 9 | Hồ sơ 01–03 còn Exit Gates ⬜ dù code đã chạy | Thấp | Chưa ai đóng sổ | Gộp việc đóng sổ vào phase G |
| 10 | Dataset zip không commit (giấy phép CC BY-NC-SA) | Thấp | `dataset/**/*.zip` nằm trong `.gitignore` | Người dùng tự tạo bằng [vcf-pack](../tools/vcf-pack/) |

## 6. Cách kiểm lại nhanh

```powershell
cd model\worker
.venv\Scripts\python -m pytest -q -m "not perf and not gpu" tests     # kỳ vọng: 0 fail
.venv\Scripts\python -m ruff check c4 service
cd ..\..\web ; npx tsc --noEmit ; npx vitest run
cd .. ; python model\scripts\check_ports.py                          # exit 0
```

Đọc tiếp: [README](../README.md) · [run-local](run-local.md) · [model-workflow](model-workflow.md).
