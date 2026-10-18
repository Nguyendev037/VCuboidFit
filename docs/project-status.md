# Tiến độ VCuboidFIT và bằng chứng

Cập nhật **18/10/2026**. Phiên bản đã push **0.11.0** (`web/package.json`, `model/worker/pyproject.toml`); bản local **0.11.1** (gỡ banner trình chiếu) chưa commit. Tag gần nhất `v0.6.5`. Nguồn hiện trạng là code trong repo và JSON/report được commit; SPEC, evidence máy và nhật ký quyết định nằm ở hồ sơ quản trị BuildLab `planning/`. Push code không đồng nghĩa nghiệm thu nghiên cứu.

## 1. Tóm tắt một trang

**VCuboidFIT** chọn ra khoảng 5 % keyframe đáng gán nhãn nhất cho hệ phanh khẩn cấp AEB (Autonomous Emergency Braking), ưu tiên người đi bộ, xe đạp, xe máy (VRU). Người duyệt xem LiDAR, hộp 3D, sáu camera và lý do chọn trên web rồi xuất danh sách/ZIP.

| Mảng | Hiện trạng 18/10 |
|---|---|
| Engine | `c4_legacy` (mặc định, Tầng 0 CPU + PointPillars tuỳ chọn); `rare_v24` hai profile `lidar_only` và `multisensor` (OpenCV 13 đặc trưng + OpenCLIP), không VLM |
| Tầng 1 PointPillars | Train từ đầu trên nuScenes trainval (A100), bản dùng **e12/20: mAP 0,220 · NDS 0,343** trên 602 frame VAL; e6 lưu Git LFS `model/weights/pointpillars-trainval-e6/` |
| Web | Next.js 16: trang chủ, `/dashboard` (panel 3 câu + Chế độ chuyên gia), `/review/**` viewer 3D kiểu CVAT + 6 camera, `/vi-sao`, `/huong-dan` |
| Triển khai | Azure Container Apps public (không mật khẩu demo, phiên `vcf_sid`); GPU thuê Vast có warm-up, tự tắt máy rảnh, chủ dự án phải đồng ý trước khi thuê máy mới |
| Bằng chứng | (1) benchmark T nuScenes `pitch-v2`: **chưa chứng minh** M2 hơn M1; (2) benchmark giám khảo độc lập Argoverse 2: lô OURS **đứng đầu nhưng chưa vượt chắc** bên thứ 3, nhãn **thăm dò** |

## 2. Thành phần sản phẩm

| Thành phần | Hiện trạng | Giới hạn |
|---|---|---|
| `c4_legacy` | Mặc định của service; Tầng 0 hình học CPU, PointPillars tuỳ chọn | Hiệu quả hybrid phụ thuộc chất lượng seed |
| `rare_v24` | Ứng viên → track/gate → điểm vật/khung (0,70 vật · 0,15 VRU · 0,15 bối cảnh) → chọn ngân sách/MMR | Chưa chứng minh hơn M1 trên T; trên AV2 chưa vượt chắc bên thứ 3 |
| Profile `multisensor` | OpenCV đo 13 đặc trưng chất lượng ảnh → 4 cờ (đêm, chói, mờ, màn mờ); OpenCLIP 4 trục bối cảnh + độ lạ crop vật | Cần ảnh, cache và trọng số; web chưa tự sinh cache bối cảnh |
| Backend FastAPI | Jobs/datasets/select/media/export, queue, xoá lịch sử, `/api/uploads/limits` | File-based (Parquet/JSON/CSV/NPY), không DB |
| Frontend | Panel Tinh chỉnh 3 câu, tooltip `web/lib/glossary.ts`, viewer 3D, chế độ trình chiếu `?present=1` (lưu `sessionStorage`) | Review cần job đã chạy |
| GPU | Local RTX 4060 8 GB; Colab A100 cho train/benchmark; Vast cho bản online | Bridge Tầng 1 Colab còn gate môi trường thật |

Chi tiết tầng camera và điểm S: [camera-layer](camera-layer/README.md). Kỹ thuật toàn hệ: [system-reference](system-reference.md) (local, chưa commit).

## 3. Kết quả thực nghiệm

### 3.1. Benchmark T nuScenes (`pitch-v2`, 13–14/10, A100)
Nguồn công khai: [bench_pitch.json](../web/public/demo/bench_pitch.json). Pool T **1 389 frame / 35 scene**, B = **70**, **42 instance đích**, bootstrap theo scene 1 000 lần, random TB 100 lần.

| Phương pháp | IY | CI95 | Reach trong 1 m |
|---|---:|---|---|
| M0 Random | 0,073 | [0,020; 0,156] | — |
| M1 Legacy | 0,114 | [0,000; 0,291] | — |
| M2 `lidar_only` | 0,100 | [0,000; 0,257] | 14/42 |
| M3 `multisensor` | 0,057 | [0,000; 0,171] | 14/42 |

**M2 − M1 = −0,014; CI95 [−0,164; 0,084] → chưa chứng minh.** Trần reach 14/42 cho thấy khó khăn chính là bắt ứng viên. T không mở lại. Report SHA256 `0df8bd66…`.

### 3.2. Benchmark giám khảo độc lập Argoverse 2 (hồ sơ 21, 18/10, A100)
Chấm trên **Argoverse 2 Sensor VAL** (xe, cảm biến, thành phố khác nuScenes; engine giữ nguyên config nuScenes). 150 log · 4 806 khung · 345 259 hộp 3D; chia CAL 960 / POOL 2 630 / EVAL 1 216 khung; B = 132. Hai giám khảo công khai JA Faster R-CNN v2 và JB RT-DETR đếm vật thật bị bỏ sót (SY@B).

| | OURS | X0 ngẫu nhiên | X3 đông người | X1 k-center | X2 YOLO phân vân | N2 tối | N1 mờ |
|---|---:|---:|---:|---:|---:|---:|---:|
| JA | **0,970** | 0,921 | 0,909 | 0,803 | 0,455 | 0,280 | 0,212 |
| JB | **1,000** | 0,943 | 0,932 | 0,765 | 0,492 | 0,273 | 0,197 |

- D (OURS − mạnh nhất X1..X3): JA +0,061 [−0,210; +0,268] · JB +0,068 [−0,258; +0,336] ⇒ **chưa chứng minh vượt bên thứ 3**.
- Chắc chắn: OURS hơn N1, N2, X2 với cả hai giám khảo (p_Holm ≤ 0,006) ⇒ độ khó đến từ vật thật, không từ ảnh xấu.
- **Nhãn thăm dò:** recall vật dễ của giám khảo chỉ ~0,84 (đăng ký trước 0,90, vì người đi bộ bị che); người quyết hạ ngưỡng sau khi xem CAL, lệch được ghi tự động trong report `533d6a16…`.

Quy trình, lỗi đã gặp, vá GPU trên Colab, việc cho V2: [judge-bench](judge-bench.md). Kịch bản trình bày: [judge-bench-script](judge-bench-script.md), [demoday-script](demoday-script.md) (slide 9–14 Demo Day).

### 3.3. PointPillars
| Bản | mAP | NDS | Ghi chú |
|---|---:|---:|---|
| mini-e80 (seed mặc định local) | 0,027 | 0,103 | 404 khung, chỉ thử quy trình |
| trainval e12/20 (A100) | **0,220** | **0,343** | 602 frame VAL; ô tô 0,790 · người đi bộ 0,132 · xe đạp 0,012 |

Chưa gắn PointPillars mới vào benchmark T hay AV2.

## 4. Kiểm thử gần nhất có bằng chứng

| Phép đo | Kết quả | Ngày / phạm vi |
|---|---|---|
| pytest benchmark + adapter | 126/126 | 17/10, `tests/bench`, `test_adapt_*`, `test_splits_override` |
| vitest | 265/265; bản 0.11.1: 38/38 (3 file) | 15/10; 18/10 |
| tsc / lint | 0 / 0 lỗi | 18/10 (0.11.1) |
| pytest lidar · vcf-pack | 118 · 15 | 15/10 |
| e2e panel | 2/2 | 15/10 |
| Full pytest worker | 488 pass / 3 fail / 3 skip | snapshot cũ; không công bố toàn repo xanh |

## 5. Việc còn lại

| Việc | Trạng thái |
|---|---|
| Commit bản 0.11.1 (gỡ banner, giữ Chế độ chuyên gia, chọn lại sau Tầng 1) | Phiên web còn thay đổi chưa commit |
| Judge-bench: thẩm định CPU độc lập, PandaSet, Pha 4 train-on-selection | Chưa chạy |
| Judge-bench V2: GPU novelty trong engine có cờ; định nghĩa vật dễ có che khuất; sao lưu Drive | Để kỳ sau |
| PointPillars e12 trong `rare_v24` | Cần phép đánh giá mới trên dữ liệu đủ lớn |
| Azure: A10 Tầng 1 end-to-end; sign-off hồ sơ 20 | Còn gate |
| Hồ sơ 11/12/13 | Còn sign-off |

Không mở lại T, không đổi freeze/prereg để cải thiện số báo cáo.

## 6. Cách kiểm lại

Đọc [getting-started](getting-started.md) để cài môi trường, [web](web.md) để dựng mock media. Từ root repo:

```powershell
model\worker\.venv\Scripts\python -m pytest -q model/worker/tests/bench model/worker/tests/test_splits_override.py
cd web
node node_modules/typescript/bin/tsc --noEmit
node node_modules/eslint/bin/eslint.js
node node_modules/vitest/vitest.mjs run
```

E2E job thật cần backend và job phù hợp; `demo-flow` A6 chủ động dừng worker.

Đọc tiếp: [README](../README.md) · [model-workflow](model-workflow.md) · [Colab](colab-dev-setup.md) · [GPU thuê](gpu-rental.md) · [judge-bench](judge-bench.md).
