# Chạy local - Windows, CPU và Docker GPU

Mọi lệnh chạy từ **thư mục gốc repo** (`VCuboidFit/`) trừ khi ghi `cd`. PowerShell. Yêu cầu: Python 3.11+
(đã thử 3.12), Node 20+ (đã thử 26), Git. Tuỳ chọn: 7-Zip (chỉ cần cho .7z/.rar), Docker Desktop + WSL2 + NVIDIA (Tầng 1).

## 0. Hai thư mục phải khớp: WORKSPACE

Web và worker trao đổi qua một thư mục `WORKSPACE` (`uploads/`, `datasets/`, `jobs/`). Mặc định của hai bên
**khác nhau** trong cấu trúc này, nên luôn đặt biến tường minh:

| Bên | Biến | Mặc định trong code | Nên đặt |
|---|---|---|---|
| worker (`model/worker/service/settings.py`) | `WORKSPACE` | `../workspace` tính từ thư mục chạy | chạy trong `model/worker` => `model/workspace` |
| job runner (`c4/jobs/runner.py`) | (ghi cạnh `parents[3]`) | `model/workspace` | cùng chỗ trên |
| web (`web/lib/server/workspace.ts`) | `WORKSPACE` | `<repo>/workspace` (cạnh `web/`) | `../model/workspace` (file `web/.env.example`) |

Các biến khác: worker `SEVENZIP_PATH` (mặc định `7z`), `C4_PROFILE` (`local-4060`/`cloud`), `C4_WEIGHTS_DIR`,
`C4_FAKE_MODELS`; web `WORKER_URL` (mặc định `http://127.0.0.1:8001`), `MAX_UPLOAD_GB` (100), `NEXT_PUBLIC_MOCK`.
Mẫu: `model/worker/.env.example`, `web/.env.example` (worker không tự đọc `.env` - đặt trong shell).

## 1. Worker (Python) - Tầng 0 trên CPU

```powershell
python -m venv model\worker\.venv
model\worker\.venv\Scripts\pip install -e "model\worker[dev,service]"
```
Kiểm cài đặt:
```powershell
cd model\worker
.venv\Scripts\python -m pytest -q -m "not perf and not gpu" tests/lidar tests/service/test_lidar.py tests/service/test_models.py
```
Chạy service (giữ cửa sổ này mở):
```powershell
cd model\worker
$env:WORKSPACE = (Resolve-Path ..).Path + "\workspace"     # = model\workspace
.venv\Scripts\python -m uvicorn service.main:create_app --factory --port 8001
# kiểm: curl http://127.0.0.1:8001/health
```
Không cài `.[gpu]` nếu chỉ chạy đường LiDAR Tầng 0 (không cần torch).

## 2. Web (Next.js)

```powershell
cd web
copy .env.example .env.local        # WORKER_URL=http://127.0.0.1:8001, WORKSPACE=../model/workspace
npm ci
npm run dev                         # http://localhost:3000
```
Kiểm: `npx tsc --noEmit` và `npx vitest run`. Chạy không cần worker (dữ liệu mẫu):
`$env:NEXT_PUBLIC_MOCK="1"; npm run dev`.

## 3. Upload một bộ zip

1. Chuẩn bị `dataset/01_small_3scenes/` (xem [dataset/README.md](../dataset/README.md)).
2. Mở <http://localhost:3000>, Bước 1: chọn **tất cả** `vcf_part_*.zip` + `vcf_manifest.json` của một thư mục.
3. Upload chạy từng chunk 50 MB, có kiểm SHA-256 và tiếp tục được khi đứt. Xong web hiển thị báo cáo dataset
   (số scene/frame). Bấm chạy: worker chạy stage `lidar_index` rồi `t0`; xem kết quả ở màn "Chọn 5 %".
4. Không cần web: chép thư mục part vào `model\workspace\uploads\<tên-bất-kỳ>\` rồi gọi API worker.

## 4. Thí nghiệm bằng CLI (tune k, lambda, m + bootstrap + ablation)

```powershell
cd model\worker
.venv\Scripts\python -m c4.cli.lidar_experiment --data-root D:\nuscenes --out ..\workspace\experiments\mini --split V --tune --bootstrap 200
# kết quả: model\workspace\experiments\mini\V\report_selection.md, metrics.json, <run>\selected_5pct.csv
```
`--data-root` là thư mục chứa `v1.0-mini/ samples/ sweeps/`. Đo trên mini (404 frame, 32 lõi): descriptor
~20 ms/frame; chọn + chấm ~4 s.

## 5. Tầng 1 trong Docker (RTX 4060 8 GB)

Cần Docker Desktop + WSL2 + driver NVIDIA. Cần `index.parquet`: chạy bước 4 cho cùng thư mục `--out` trước.
```powershell
docker build -t vcf-tier1:0.1 model\docker\tier1          # ~15 phút lần đầu, ~18.7 GB
model\scripts\tier1.ps1 -Data D:\nuscenes -Exp model\workspace\experiments\mini -Sweeps 10 -Epochs 20 -Batch 2
# rồi chạy lại bước 4: ma trận có thêm hybrid_mmr, t1_*_mmr, entropy_only
```
Hết VRAM: `-Batch 1`, rồi `-Sweeps 1` (dùng cùng số sweeps cho downstream). Image không dùng apt/git
(mọi gói qua pip/HTTPS). Muốn web dùng Tầng 1: chép `t1\signals.parquet` vào thư mục job.

## 6. Lỗi hay gặp

| Hiện tượng | Cách xử |
|---|---|
| Web báo không thấy upload / job dù worker có | `WORKSPACE` web và worker khác nhau (mục 0) |
| `UnicodeEncodeError cp1252` | `$env:PYTHONIOENCODING="utf-8"` |
| `.ps1` báo lỗi cú pháp ở chữ có dấu | file phải có BOM UTF-8 (PowerShell 5.1) |
| `tier_unavailable` trên web | chưa có `t1/signals.parquet` cho job; chạy Tầng 1 rồi chép vào |
| `npm ci` lỗi mạng/peer | xoá `web/node_modules`, dùng đúng `package-lock.json` đã có |
| Upload `.7z` báo thiếu 7z | cài 7-Zip và đặt `SEVENZIP_PATH`, hoặc dùng `.zip` |
