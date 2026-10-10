# ROADMAP — các trường hợp còn thiếu (vòng phản biện song song thứ 3, 10/10/2026)

Ba agent độc lập rà lại workflow v2.1 (đã có M0.5 Pilot) từ 3 góc: **vòng đời ML**,
**vận hành dữ liệu & gán nhãn**, **sản phẩm/an toàn**. 24 finding, gộp thành 3 đợt
thực hiện. Verdict chung: workflow v2.1 đúng ở khâu CHỌN FRAME, còn hở ở khâu
**SAU pipeline** (handoff, truy vết, quản trị) và **XUYÊN VÒNG** (ledger, refit, drift).

## Wave 1 — bắt buộc trước vòng gán nhãn thứ 2

| Finding (nguồn) | Hành động | Trạng thái |
|---|---|---|
| F1 [CRITICAL] Pipeline one-shot, vòng 2 sẽ chọn lại frame đã gán (ML) | Label ledger: `exclude_fids` có sẵn trong `run_pipeline` dùng làm ledger v0; M4 lọc theo ledger trước khi rank | Cơ chế có sẵn, cần wire vào M4 |
| F3 [CRITICAL] Hidden-GT bị nhiễm sau vòng 1 — frame mined trùng GT giấu (ML) | Khoá pool GT giấu, loại khỏi quota gán nhãn; rút GT giấu mới theo version | Quy trình |
| IAA chưa đo — go/no-go đứng trên yield của 1 annotator (Ops) | Double-label 5–10% pilot + top-B; ngưỡng IoU ≥0.75, class acc ≥98%; senior adjudicate | Quy trình; thêm cột `annotator` vào gt.json |
| Không có resume/idempotency — crash 30k/40k mất 6 giờ (Ops) | `out_dir/<run_id>/`, checkpoint mỗi ~1k frame, ghi atomic | Code TODO nhỏ |
| Ngân sách tính theo frame nhưng thị trường tính theo box (~$0.12/box LiDAR) (Ops) | M0.5b đo objects/frame (median, p90) → quy B frame → ước box; quota & PO tính theo box | Recipe (recipe 9 ghi chú) |
| Bảng xếp hạng chưa version/lock — 2 đội gán trên 2 bản khác nhau (SP) | Ranking là artifact có version (hash), 1 owner, freeze theo tuần | Quy trình |

## Wave 2 — trước vòng 3 / trước khi scale toàn bộ

| Finding (nguồn) | Hành động |
|---|---|
| F2 [CRITICAL] Scorer/quota không cập nhật sau vòng 1 (ML) | Nhãn mới đổ vào V (re-split theo scene + thời điểm), refit IsolationForest/OOD trên nhãn tích lũy, quota tái phân bổ theo yield |
| F5 [MAJOR] Drift mùa/địa bàn làm OOD chai; split chưa cân thời gian (ML) | Split V/T theo scene + batch thời gian; drift monitor (density, intensity, class ratio) mỗi vòng |
| F6 [MAJOR] Scorer tự đuổi theo đuôi đã harvest sau 2–3 vòng (ML) | Giữ 10–20% budget exploration thuần (anchor random); theo dõi PSI phân phối score |
| Thiếu label schema versioning (Ops) | `schema_version` semver vào mọi output/GT, mapping cũ→mới, dự phòng budget relabel |
| QC hiệu chuẩn sensor thiếu ở M0 (Ops) | Reprojection error <2–3 px, timestamp sync <10 ms; scene lệch chuẩn → flag khỏi slice đêm |
| Không có truy vết frame → scenario → requirement (SP, ISO 21448) | Gán scenario-ID chuẩn cho từng frame, traceability matrix theo lô |
| Taxonomy chưa map quy chuẩn UN R152 (20–60 km/h) / Euro NCAP 2026+ (SP) | Map đặc trưng chọn frame vào taxonomy scenario chuẩn; ">30 m" → khoảng cách tới hạn theo vận tốc |
| Thiếu tiêu chí dừng + RACI (SP) | Stop-rule định lượng (recall trên hidden GT ≥ X%, coverage scenario ≥ Y%, N tuần yield không tăng) do safety manager ký |
| Báo cáo quản trị chưa có (SP) | Tầng report: burn-rate ngân sách, coverage scenario × điều kiện, ETA dựa trên SLA |

## Wave 3 — trước khi dùng camera / dùng nhãn làm evidence

| Finding (nguồn) | Hành động |
|---|---|
| Thêm camera KHÔNG phải bolt-on (Ops) | Thiết kế camera như sidecar channel có schema ngay từ M0 (sync, lưu trữ ×2, feature slicing) |
| Quyền riêng tư: mặt/biển số trong ảnh; point cloud dày tái tạo được dáng người (SP) | Blur/inpaint trước handoff, LiDAR trong môi trường kiểm soát, ghi DPIA |
| F7 (ML) Dataset versioning | `frame_id` bất biến, release nhãn theo tag, M6 pin đúng release |
| F8 (ML) Reproducibility GPU không deterministic | Run manifest: seed/commit/torch-CUDA/GPU/hash checkpoint + dataset |
| KPI/SLA đội gán + monitoring skew (Ops, SP) | Gold set ≥95% acc, TAT/batch; KL-divergence nhãn-đã-gán vs quota, cảnh báo tuần |

## Những gì KHÔNG làm và vì sao
- **Gán cả clip 20 Hz** (gợi ý từ Ops): chi phí tracking xuyên occlusion quá lớn cho mục tiêu
  khai thác hiếm — giữ keyframes only; chỉ mở khi AEB cần temporal labels, báo giá riêng.
- **Retrain model giữa các vòng** — v2.2 (quyết định 10/10 "Cả hai"): KHÔNG nằm trong lõi,
  nhưng đã có công tắc tuỳ chọn (`scripts/train_seed.py`, `--retrain`). Khi bật: ranking sinh
  lại toàn bộ + đo rank-overlap@B giữa 2 model (F4), sanity lại checkpoint mới, AP mới được báo.
