# Engine Tầng 0 — pipeline LiDAR hình học

Tài liệu này mô tả **đúng code hiện tại** trong `worker/c4/lidar/`, hai cấu hình
`worker/configs/lidar.yaml`, `worker/configs/gt.yaml` và
[`SPEC-P01-T0-Engine.md`](../../../planning/04_2026-10-08_lidar-mining-pivot/specs/SPEC-P01-T0-Engine.md).
Tầng 0 chạy CPU, chọn bằng **Độ hiếm (ước lượng)**; nhãn chỉ xuất hiện trong bước
đánh giá, không đi vào mining.

## 1. Sơ đồ luồng

```text
nuScenes H:/
   │
   ├─ index.py + splits.py ──> index.parquet
   │                            (sample_token, scene, pose, split)
   ├─ pcd.py ──> descriptor.py ──> extract.py
   │                              ├─ desc_raw.npz
   │                              ├─ filter.parquet
   │                              └─ bev/*.png
   ├─ embed() ──> z0 ──> score.py ──> rarity / S
   ├─ select.py ──> MMR, random, coreset, top-k
   └─ eval.py <── gt.py chỉ đọc nhãn ──> metrics.json

 experiment.py ── chuẩn bị cache, tune trên V, ghi report
 pipeline.py   ── luồng web: lidar_index → t0 → select
```

| Mô-đun | Trách nhiệm | Có được đọc nhãn không? |
|---|---|---|
| `index.py` | Lấy keyframe `LIDAR_TOP`, pose ego, yaw, kiểm tra file | Không |
| `splits.py` | Chia scene thành T/S/V/P theo seed | Không |
| `pcd.py` | Đọc float32 `(x,y,z,intensity,ring)` và tiền xử lý | Không |
| `descriptor.py` | Tính các khối hình học, PCA embedding | Không |
| `extract.py` | Chạy descriptor song song, ghi cache | Không |
| `score.py` | k-NN khác scene, percentile, gộp điểm | Không |
| `select.py` | MMR và baseline | Không |
| `gt.py` | Tạo `gt_rare_lidar`, tần suất cell | **Có; duy nhất** |
| `eval.py` | Recall, uplift, precision, coverage, bootstrap | Nhận truth đã tạo |
| `experiment.py` | Chạy ma trận, tune, ablation, report | Chỉ qua `eval` |
| `pipeline.py` | Điều phối cho job web và cache fingerprint | Không tự đọc GT để chọn |

## 2. Chỉ mục và chia tập

`build_lidar_index(t, data_root)` duyệt sample có `LIDAR_TOP` là keyframe, file
tồn tại, rồi ghi pose ego và `frame_idx` theo chuỗi `next`. `assign_splits` chia
theo **scene**, không chia ngẫu nhiên từng frame:

| Tập | Vai trò | Quy tắc |
|---|---|---|
| T | Seed/đánh giá model Tầng 1 | trainval: phần train; mini: `scene-0103`, `scene-0916` |
| S | Seed có nhãn cho PointPillars | `ceil(S_frac * train)`; mini: 2 scene |
| V | Tune và so sánh phương pháp | `V_scenes`; mini: 3 scene |
| P | Pool chấm cuối | Phần còn lại; chỉ chấm sau `final.yaml` |

Không một scene nào được nằm ở hai split. `scene_token` là đơn vị chống rò giữa
train/tune/eval.

## 3. Descriptor hình học

### 3.1 Tiền xử lý cố định

| Khoá | Giá trị | Ý nghĩa |
|---|---:|---|
| `pcd.remove_close_m` | `1.0` | Bỏ điểm có `|x|, |y| < 1 m` |
| `pcd.crop_m` | `50.0` | Cắt vùng BEV ±50 m |
| `pcd.voxel_m` | `0.2` | Giữ điểm đầu trong voxel sau sort tất định |
| `filter.min_points` | `2000` | Sau remove-close, trước crop |
| `pca_dim` | `64` | Kích thước embedding cuối |

### 3.2 Các khối đặc trưng

| Khối | Nội dung |
|---|---|
| A — range | Histogram khoảng cách theo `range_bins_m`, chuẩn hóa tổng 1, kèm `log(n)` |
| B — height | Histogram z từ `-3` đến `5 m`, bước `0.5 m`, chuẩn hóa |
| C — BEV | Histogram đếm lưới cell `2 m`, kích thước `50×50` |
| D — cụm | Mặt đất RANSAC; DBSCAN trên điểm ngoài mặt đất; số cụm, histogram kích thước và BEV, cụm nhỏ-xa |
| E — cảm biến | Tỉ lệ điểm ngoài mặt đất trong 3 m, intensity trung bình và độ lệch chuẩn |

`embed` z-score từng cột; cột có độ lệch chuẩn bằng 0 thành 0; chia khối cho
`sqrt(số chiều khối)`, ghép rồi PCA bằng SVD. Dấu thành phần PCA được chuẩn hóa
tất định. `drop_blocks` chỉ dành cho ablation, không phải đường chạy mặc định.

## 4. File đầu ra

| Giai đoạn | Đường dẫn | Nội dung |
|---|---|---|
| Index | `<out>/index.parquet` | Hợp đồng `lidar_index` |
| GT đánh giá | `<out>/gt/gt_rare_lidar.parquet` | Chỉ dùng bởi eval |
| Tần suất cell | `<out>/gt/cell_freq.csv` | Bảng kiểm tra G1 |
| Extract | `<out>/desc_raw.npz` | Descriptor thô và token |
| Filter | `<out>/filter.parquet` | `keep`, `reason`, số điểm |
| Hình | `<out>/bev/<token>.png` | BEV minh họa |
| Experiment | `<out>/<split>/<run>/selected_5pct.csv` | Frame được chọn |
| Metrics | `<out>/<split>/metrics.json` | Chỉ số theo run |
| Report | `<out>/<split>/report_selection.md` | Bảng so sánh, tune, ablation |
| Web selection | `<job>/out/selections/<sid>/` | `result.json`, `scores.parquet`, `selected.csv` |

Lỗi file point cloud thiếu/hỏng đặt `keep=false`, `reason=read_error`; ít hơn
`min_points` đặt `reason=few_points`. RANSAC/DBSCAN suy biến thì khối D/E bằng
0. Nếu toàn bộ frame không hợp lệ, pipeline ném
`ValueError("Không có frame LiDAR hợp lệ")` và job thất bại mã 4.

## 5. Tham số cố định và tham số tune

| Nhóm | Cố định trước | Tune được ở V |
|---|---|---|
| Lọc/descriptor | remove-close, crop, voxel, min-points, bins, RANSAC, DBSCAN, PCA | Không |
| Rare theo nhãn | `tau=0.02`, distance/points bins, class map | Không sau khi chốt G1 |
| Score | percentile và k-NN khác scene | `k ∈ {5,10,20}` |
| Đa dạng | MMR `min_gap=1` | `lam ∈ {0.5,0.7,0.9,1.0}` |
| Quota cảnh | Mặc định `m=4` | `m ∈ {2,4,8,None}` |
| Trọng số | Tầng 0 luôn `[α,β,γ]=[1,0,0]` | Tầng 1 mới tune preset/weights |
| Bootstrap | 200 lần, seed 0 | Không đổi trong nghiệm thu |

`rarity(z, scene, k)` chỉ tìm láng giềng ở **scene khác** trong mảng đang truyền
vào. `combine` tạo điểm `S`; với Tầng 0, `r_nov` và `r_unc` không được giả tạo
bằng percentile của mảng toàn số 0.

## 6. Ví dụ chạy `lidar_experiment`

Từ `vcuboidfit\worker` trên Windows:

```powershell
.venv\Scripts\python -m c4.cli.lidar_experiment `
  --data-root H:\ `
  --out ..\workspace\experiments\mini `
  --split V --tune --bootstrap 200
```

Chạy cố định một bộ tham số sau khi đã tune:

```powershell
.venv\Scripts\python -m c4.cli.lidar_experiment `
  --data-root H:\ --out ..\workspace\experiments\mini `
  --split V --tier 0
```

Trên Linux thay interpreter bằng `python`. `--split P` bị từ chối nếu chưa có
`worker/configs/final.yaml` đã chốt và tag `freeze-v1`; đây là cổng G4, không phải
shortcut để xem kết quả sớm.

## 7. Chống rò nhãn

| Quy tắc | Ý nghĩa kiểm chứng |
|---|---|
| Chỉ `gt.py` được import bảng annotation | Mining vẫn không biết nhãn |
| `pcd/descriptor/extract/score/select` không import `gt` và không đọc `gt/` | Không chọn theo rare thật |
| `eval.py` mới nhận `Truth`/`gt_rare_lidar` | Recall là phép chấm độc lập |
| Tầng 1 chỉ train trên S | Không đưa V/P vào `infos_seed.pkl` |
| PCA và k-NN fit trên tập đang chọn, không trộn scene | Không nhìn tương lai |
| P chỉ chạy một lần sau `final.yaml` | Tránh tune trên tập báo cáo |

Theo glossary, **Độ hiếm (ước lượng)** là tín hiệu để chọn; **Hiếm thật (theo
nhãn)** chỉ dùng để chấm. Nhầm hai khái niệm này sẽ làm sai cả báo cáo lẫn kết
luận khoa học.
