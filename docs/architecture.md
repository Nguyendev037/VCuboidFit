# Kiến trúc

Thiết kế gốc: [C4-Rare-Scenario-Mining-MVP-Architecture.pdf](C4-Rare-Scenario-Mining-MVP-Architecture.pdf) (C4 Rare Scenario Mining - MVP Architecture). Dưới đây là tóm tắt phần đã cài đặt.

## 1. Mục tiêu và phi mục tiêu

* Chọn **5 % keyframe `LIDAR_TOP`** đáng gán nhãn 3D, **chỉ từ point cloud + ego pose + timestamp**; không đọc
  annotation, camera hay `scene.description` (ngoại trừ module chấm điểm `gt.py`).
* **Tầng 0** (bắt buộc, CPU): descriptor hình học khối A-E -> PCA ~64 chiều -> Rarity k-NN (bỏ láng giềng cùng
  scene) -> MMR + quota theo scene.
* **Tầng 1** (nên có, GPU): PointPillars huấn luyện **từ đầu** chỉ trên seed S (OpenPCDet) -> embedding BEV, box
  gốc + box lật -> Novelty, Uncertainty (Entropy + Inconsistency) -> hybrid. Thiếu Tầng 1: alpha=1, beta=gamma=0.
* Không làm: dùng checkpoint công khai (rò mô hình đã thấy pool), encoder LiDAR học sẵn cho Tầng 0, normalizing
  flow, active learning nhiều vòng, chấm tập P trước khi đóng băng tham số.

## 2. Bất biến

1. **Nhãn một chiều:** chỉ `c4/lidar/gt.py` đọc annotation; chỉ `c4/lidar/eval.py` đọc ground truth rare. Test
   `test_no_leakage_lidar.py` quét import và chuỗi.
2. **Hợp đồng file:** mỗi module ghi bảng khoá `sample_token`; module sau chỉ đọc file.
3. **Một script chấm** cho mọi run. 4. **Tất định** (seed cố định, PCA bằng SVD, tie-break theo token).
5. **Không rò thời gian/scene** trong k-NN. 6. **Tầng 0 độc lập Tầng 1.** 7. Mỗi run ghi `config.yaml` (tham số, seed, git SHA).

## 3. Bản đồ module (`model/worker/c4/`)

| Module | File | Vai trò | Đọc nhãn |
|---|---|---|---|
| M1 | `lidar/index.py`, `splits.py`, `nusc_splits.py` | chỉ mục keyframe, chia S/V/P/T theo scene | không |
| M2 | `lidar/gt.py` | cell rare, `gt_rare_lidar` | có (duy nhất ghi) |
| M3 | `lidar/pcd.py`, `descriptor.py`, `extract.py` | khối A-E -> z0 (PCA), mặt nạ giữ, ảnh BEV | không |
| M4 | `lidar/tier1/train_seed.py` | PointPillars từ đầu trên S (Docker GPU) | chỉ S |
| M5 | `lidar/tier1/infer_t1.py` | z1, box gốc/lật, `signals.parquet` | không |
| M6 | `lidar/score.py`, `uncertainty.py` | Rarity, Ent/Inc/Nov, gộp hạng phần trăm | không |
| M7 | `lidar/select.py` (+ `mining/mmr.py`) | MMR + quota/scene, baseline | không |
| M8 | `lidar/eval.py` | recall, nRecall, uplift, coverage, redundancy | có (duy nhất đọc) |
| M9 | `lidar/tier1/downstream.py` | train S+A, chấm trên T (stretch) | S+A, T |
| M10 | `service/` + `web/` | API FastAPI + giao diện | chỉ trang đánh giá |
| Điều phối | `lidar/params.py`, `experiment.py`, `pipeline.py`, `cli/lidar_*.py` | tham số, ma trận thí nghiệm, đường web | qua eval |

Pipeline camera cũ (DINOv2/YOLO/CLIP, `c4/extract`, `c4/mining`) vẫn còn; đường LiDAR là mặc định.

## 4. Tham số người dùng chỉnh được (panel "Tham số nâng cao" trên web)

`k` (láng giềng), `lam` (mức đa dạng MMR), `m` (quota/scene), trọng số alpha/beta/gamma và bật/tắt Tầng 1.
Mặc định và lưới tune ở `model/worker/configs/lidar.yaml`. Chỉ tune trên tập V: lưới k x lam x m (48 cấu hình)
và (alpha, beta) khi có Tầng 1; phần còn lại cố định. Chấm tập P một lần duy nhất, sau khi đóng băng
`configs/final.yaml` (tag `freeze-v1`).

## 5. Luồng dữ liệu

```text
upload (web, chunk 50 MB) -> <WORKSPACE>/uploads/<id>/  -> giải nén + kiểm cấu trúc nuScenes
  -> <WORKSPACE>/datasets/<id>/data/ -> job: lidar_index (index.parquet, filter, BEV) -> t0 (descriptor, score, select)
  -> jobs/<id>/lidar/*.parquet + selected_5pct.csv -> API /jobs/{id}/select, /frames -> web
```
Bảng dữ liệu có manifest kèm theo (`SCHEMA_VERSION` trong `c4/contracts.py`); ghi `.tmp` rồi `os.replace`.

## 6. Kiểm thử

`pytest -m "not perf and not gpu" tests/lidar tests/service/test_lidar.py tests/service/test_models.py` (model CPU);
`npx tsc --noEmit` + `npx vitest run` (web). Test camera trong `tests/service/` cần thêm torch (`.[gpu]`).
Chi tiết cách chạy: [run-local.md](run-local.md).
