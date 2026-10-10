> **Mới vào dự án? Đọc `docs/README_TONG_QUAN.md` trước** (tổng quan 10 phút cho cả team: flowchart, user story, cách đọc kết quả).


---

## 10. Cập nhật v2.1 (10/10) — thêm M0.5 Pilot + vòng phản biện song song thứ 3

**M0.5 trả lời câu hỏi "có nên chạy model trên tập nhỏ hiếm trước khi chạy to không"**:
CÓ, nhưng tách hai việc — (a) **sanity check model** trên 100–300 frame CÓ nhãn
(random + phân tầng) để bắt lỗi schema/IoU/độ recall theo slice và ra go/no-go;
(b) **pilot batch** vài trăm frame, gán tay top-B′ + random-B′ để so yield thật
trước khi đốt 40k keyframes. Frame pilot bị ép `split='PILOT'` — M6 tự loại, không leak.

```
M0 → M0.5a (PASS?) → M0.5b (GO?) → M1 → M2/M3 → M4 → M5 → [Gán nhãn] → M6
```

Hình đầy đủ: `docs/workflow_v2.png` (sinh lại bằng `python3 docs/make_diagram.py`).

```bash
# (a) sanity check — go/no-go trước khi scale:
python scripts/run_pilot.py sanity --source nuscenes --dataroot ... --version v1.0-mini \
    --n-random 150 --n-strat 50 --out pilot_sanity.json
# (b) lô thử nghiệm + 2 bảng gán tay:
python scripts/run_pilot.py batch --source nuscenes --dataroot ... --n-frames 800 \
    --budget 60 --out pilot_output
# chống leak khi chạy FULL POOL sau này:
python scripts/run_pipeline.py ... --exclude-fids pilot_output/pilot_fids.json   # xem run_pipeline
```

**Vòng phản biện song song thứ 3** (3 agent: vòng đời ML / ops+gán nhãn / sản phẩm+an toàn)
phát hiện 24 trường hợp còn thiếu — đã phân loại thành 3 đợt trong [`ROADMAP.md`](ROADMAP.md):
Wave 1 (label ledger, khoá hidden-GT, IAA, resume, ngân sách theo box, lock ranking),
Wave 2 (refit scorer, drift, schema versioning, scenario-ID ISO 21448, stop-rule),
Wave 3 (camera sidecar, privacy, dataset release, run manifest). Smoke tests nay là **7/7**.

## 11. Tài liệu phân tích
- [`docs/PHAN_TICH_CAC_LUONG.md`](docs/PHAN_TICH_CAC_LUONG.md) — mỗi module: làm gì, vì sao
  phải có (nếu bỏ thì vỡ gì), input/output, giúp ích gì, và **ý nghĩa từng metric** nó trả ra
  (cách đọc, ngưỡng, hành động) — cho người mới và người chấm kết quả, không cần đọc code.

## 12. Cập nhật v2.2 (10/10) — quyết định "Cả hai" + sửa chống leak

- **Model:** LÕI = checkpoint PointPillars công khai đóng băng. TUỲ CHỌN = Bước 0 train Seed
  + vòng retrain (`scripts/train_seed.py`, cờ `--model-mode seed --seed-manifest --retrain
  --explore-frac`). AP downstream chỉ báo khi `--retrain` bật; `report.json` có khối `model`.
- **Sửa leak:** `NuscenesSource` bản cũ nhận `split` nhưng không dùng → nạp cả scene train mà
  checkpoint công khai đã thấy. Nay `--split auto` (mặc định) = 150 scene val / 2 scene
  mini_val theo split chính thức; `split=all/train` với checkpoint công khai bị chặn.
- **Đáp án M6:** luật xa >30 m / <10 điểm chỉ tính VRU (`obj.far_few_scope="vru"`). Tính mọi
  lớp thì 404/404 keyframe mini là "hiếm" (đo thật trên nuScenes mini).
- **Đã chạy thật** trên nuScenes v1.0-mini (LiDAR keyframes, detector heuristic): pipeline +
  M6 chạy hết; mini_val chỉ 2 scene nên số liệu chưa có ý nghĩa báo cáo.
- Smoke tests: **10/10** (thêm `test_select_scenes`, `test_model_toggle`, `test_outlier_gate`).

## Thay đổi v2.3 (10/10/2026) — hiếm ≠ ngoại lai

- **Cổng ngoại lai** (`rare_mining/outlier_gate.py`) chạy sau M1: 4 phép thử không nhãn (hợp lệ
  dữ liệu, nhất quán thời gian theo điểm trong hệ toàn cục, hình học theo mặt đất cục bộ, k-NN tới
  V). Kết quả Hợp lệ / Nghi ngờ / Ngoại lai; chỉ Hợp lệ được chọn, còn lại ra `review_T.csv`.
- **OOD chỉ là cờ** (`ood_flag`, `frame.w_ood = 0`), không cộng vào điểm chọn.
- `report.json → outlier_gate`: số frame mỗi nhóm, phép thử lỗi giả trên V, tỉ lệ frame hiếm thật
  bị loại nhầm. Số đo trên nuScenes mini: `docs/README_TONG_QUAN.md` mục 4.
