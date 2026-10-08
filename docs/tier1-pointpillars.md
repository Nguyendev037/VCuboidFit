# Tầng 1 — PointPillars seed và tín hiệu model

Tài liệu này bám theo `worker/c4/lidar/tier1/`, `uncertainty.py`,
`docker/tier1/`, `scripts/tier1.ps1`, `scripts/tier1.sh`,
`docker/cloud/docker-compose.yml` và
[`SPEC-P02-T1-PointPillars.md`](../../../planning/04_2026-10-08_lidar-mining-pivot/specs/SPEC-P02-T1-PointPillars.md).
Tầng 1 là tùy chọn; nếu chưa có model, Tầng 0 vẫn chạy với `α=1`.

## 1. Sơ đồ chạy

```text
index.parquet + nuScenes
          │
          ▼
train_seed.py ──> t1/pcdet/infos_seed.pkl
              ├─> t1/pcdet/infos_all.pkl
              ├─> t1/train_config.yaml
              ├─> t1/seed_tokens.txt
              └─> t1/ckpt/seed_latest.pth
          │
          ▼
infer_t1.py ──> preds_orig.pkl + preds_flip.pkl
             ├─> z1.npy
             ├─> signals.parquet
             └─> seed_eval.json
          │
          ▼
lidar_experiment --split V --tune
  └─> hybrid_mmr / t1_*_mmr / entropy_only
```

| Thành phần | Vai trò | Môi trường |
|---|---|---|
| `train_seed.py` | Tạo info và train PointPillars từ đầu trên S | Trong Docker hoặc môi trường pcdet |
| `infer_t1.py` | Suy luận gốc/lật trên mọi keyframe, lấy `z1` và tín hiệu | GPU |
| `uncertainty.py` | Entropy, bất nhất lật, novelty, percentile | CPU thuần NumPy |
| `downstream.py` | M9, huấn luyện so sánh sau khi chấm P | GPU, stretch |
| `Dockerfile` | PyTorch/CUDA/OpenPCDet reproducible | Docker |
| `tier1.ps1/.sh` | Runner train → infer | Windows/Linux/Kaggle |

## 2. Image, GPU và VRAM

| Hạng mục | Giá trị đã ghim |
|---|---|
| Base | `pytorch/pytorch:2.1.2-cuda11.8-cudnn8-devel` |
| OpenPCDet | commit `233f849829b6ac19afb8af8837a0246890908755` |
| spconv | `spconv-cu118==2.3.6` |
| NumPy | `1.26.4` |
| CUDA arch | `7.5;8.0;8.6;8.9;9.0+PTX` |
| Mount dữ liệu | `/nusc:ro` |
| Mount thí nghiệm | `/exp` |
| Mount code | `/work/worker` |
| Shared memory local | `8g` trong script; cloud image dùng `16g` |

| GPU | VRAM | Batch gợi ý | Ghi chú |
|---|---:|---:|---|
| RTX 4060 Laptop | 8 GB | 2, giảm 1 khi OOM | Cổng L2 local |
| T4 | 16 GB | 4 | Kaggle/Colab, chậm |
| L4 / RTX 4090 / A10 / RTX 3090 | 24 GB | 8 | Gói GPU thuê |
| A100 | 40–80 GB | 16 | Nhanh nhất, chi phí cao |

Nếu thiếu VRAM: giảm `--batch` trước, sau đó dùng `--sweeps 1`; **cùng giá trị
sweeps phải được dùng cho downstream**. CUDA OOM trả mã 3 và in gợi ý
`--batch 1 --sweeps 1`. Không có GPU cũng trả mã 3; Tầng 0 không bị ảnh hưởng.

## 3. File `t1/` và contract

| File | Nội dung | Điều kiện |
|---|---|---|
| `t1/pcdet/infos_seed.pkl` | Info chỉ token `split=="S"` | Phải là tập con S |
| `t1/pcdet/infos_all.pkl` | Info mọi keyframe theo thứ tự index | Dùng cho infer |
| `t1/ckpt/seed_latest.pth` | Checkpoint model seed | Không dùng pretrained công khai |
| `t1/train_config.yaml` | Config, sweeps, epoch, batch, CBGS | Ghi cả việc tắt CBGS nếu seed thiếu lớp |
| `t1/seed_tokens.txt` | Token seed đã train | Đối chiếu leakage |
| `t1/z1.npy` | Embedding `spatial_features_2d` mean theo H/W | Một dòng mỗi index |
| `t1/preds_orig.pkl` | Dự đoán lượt gốc | Theo thứ tự index |
| `t1/preds_flip.pkl` | Dự đoán lượt lật rồi đưa về hệ gốc | Theo thứ tự index |
| `t1/signals.parquet` | `ent`, `inc`, `n_det`, `nov`, `sample_token` | Hợp đồng `t1_signals` |
| `t1/seed_eval.json` | mAP/NDS trên T | `null` + lý do nếu thiếu devkit |

Ngưỡng điểm box là `0.1`; lật point cloud dùng `y → -y`, box trả về bằng
`y → -y`, `yaw → -yaw`, và `vy → -vy` nếu có.

## 4. Tín hiệu và cách đọc

| Tín hiệu | Cách tính | Tên glossary |
|---|---|---|
| `nov`/`r_nov` | Khoảng cách embedding `z1` tới frame seed | **Lạ với model** |
| `ent` | Entropy Bernoulli trung bình từ score box | Thành phần bất định |
| `inc` | `1 - số box ghép được / max(số box hai lượt,1)` | Thành phần bất định |
| `r_unc` | `0.5 × percentile(ent) + 0.5 × percentile(inc)` | **Model chưa chắc chắn** |
| `r_rar` | Tầng 0 k-NN khác scene | **Độ hiếm (ước lượng)** |

Nếu không có frame seed, novelty là vector 0. Không được gọi percentile trên
vector toàn 0 để hiển thị p50 giả; gotcha này được ghi trong
[`-known-gotchas.md`](../../../brain4agent/-known-gotchas.md).

## 5. Lệnh Windows

Từ thư mục `vcuboidfit`:

```powershell
docker build -t vcf-tier1:0.1 docker\tier1
.\scripts\tier1.ps1 `
  -Data H:\ `
  -Exp .\workspace\experiments\mini `
  -Sweeps 10 -Epochs 20 -Batch 2
```

Script yêu cầu `<Exp>\index.parquet` đã có; hãy chạy Tầng 0 trước. Script mount
nuScenes read-only, output ra volume `/exp`, rồi chạy tuần tự `train_seed` và
`infer_t1`. `ErrorActionPreference` của lệnh Docker được hạ xuống `Continue`;
kết luận dựa trên `$LASTEXITCODE`, vì PowerShell 5.1 coi stderr Docker là lỗi.

## 6. Lệnh Linux/Docker và không Docker

```bash
docker build -t vcf-tier1:0.1 docker/tier1
bash scripts/tier1.sh /data/nuscenes /data/exp/mini \
  --sweeps 10 --epochs 20 --batch 8
python -m c4.cli.lidar_experiment \
  --data-root /data/nuscenes --out /data/exp/mini --split V --tune
```

Kaggle/Colab đã cài OpenPCDet có thể bỏ Docker:

```bash
export PCDET_ROOT=$PWD/OpenPCDet
echo 233f849829b6ac19afb8af8837a0246890908755 > "$PCDET_ROOT/BUILD_COMMIT"
bash scripts/tier1.sh "$NUSC" "$EXP" --no-docker --sweeps 1 --epochs 20 --batch 4
```

`--no-docker` bắt buộc `PCDET_ROOT/BUILD_COMMIT`; script chạy Python trực tiếp
trong worker. Dùng `--sweeps 1` khi dữ liệu chỉ có keyframe hoặc RAM/đĩa hạn chế,
và ghi rõ điều này trong báo cáo.

## 7. GPU thuê qua Compose

```bash
export NUSC=/data/nuscenes EXP=/data/exp/trainval
docker compose -f docker/cloud/docker-compose.yml run --rm tier0
SWEEPS=10 EPOCHS=20 BATCH=8 \
  docker compose -f docker/cloud/docker-compose.yml run --rm tier1
docker compose -f docker/cloud/docker-compose.yml run --rm experiment
```

`tier0` chạy CPU; `tier1` yêu cầu NVIDIA runtime; `experiment` tune trên V. M9
`downstream` chỉ chạy sau khi đã chấm P:

```bash
DS_RUNS="hybrid_mmr random_0 random_1 random_2" \
docker compose -f docker/cloud/docker-compose.yml run --rm downstream
```

Các biến `NUSC`, `EXP`, `SWEEPS`, `EPOCHS`, `BATCH`, `DS_RUNS` là đầu vào vận hành,
không phải tham số để thay đổi contract dữ liệu.

## 8. Không rò nhãn và vùng cấm

| Cấm | Vì sao |
|---|---|
| `gt_sampling` trong `DATA_AUGMENTOR` | DB có thể lấy nhãn từ V/P, làm model nhìn đáp án |
| `--pretrained_model` hoặc checkpoint công khai | Seed phải train từ đầu |
| Đổi sweeps giữa train seed và downstream | So sánh không còn công bằng |
| Chạy Tầng 1 trong web runner | GPU job dài; web chỉ đọc `t1/` có sẵn |
| Tự kết luận từ `seed_eval` thiếu devkit | Script ghi `null` và lý do, không giả dữ liệu |

Nếu `infos_seed.pkl` rỗng, script trả mã 2. Sau khi chạy xong, gọi lại
`lidar_experiment --split V --tune` để sinh các run hybrid/Tầng 1; web chỉ mở
Tầng 1 khi job có `t1/signals.parquet`.

## 9. Lỗi đã gặp và xử lý

| Hiện tượng | Xử lý |
|---|---|
| CUDA OOM | `--batch 1`, rồi `--sweeps 1`; giữ sweeps cho downstream |
| Không có GPU | Không chạy Tầng 1; dùng Tầng 0 CPU |
| `tier_unavailable` trên web | Chạy train + infer, chép `t1/` đúng job |
| Docker không apt/git được | Dockerfile không dùng apt/git; tải tarball HTTPS |
| `libGL.so.1` hoặc `av2` | Image dùng OpenCV headless và patch OpenPCDet |
| `np.int`/`np.float`/`np.bool` | Chạy `patch_pcdet.py`; không sửa bằng sed mù |
| `balanced_infos_resampling` chia 0 | Seed thiếu lớp: train tự tắt CBGS |
| PowerShell lỗi chữ Việt | `.ps1` phải UTF-8 có BOM |
| output Windows lỗi cp1252 | Đặt `PYTHONIOENCODING=utf-8` cho runner ngoài CLI |

## 10. Mốc thực tế

Trên mini hiện có: 20 epoch khoảng 5 phút và đỉnh khoảng 5.4 GB VRAM; infer đủ
404 frame; model seed cold-start từng cho 0 box, còn bản e80 đạt mAP `0.027`,
NDS `0.103` trên T. Đây là số liệu vận hành của mini, không phải kết luận
trainval. Nhóm C khoảng 100% trên mini cũng là dấu hiệu định nghĩa đang quá rộng,
không phải chất lượng Tầng 1.
