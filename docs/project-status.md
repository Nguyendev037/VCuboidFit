# Tình trạng dự án và kế hoạch còn lại

PATCH v0.6.7 (2026-10-14): sửa xoá lịch sử với job có tên (trước đó “Xoá tất cả” bỏ qua `night_v24`, `m2_mini`, `full_mini`). Cổng kiểm: 15 test xoá pass; thao tác trên browser xoá đủ 3 job, API/list UI còn 0. Dataset/trọng số được giữ, backend vẫn chạy; job demo đã xoá cần tạo lại khi dùng Review hoặc e2e dựa vào job đó. Chi tiết [web.md](web.md).

Frontend v0.6.6 (2026-10-14): trang chủ thay khối benchmark bằng góc nhìn người sử dụng, ghi rõ là tiêu chí đánh giá, chưa phải lời chứng thực. Số benchmark T giữ ở `/vi-sao#bang-chung`; phần `/vi-sao#phuong-phap` giải thích M0–M3, IY capture B, cùng ngân sách và bootstrap CI95. Nhấn mạnh giá trị vận hành của VCuboidFIT, không kết luận hơn baseline. Tiêu đề mục dùng Newsreader 30–48 px, nội dung thẻ 16–18 px. Chi tiết chạy, media và bàn giao ở [web.md](web.md). Hồ sơ 13 vẫn chờ nghiệm thu tổng thể; chưa tạo tag phát hành.

Cập nhật 2026-10-14 · cấu hình hiện hành **v0.6.7**, tag gần nhất `v0.6.5` = `8bcc9c0`. Lượt engine/viewer/Deep Review tới `87389ef`; frontend/docs tới `519af50`, sau đó hotfix xoá lịch sử trên `main`. Hồ sơ 11/12 còn mốc 0.7.0/0.8.0 và nghiệm thu demo 15/10.
**v0.6.3–v0.6.5**: notebook Colab chạy Tầng 1, cầu nối Colab ổn định, tái dùng trọng số seed pretrained. Từ đó đã mở rộng thêm: hồ sơ 10 (chuẩn hoá định nghĩa "hiếm" RHCIO v2.4 theo instance), hồ sơ 11 (engine mới `rare_v24`, tầng bối cảnh OpenCLIP không VLM, benchmark prereg `pitch-v2` chạy tập T trên Colab A100), hồ sơ 12 (UI demo ngày 15/10/2026 15:00, số T lên trang chủ, trang `/vi-sao`, xuất ảnh hiếm ZIP).

Repo này là **ROOT duy nhất** của sản phẩm (xem [README](../README.md)): code, tài liệu, Docker, notebook đều sửa và push tại đây.

Nguồn các khẳng định: hồ sơ kế hoạch nội bộ 01–05, 10–12 (ghi dạng "hồ sơ NN, mục X"; thư mục kế hoạch nằm ngoài repo này),
báo cáo và evidence của các hồ sơ (R01–R09 hồ sơ 05, R01–R26 hồ sơ 11, R01–R12 hồ sơ 12), `git log` của repo. Số đo chỉ lấy từ evidence/report đã có, không ước lượng thêm.

## 1. Tổng quan

**Mục tiêu**: từ một bộ nuScenes, chọn **5 % keyframe LiDAR đáng gán nhãn 3D nhất** (cảnh hiếm), chỉ dùng point cloud,
ego pose và timestamp (không camera, không nhãn lúc chọn). Có website Next.js (Chọn 5 %, Deep Review, Frame Viewer,
trang Vì sao, xuất ảnh hiếm) và engine Python `c4` (gồm `c4_legacy` Tầng 0 CPU/Tầng 1 PointPillars và engine mới `rare_v24` theo chuẩn RHCIO).

| Thành phần | Trạng thái |
|---|---|
| Tầng 0 (CPU) | Chạy được toàn bộ, ~15 s trên nuScenes-mini; mặc định của `c4_legacy` |
| Tầng 1 local (Docker GPU) | Chạy thật trên RTX 4060 8 GB với mini (hồ sơ 04, P02) |
| Tầng 1 từ xa qua Colab | Code + test xong (hồ sơ 05/05b); Colab A100 đã dùng thật cho benchmark T (hồ sơ 11), còn cầu nối Tầng 1 từ xa **chưa đo trên Colab thật** (G3/G3b hồ sơ 05) |
| Engine `rare_v24` | Đã dựng xong (hồ sơ 11); pipeline gồm ứng viên cụm ego-frame, tracker, gate, điểm vật/frame, ngân sách MMR; 2 profile `lidar_only` và `multisensor` (crop OpenCLIP) |
| Bối cảnh camera | Tầng bối cảnh OpenCV + OpenCLIP (không VLM) phân tích 4 trục (chiếu sáng, chói, che khuất/ống kính, thời tiết), sinh cờ chất lượng và hàng đợi người duyệt |
| Benchmark T | Đã chạy prereg `pitch-v2` trên Colab A100 (tập T 1 389 frame / 35 scene, B = 70, 42 instance đích); kết quả M2/M3 chưa chứng minh khác biệt so với baseline M1 (xem mục 3.4) |
| Website | Đầy đủ giao diện v2: tokens, trang chủ nạp số T thật, dashboard tách module, viewer chú giải + phím tắt, trang `/vi-sao`, xuất ZIP ảnh hiếm 6 camera + BEV |
| Dữ liệu trainval | Pool 170 scene (6 753 keyframe) đã có trên máy dev và Drive; benchmark T chạy trên Colab |

Tài liệu liên quan: [run-local](run-local.md) · [model-workflow](model-workflow.md) · [glossary](glossary.md) ·
[gpu-rental](gpu-rental.md) · [colab-dev-setup](colab-dev-setup.md).

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
| 10 · Định nghĩa "hiếm" v2.4 + Taxonomy RHCIO | Chuẩn hoá định nghĩa "hiếm" RHCIO theo instance (surprisal Q90 trên V, primary R2 rare_combo), metric IY/NY/Oracle, bộ SPEC 8 file; chuyển phần thi công sang hồ sơ 11 (bỏ VLM) | Bộ SPEC hoàn chỉnh (00, 01, P01–P04, OPERATIONS, TESTING); thẩm định độc lập R01 (Codex astra) thống nhất primary R2, cấm OR nhãn R; đo base rate mini (404 frame) instance-level | `5e2d671` (nền cho 0.7.0) | local ✅ (SPEC, base rate R01) · server ⬜ (thi công ở hồ sơ 11) |
| 11 · Dựng lại engine `rare_v24` không VLM + bối cảnh OpenCLIP + benchmark Colab A100 | Engine `rare_v24` (`c4/rare/`: GT RHCIO, ứng viên cụm ego-frame, tracker, gate, điểm vật/frame, MMR budget, eval IY/NY/oracle), tầng bối cảnh (`c4/context/`: sun, quality_cv, clip_axes, thresholds, fuse), API EngineRouter, CLI bench_pitch, notebook Colab A100 | pytest 378 pass / 5 skip; benchmark T (1 389 frame, 35 scene, B=70, 42 instance đích) chạy trên Colab A100; đo reachability 14/42 (33 %); bối cảnh camera review 1,7 %; xuất gói kết quả `T_demo_bundle.zip` | `f4d91e4`, `c4e41b9`, `010611f`, `c409106`, `fa32836`, `dd5989d` (0.7.0) | local ✅ (C0–C3, M1–M3, M5, M6, M8a) · **Colab thật ✅** (chạy thành công T trên A100; gate chất lượng `not shown / underpowered`) |
| 12 · Demo toàn hệ thống + nâng cấp UI/UX | Web Next.js (design tokens, trang chủ số thật từ T, tách dashboard, trạng thái rỗng/lỗi, viewer chú giải + phím tắt, trang `/vi-sao`, xuất ảnh hiếm ZIP), job demo local (`m2_mini`, `night_v24`) | vitest 221 pass (23 file), Playwright e2e 9/9 pass (luồng demo hoàn chỉnh), tsc/eslint 0 lỗi; nạp số đo T vào demo web tĩnh qua `bench_pitch.json` | `f88fd87`, `690f3a6`, `203636d`, `7eaa221`, `59d62b9`, `922cd86` (0.8.0) | local ✅ (G1, G2, G3: test, build, e2e) · demo thật ⬜ (chờ 15:00 thứ Năm 15/10) |

Các quyết định cần nhớ khi đọc code (hồ sơ 04, mục 6 và nhật ký quyết định):

| Quyết định | Nội dung |
|---|---|
| Đ15 / Q4 | MMR dùng Rar chuẩn hoá min-max (thay hạng phần trăm) vì hạng % nén biên độ, làm frame hiếm cùng kiểu bị coi là trùng. Đã đóng băng; **không đổi sau khi chấm P** |
| Đ16 / Q1 | Nhóm C (visibility "1" hoặc ≤ 5 điểm ở > 40 m) phủ ~100 % frame mini ⇒ định nghĩa theo **số lượng / tỉ lệ box khó**, chốt trên trainval |
| Đ17 / Q2 | τ tạm = 0.02 trên pool 120 frame (cell xuất hiện 1–2 frame là hiếm); chốt thật ở G1 trên trainval |
| Đ18 / Q3 | Seed S nằm **ngoài** ngân sách 5 % |
| Đ19 | Tầng 1 chạy trên GPU thuê/Colab ở bước cuối, sau khi trainval + freeze |
| Bất biến | Chỉ `c4/lidar/gt.py` đọc nhãn; chỉ `eval` đọc `gt_rare_lidar`; mining/extract không đọc `gt/`; một model GPU một process; `select` chạy CPU ≤ 3 s |
| Đ1 (hồ sơ 11) | Bỏ hoàn toàn VLM ở mọi khâu (chọn, giải thích, chấm); dùng OpenCLIP pretrained + OpenCV cho bối cảnh camera và multisensor |
| Đ9 (hồ sơ 10) | Định nghĩa "hiếm" RHCIO đếm theo instance: surprisal Q90 trên V, primary R2 rare_combo; cấm OR nhãn R |
| Đ28 (hồ sơ 11) | Capture B là luật chính (instance chỉ tính thu được khi lô chọn có frame nó ở đúng dạng hiếm), capture A (bất kỳ frame nào có điểm LiDAR) báo cáo phụ |
| Đ44 (hồ sơ 11) | Box cụm chuyển từ hệ cảm biến LIDAR_TOP sang ego frame trước khi chiếu sang 6 camera và tính điểm |
| Đ46 (hồ sơ 11) | Mở tập T một lần với prereg `pitch-v2`, báo cáo trung thực nếu CI95 chứa 0; bước tiếp theo chuyển sang Tầng 1 PointPillars |

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
Đến hồ sơ 12 (ngày 2026-10-14): pytest worker 382 pass / 0 fail / 5 skip (gate G1); vitest web 221 / 221 pass (23 file), Playwright e2e 9 / 9 pass với worker thật, tsc và eslint exit 0 (gate G3b, sau khi thêm trang `/vi-sao`).

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

### 3.4 Kết quả benchmark T (2026-10-14)

Chạy trên Colab A100 theo kế hoạch preregistered `pitch-v2` (hồ sơ 11, commit `dd5989d`, seed 20261013, 1000 bootstrap). Tập pool T gồm 1 389 frame (35 scene), ngân sách B = 70 (5 %), 42 instance đích (theo quy tắc capture B: `rare_form`). Lần chạy retry-1 hoàn tất sau 1 236 s (lần 1 exit 2 sau 3,6 s do đường dẫn data-root, xảy ra trước khi đọc bất kỳ nhãn nào, Đ54 hồ sơ 11).

Nguồn: `report_pitch.json` (sha256 `0df8bd669634704a885324fe0156ab2267a248647933c4a8043540eb0ea52007`), gói `T_demo_bundle.zip` (sha256 `0ca79700a131d8410ce08e652fc8de3b61e37a40515d3e8fb800542072ddd457`), trích tại `evidence/K2/T_result.md` (hồ sơ 11).

| Phương pháp | IY | CI95 | instance | NY | reach (r=1 m) | IY capture A |
|---|---|---|---|---|---|---|
| M0 Random (TB 100) | 0,073 | [0,020; 0,156] | 5,09 | 0 | — | 0,262 |
| M1 Legacy Tầng 0 | 0,114 | [0; 0,291] | 8 | 0,079 | — | 0,257 |
| M2 rare_v24 lidar_only | 0,100 | [0; 0,257] | 7 | 0,052 | 14/42 = 0,333 | 0,343 |
| M3 rare_v24 multisensor | 0,057 | [0; 0,171] | 4 | −0,030 | 14/42 = 0,333 | 0,286 |
| Oracle (tham chiếu NY) | 0,600 | — | 42 | — | — | — |

- **Kết luận chính (prereg):** M2 − M1 Δ = −0,014, CI95 [−0,164; 0,084] ⇒ **`not shown / underpowered`** (nguyên văn report).
- **So sánh phụ (Holm):** M2 − M0 +0,027 [−0,033; 0,107] p_holm 0,49 · M3 − M2 −0,043 [−0,086; 0] p_holm 0,18 — khác biệt không có ý nghĩa thống kê.
- **Reach:** 14/42 (33,3 %) instance đích có ứng viên cụm trong bán kính 1 m.
- **Bối cảnh:** `glare_sun` cov 0 ở mọi phương pháp (pool T ban ngày, không frame nào gắn chói nắng). Đêm/mưa: 0 (pool không có).
- **Thời gian:** M2 140 s · M3 1 035 s (crop OpenCLIP) · tổng bench 1 236 s.

**Diễn giải trung thực:**
Engine `rare_v24` chưa chứng minh khác biệt so với baseline trên T: mọi CI chứa 0; capture B nhỏ (42 instance) ⇒ underpowered. Trần reachability 33 % (14/42 instance đích có ứng viên cụm trong 1 m) cho thấy nút thắt là bắt ứng viên (cụm DBSCAN bỏ lỡ VRU < 8 điểm — chẩn đoán V R14 hồ sơ 11), không phải xếp hạng. Capture A (frame có VRU bất kỳ): M2 0,343 so với M0 0,262.

**Bước tiếp theo Tầng 1:**
Chuyển sang Tầng 1 PointPillars (hồ sơ 11 Đ46 c) nhằm dùng mạng nơ-ron phát hiện 3D học từ điểm thưa để thay thế cho bộ gom cụm DBSCAN hình học thô, giải quyết trần reachability trước khi đánh giá lại.

## 4. Kế hoạch còn lại theo phase

Cột "ai làm": **Người** = cần tay người (dữ liệu, tài khoản, quyết định); **Agent** = agent làm được khi có điều kiện.

| Phase | Việc | Ai làm | Phụ thuộc | Gate đóng |
|---|---|---|---|---|
| UI Demo (hồ sơ 12) | Nâng cấp toàn diện UI/UX: tokens, nạp số T thật lên trang chủ, tách dashboard, trạng thái rỗng/lỗi, viewer chú giải + phím tắt, trang `/vi-sao`, xuất ZIP ảnh hiếm | Agent | G0 số T, hồ sơ 11 | G1–G3 ✅ local |
| FREEZE code demo | Đóng băng mã nguồn lúc 13:00 ngày 2026-10-15; không thêm tính năng mới trước demo | Người + Agent | G3b gate xanh | FREEZE 13:00 15/10 |
| Demo sản phẩm | Tập dượt và trình diễn trực tiếp hệ thống vào 15:00 thứ Năm 2026-10-15 theo kịch bản (SPEC-P03 hồ sơ 12) | Người dẫn, Agent hỗ trợ | FREEZE 13:00 | Demo 15:00 15/10 |
| Đóng hồ sơ 11 & 12 | Sau demo: ký nghiệm thu, đồng bộ não bộ 6 điểm, phát hành phiên bản 0.7.0 (hồ sơ 11) và 0.8.0 (hồ sơ 12) | Agent chạy, Người duyệt | Demo hoàn tất | Sign-off 0.7.0 / 0.8.0 |
| Tầng 1 PointPillars | Tích hợp detector 3D PointPillars trên GPU để bắt ứng viên thưa điểm (< 8 điểm), nâng trần reachability vượt mốc 33 % của DBSCAN | Agent nghiên cứu/thi công | Sau demo 15/10 | Kế hoạch kế tiếp |
| Bổ sung dữ liệu đêm/mưa | Tải thêm blob trainval chứa scene đêm/mưa (blob 10, 06, 09) để đánh giá đầy đủ 4 trục bối cảnh camera trên dữ liệu thật | Người tải, Agent chạy | Dung lượng ổ đĩa | Mở rộng sau demo |

Ghi chú về phiên bản: Hồ sơ 11 (engine `rare_v24` và tầng bối cảnh) sẽ đóng ở mốc **v0.7.0**. Hồ sơ 12 (toàn bộ UI demo và trang `/vi-sao`) sẽ đóng ở mốc **v0.8.0** ngay sau buổi demo ngày 15/10/2026. Lịch sử thay đổi và tài liệu não bộ sẽ được đồng bộ theo đúng Ma Trận 6 Điểm.

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
