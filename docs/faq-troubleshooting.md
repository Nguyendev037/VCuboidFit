# FAQ và xử lý sự cố

Phạm vi này tổng hợp cách cài/chạy thật trong
[`chay-model-gpu.md`](gpu-rental.md), trạng thái bàn giao trong
[`HANDOFF.md`](run-local.md), các gotcha đã ghi ở
[`-known-gotchas.md`](../../../brain4agent/-known-gotchas.md) và bộ dữ liệu
[`H:/vcf_test_data/README.md`](../../../H:/vcf_test_data/README.md). Đường dẫn
`H:\` dưới đây là ổ dữ liệu nuScenes trên máy Windows.

## 1. Nên bắt đầu từ đâu?

| Mục tiêu | Chọn | Cần |
|---|---|---|
| Chạy demo, kiểm tra web, không GPU | L1 — Tầng 0 CPU | Python 3.12, venv |
| Thử PointPillars local | L2 — Docker | Docker Desktop, WSL2, NVIDIA |
| Kết quả trainval thật | C — GPU thuê | Ubuntu, Docker, GPU ≥16 GB, khoảng 400 GB |
| Chưa thuê máy | K — Kaggle/Colab | GPU notebook, `--sweeps 1` |

Tầng 0 là bắt buộc và không cần model. Tầng 1 chỉ mở khi job có
`t1/signals.parquet`; thiếu Tầng 1 không ngăn chọn bằng **Độ hiếm (ước lượng)**.

## 2. Cài đặt Windows CPU

```powershell
cd vcuboidfit\worker
python -m venv .venv
.venv\Scripts\pip install -e ".[dev,service]" scikit-learn joblib pillow
.venv\Scripts\python -m c4.cli.lidar_experiment `
  --data-root H:\ `
  --out ..\workspace\experiments\mini `
  --split V --tune --bootstrap 200
```

Python máy là 3.12 và repo chưa dùng `uv`; dùng đúng `python -m venv`. Nếu
torch CUDA cài thành bản CPU, hãy cài torch bằng `--index-url` CUDA trước rồi
mới cài extra GPU; `--extra-index-url` có thể vẫn lấy wheel CPU từ PyPI.

| Kiểm tra | Kỳ vọng |
|---|---|
| `<out>/index.parquet` | Có sau bước index/Tầng 0 |
| `<out>/V/report_selection.md` | Báo cáo tune |
| `<out>/V/metrics.json` | Metrics của các run |
| `<out>/V/<run>/selected_5pct.csv` | Danh sách frame |

## 3. Dùng `H:\vcf_test_data`

| Bộ | Quy mô | Dùng khi |
|---|---:|---|
| `01_small_3scenes` | 3 scene, 121 keyframe, khoảng 912 MiB | Test upload nhanh, scene đêm, UI |
| `02_full_mini_10scenes` | 10 scene, 404 frame, khoảng 5 GiB | Chạy pipeline thật và Tầng 1 |

Khi upload web, chọn **tất cả** `vcf_part_*.zip` và `vcf_manifest.json` của
một thư mục; không trộn hai bộ. Server nhận chunk 50 MB, giải nén vào `data/`
rồi kiểm tra cấu trúc nuScenes.

```text
01_small_3scenes/
02_full_mini_10scenes/
```

Tầng 1 chỉ được dùng artifact mini đầy đủ:
`workspace/experiments/mini-e80/t1/signals.parquet`. Không chép artifact này
vào job của bộ nhỏ vì sample token khác nhau. Dữ liệu gốc `H:/v1.0-mini`,
`H:/samples`, `H:/sweeps` không bị sửa.

## 4. PowerShell, BOM và mã hóa

| Triệu chứng | Nguyên nhân | Cách xử lý |
|---|---|---|
| `.ps1` lỗi cú pháp ở chữ tiếng Việt | PowerShell 5.1 đọc sai UTF-8 không BOM | Lưu script UTF-8 có BOM |
| CLI pipe/redirect lỗi `UnicodeEncodeError: cp1252` | stdout Windows không phải UTF-8 | `set PYTHONIOENCODING=utf-8` |
| Docker stderr làm script dừng | `$ErrorActionPreference=Stop` coi stderr là exception | Runner đã đặt `Continue`, chỉ tin `$LASTEXITCODE` |
| Python log bị mojibake | Console code page | Chạy terminal UTF-8 hoặc đặt biến môi trường trên |
| Sửa regex bằng sed làm mất `\b`/`\1` | Shell escape chuỗi thay thế | Dùng script Python có test, kiểm tra lại token/mã regex |

Ví dụ:

```powershell
$env:PYTHONIOENCODING = "utf-8"
.\scripts\tier1.ps1 -Data H:\ -Exp .\workspace\experiments\mini
```

## 5. Docker local và lỗi IDM

Build image:

```powershell
cd vcuboidfit
docker build -t vcf-tier1:0.1 docker\tier1
.\scripts\tier1.ps1 -Data H:\ -Exp .\workspace\experiments\mini `
  -Sweeps 10 -Epochs 20 -Batch 2
```

Mạng local có thể chặn `archive.ubuntu.com:80`; Dockerfile không dùng `apt`/`git`,
OpenPCDet tải tarball HTTPS và `patch_pcdet.py` vá import Argo2, alias NumPy.
`nuscenes-devkit` cần OpenCV headless để tránh `libGL.so.1`.

Nếu IDM tự tải file point cloud thay vì viewer đọc, đây là chủ ý tương thích:
URL media dùng đuôi `.f16`, route map vào file thật `.bin` và trả MIME riêng
`application/x-vcf-lidar-f16`. Xem thêm [API reference](api-reference.md#7-media-route-và-lý-do-dùng-f16).

## 6. Docker cloud / Kaggle / Colab

GPU thuê:

```bash
export NUSC=/data/nuscenes EXP=/data/exp/trainval
docker compose -f docker/cloud/docker-compose.yml run --rm tier0
SWEEPS=10 EPOCHS=20 BATCH=8 \
  docker compose -f docker/cloud/docker-compose.yml run --rm tier1
docker compose -f docker/cloud/docker-compose.yml run --rm experiment
```

Kaggle/Colab không có Docker:

```bash
export PCDET_ROOT=$PWD/OpenPCDet
echo 233f849829b6ac19afb8af8837a0246890908755 > "$PCDET_ROOT/BUILD_COMMIT"
bash scripts/tier1.sh "$NUSC" "$EXP" --no-docker --sweeps 1 --epochs 20 --batch 4
```

`--no-docker` cần `PCDET_ROOT` đã build và `BUILD_COMMIT`. Với `--sweeps 1`,
chỉ dùng keyframe, phải ghi rõ trong báo cáo và giữ nguyên cho downstream.
Kết quả `t1/ckpt`, `t1/*.pkl`, `features/` nên được chép ra Drive/Kaggle
Output sau từng bước để phiên notebook bị ngắt không mất dữ liệu.

## 7. RAM, VRAM và tốc độ

| Vấn đề | Cách xử lý |
|---|---|
| CUDA OOM | Giảm `--batch`, sau đó `--sweeps 1`; mã thoát 3 |
| RAM/đĩa thiếu | Dùng bộ nhỏ hoặc `--sweeps 1`; không trộn artifact |
| Docker hết shared memory | Giữ `--shm-size 8g` local; cloud compose dùng image 16g |
| Tầng 0 chậm | Chọn `n_jobs` phù hợp số lõi; mini khoảng 20 ms/frame descriptor |
| infer lâu trên trainval | Đây là 2 lượt gốc+lật cho 28k frame; dành GPU đủ VRAM |
| CPU cài thiếu `filelock/sklearn/joblib/Pillow` | Cài core/dev dependency đúng pyproject |

Số đo mini tham khảo: 404 frame, descriptor khoảng 20 ms/frame trên 32 lõi,
chọn+chấm khoảng 4 giây; PointPillars 20 epoch khoảng 5 phút và 5.4 GB VRAM.
Đây là benchmark mini, không suy ra trainval.

## 8. `Recall 0%` trên bộ nhỏ có phải bug?

Không kết luận từ một bộ nhỏ. Bộ `01_small_3scenes` chỉ có 121 frame; nếu
`gt_rare_lidar` không có cell rare hoặc ngân sách 5% quá nhỏ, Recall có thể là
0% hợp lệ. Bộ mini 404 frame hiện từng cho Tầng 0 recall `0.133` so với random
`0.053`, nhưng tài liệu bàn giao ghi rõ **chưa kết luận**.

Kiểm tra theo thứ tự:

1. Xem `gt/cell_freq.csv`, `gt/gt_rare_lidar.parquet`.
2. Xác nhận đang đọc đúng split V và đúng `budgetB`.
3. So với 10 lần random, không chỉ một random seed.
4. Xem `byGroup` và nhóm C riêng.

Glossary phân biệt **Độ hiếm (ước lượng)** dùng để chọn và **Hiếm thật (theo
nhãn)** dùng để chấm. Dataset không có nhãn thì Recall phải ẩn, không tự coi
0% là model hỏng.

## 9. Vì sao nhóm C rộng hoặc gần 100%?

Nhóm C là vật ở xa hơn 40 m với tối đa 5 điểm LiDAR hoặc visibility thấp. Trên
mini, nhóm C khoảng 100% frame; đây là định nghĩa quá rộng/bão hòa đã được ghi
ở gotcha. Không sửa ngưỡng sau khi thấy metrics; chờ cổng G1 và bảng đếm
trainval để chốt lại `tau`, cell và nhóm C trong kế hoạch.

## 10. “Tầng 1 bị khóa” trên web

`tier_unavailable` nghĩa là job chưa có `t1/signals.parquet`, không phải web
hỏng. Cách xử lý:

| Bước | Việc |
|---:|---|
| 1 | Chạy Tầng 0 để có `index.parquet` |
| 2 | Chạy `train_seed` rồi `infer_t1` bằng cùng sweeps |
| 3 | Kiểm tra `t1/signals.parquet` có đủ sample token |
| 4 | Chép toàn bộ `t1/` vào đúng `<workspace>/jobs/{jobId}/t1/` |
| 5 | Gọi lại `GET /jobs/{id}/params-schema`, sau đó select `tier:1` |

Tầng 1 không chạy trong web runner vì là GPU job dài. Nếu chọn `tier:1` trước
bước 3, API trả HTTP 422 `tier_unavailable`; đây là lỗi có chủ đích.

## 11. Mở lại lần chạy cũ

Job và selection lưu trên đĩa; reload không cần POST lại job:

```bash
curl http://localhost:8008/jobs
curl http://localhost:8008/jobs/{jobId}
curl http://localhost:8008/jobs/{jobId}/selections
curl http://localhost:8008/jobs/{jobId}/selections/{selectionId}
```

Khi restore selection LiDAR, tham số quota đã resolve là `m`, không phải
`maxPerScene`; phải giữ `lam`, weights và tier. Nếu service vừa restart mà GET
vẫn trả 405, process uvicorn cũ chưa được restart đúng workspace; kiểm tra
`WORKSPACE` rồi khởi động lại trước khi kết luận proxy hỏng.

## 12. Nhập dữ liệu mới

Không chép `t1/` hoặc cache của job cũ sang dataset mới trừ khi sample token
khớp. Quy trình an toàn:

1. Upload đúng một bộ archive và manifest.
2. Finalize, chờ `DatasetReport.ok=true`.
3. Tạo job với `pipeline:"lidar"`.
4. Chờ stage `lidar_index` và `t0` thành `done`.
5. Chọn Tầng 0; chỉ thêm Tầng 1 sau khi train/infer đúng dataset.

Lỗi `missing_input` thường là job thiếu index/cache; lỗi `contract` là file có
token/thứ tự/schema không khớp. Không xóa workspace để chữa lỗi trước khi giữ
lại `status.json`, `report.json` và log stage.

## 13. Sự cố thường bị hiểu nhầm

| Hiện tượng | Diễn giải đúng |
|---|---|
| `seed_eval.json` là `null` | Thiếu devkit eval; script vẫn hoàn tất, ghi lý do |
| Tầng 1 cold-start 0 box | Số đo đã từng gặp trên mini; không tự đổi threshold |
| `np.int` trong OpenPCDet | Cần patch đúng commit, không sed bừa |
| `test_perf_10k_frames` chập chờn | Chạy riêng 3 lần trước khi kết luận hồi quy |
| Server GET jobs trả 405 | Process cũ chưa restart, không phải route source mới sai |
| Nhóm C tốt bất thường | Mini bão hòa, chờ G1 trainval |
