# Thuê GPU chạy model chọn 5% LiDAR

Tài liệu vận hành cho pipeline LiDAR.
Thiết kế gốc: C4-Rare-Scenario-Mining-MVP-Architecture.pdf.

| Bản | Chạy gì | Cần gì | Khi nào dùng |
|---|---|---|---|
| **L1 · local CPU** (Windows thuần) | Tầng 0 + web | Python 3.12 venv | Demo, dev, mọi máy |
| **L2 · local GPU Docker** (RTX 4060 8 GB) | Tầng 0 + Tầng 1 trên nuScenes-mini | Docker Desktop + WSL2 + NVIDIA | Thử Tầng 1, cổng G2 |
| **C · GPU thuê** (Ubuntu + Docker) | Toàn bộ trên trainval (28 130 keyframe) | GPU ≥ 16 GB, ~400 GB đĩa | Kết quả thật để báo cáo |
| **K · Google Colab** (tạm) | Tầng 0 + Tầng 1 với `--sweeps 1` | Notebook GPU T4/L4/A100 | Khi chưa thuê được máy |

Tầng 0 (descriptor hình học, CPU) là kết quả bắt buộc; Tầng 1 (PointPillars seed) là "nên có".
Thiếu Tầng 1 thì mọi thứ vẫn chạy với α = 1.

> Chạy ở máy cá nhân (CPU / RTX 4060 Docker): xem [run-local.md](run-local.md). Google Colab: [colab-dev-setup.md](colab-dev-setup.md).

Image Tầng 1 dùng chung cho cả ba nơi chạy GPU: **`vcuboidfit_pointpillars:0.1`** (container
`VCuboidFit_PointPillars`). Đổi tên image bằng biến `VCF_TIER1_IMAGE` — `model/scripts/tier1.ps1` và các
compose (`model/docker/tier1`, `model/docker/cloud`, `model/docker/worker`) đều đọc biến này.

## 3. C · gói GPU thuê

**Đóng gói trên máy local** (Git Bash):
```bash
bash scripts/cloud/pack.sh --with-image   # dist/vcf-cloud-<sha>.tar.gz + dist/vcf-tier1.tar.gz (~7 GB)
```
`vcf-tier1.tar.gz` chỉ là **tên gói tar** (giữ nguyên cho tương thích `pack.sh`/`bootstrap.sh`); image bên trong
là `vcuboidfit_pointpillars:0.1`. Không mang image thì máy thuê tự build (~20 phút) — gọn hơn khi upload chậm.

**Trên máy thuê** (Ubuntu 22.04, driver NVIDIA sẵn):
```bash
mkdir vcf && tar xzf vcf-cloud-*.tar.gz -C vcf && mv vcf-tier1.tar.gz vcf/ ; cd vcf
bash scripts/cloud/bootstrap.sh            # Docker + nvidia-container-toolkit + nạp/build image
export NUSC=/data/nuscenes EXP=/data/exp/trainval
docker compose -f docker/cloud/docker-compose.yml run --rm tier0
SWEEPS=10 EPOCHS=20 BATCH=8 docker compose -f docker/cloud/docker-compose.yml run --rm tier1
docker compose -f docker/cloud/docker-compose.yml run --rm experiment
# sau cổng G4 (đã chấm P): downstream M9 — so hybrid vs random trên T
DS_RUNS="hybrid_mmr random_0 random_1 random_2" docker compose -f docker/cloud/docker-compose.yml run --rm downstream
```
Downstream (`c4.lidar.tier1.downstream`) dùng CÙNG sweeps/epoch với model seed, kết quả
`$EXP/t1/downstream/<run>/eval.json` (mAP, NDS, AP từng lớp). Đã chạy thử trên mini (|A| = 7 — chỉ
kiểm script, không kết luận).

**Dữ liệu trainval** (cần tài khoản nuScenes của nhóm, đồng ý điều khoản): tải
`v1.0-trainval_meta` + 10 blob `v1.0-trainval{01..10}_blobs` (chỉ cần `samples/LIDAR_TOP` và
`sweeps/LIDAR_TOP`; có thể xoá camera/radar sau khi giải nén để còn ~ 300 GB). Link tải là link
ký tạm từ trang nuScenes — dán vào `wget -c` trên máy thuê.

**Chọn máy** (ước lượng, chưa đo trên trainval):

| GPU | VRAM | Batch gợi ý | Ghi chú |
|---|---|---|---|
| RTX 4090 / L4 | 24 GB | 8 | rẻ, đủ cho PointPillars |
| A10 / RTX 3090 | 24 GB | 8 | |
| A100 40/80 GB | 40–80 GB | 16 | nhanh nhất, đắt |
| T4 | 16 GB | 4 | chậm, chỉ khi rẻ |

Seed S ≈ 35 scene (~1 400 frame) ⇒ train seed nhanh; tốn thời gian nhất là infer 28 k frame × 2
lượt (gốc + lật) và downstream (M9, stretch). Tầng 0 trên 28 k frame: descriptor song song CPU —
chọn máy ≥ 16 vCPU.

**Cổng G4:** chỉ chạy `--split P` sau khi chép tham số đã tune vào `model/worker/configs/final.yaml`
(`params: {k, lam, m, weights}`) và tag `freeze-v1`. Script từ chối chấm P lần hai.

## 5. Lỗi hay gặp
| Hiện tượng | Cách xử |
|---|---|
| `UnicodeEncodeError cp1252` khi chạy CLI trên Windows | đã sửa trong CLI; script khác: `set PYTHONIOENCODING=utf-8` |
| `.ps1` báo lỗi cú pháp ở chữ tiếng Việt | file phải có BOM UTF-8 (PowerShell 5.1) |
| `libGL.so.1` / `No module named av2` / `np.int` trong container | đã xử lý trong Dockerfile (opencv headless, `patch_pcdet.py`) |
| `ZeroDivisionError` ở `balanced_infos_resampling` | seed thiếu lớp ⇒ `train_seed` tự tắt CBGS (ghi trong `t1/train_config.yaml`) |
| CUDA OOM | giảm `--batch`, rồi `--sweeps 1` |
| `tier_unavailable` trên web | chưa có `t1/signals.parquet` cho job — chạy Tầng 1 rồi chép `t1/` vào job |

