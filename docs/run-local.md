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

**Một biến cổng duy nhất: `VCF_PORT`** (mặc định 8001). Nó điều khiển cổng nghe của worker, cổng publish của
compose/tunnel và URL web dùng để gọi worker (`web/lib/server/worker.ts` suy `http://127.0.0.1:${VCF_PORT}` khi
không có `WORKER_URL`). Đổi cổng chỉ đổi biến này.

Các biến khác: worker `SEVENZIP_PATH` (mặc định `7z`), `C4_PROFILE` (`local-4060`/`cloud`), `C4_WEIGHTS_DIR`,
`C4_FAKE_MODELS`, và nhóm cầu nối Colab `VCF_REMOTE_TOKEN` / `VCF_REMOTE_LEASE_SEC` (5400 s) /
`VCF_REMOTE_MAX_RESULT_MB` (200); web `WORKER_URL` (mặc định `http://127.0.0.1:8001`), `MAX_UPLOAD_GB` (100),
`NEXT_PUBLIC_MOCK`. Mẫu: `model/worker/.env.example`, `web/.env.example` (worker không tự đọc `.env` - đặt trong shell).

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
$env:VCF_PORT = "8001"
.venv\Scripts\python -m uvicorn service.main:create_app --factory --port $env:VCF_PORT
# kiểm: curl "http://127.0.0.1:$env:VCF_PORT/health"
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

Image `vcuboidfit_pointpillars:0.1`, container `VCuboidFit_PointPillars`, compose
`model/docker/tier1/docker-compose.yml`. Cần Docker Desktop + WSL2 + driver NVIDIA. Cần `index.parquet`:
chạy bước 4 cho cùng thư mục `--out` trước.

```powershell
docker compose -f model\docker\tier1\docker-compose.yml build     # ~15 phút lần đầu, ~18.7 GB
docker compose -f model\docker\tier1\docker-compose.yml run --rm pointpillars   # selfcheck: phải in "REPRO OK"
model\scripts\tier1.ps1 -Data D:\nuscenes -Exp model\workspace\experiments\mini -Sweeps 10 -Epochs 20 -Batch 2
# rồi chạy lại bước 4: ma trận có thêm hybrid_mmr, t1_*_mmr, entropy_only
```
Dùng image khác (bản cũ, máy thuê, thử nghiệm): đặt `$env:VCF_TIER1_IMAGE = "<tên-image>"` — `tier1.ps1` và
mọi compose (`tier1`, `cloud`, `worker`) đều đọc biến này. Hết VRAM: `-Batch 1`, rồi `-Sweeps 1` (dùng cùng
số sweeps cho downstream). Image không dùng apt/git (mọi gói qua pip/HTTPS). Muốn web dùng Tầng 1: chép
`t1\signals.parquet` vào thư mục job.

## 5b. Worker Docker (không web)

Image `vcuboidfit_worker:0.1` = worker FastAPI Tầng 0 (CPU), không có web UI, không nướng sẵn dữ liệu Tầng 1.
```powershell
$env:VCF_PORT = "8001"
docker build -f model\docker\worker\Dockerfile -t vcuboidfit_worker:0.1 .
docker run -d --name vcuboidfit-worker -e VCF_PORT=$env:VCF_PORT -p "${env:VCF_PORT}:${env:VCF_PORT}" -v D:\ws:/data/workspace vcuboidfit_worker:0.1
# kiểm: curl "http://127.0.0.1:$env:VCF_PORT/health"
```
Hoặc compose (`tier1` ở profile `gpu`, dùng lại image `vcuboidfit_pointpillars:0.1`):
```powershell
$env:WORKSPACE_DIR = "D:\ws"      # cổng lấy từ VCF_PORT (mặc định 8001; compose còn nhận tên cũ WORKER_PORT)
docker compose -f model\docker\worker\docker-compose.yml up -d --build worker
$env:NUSC = "D:\nuscenes"; $env:EXP = "D:\exp"
docker compose -f model\docker\worker\docker-compose.yml --profile gpu run --rm tier1
```
Nếu chạy web local cạnh container: `WORKSPACE` của web phải trỏ **cùng thư mục** với phần mount
(`-v <thư mục>:/data/workspace`) và `WORKER_URL` (hoặc `VCF_PORT`) trỏ cổng đã publish.

## 5c. Tầng 1 qua Colab (máy yếu)

Máy không có GPU vẫn lấy được Tầng 1: Colab kéo việc từ worker qua tunnel, train rồi đẩy `signals.parquet` về.

Máy yếu (worker + tunnel):
```powershell
python -c "import secrets;print(secrets.token_urlsafe(32))"   # sinh token >= 32 ký tự
$env:VCF_REMOTE_TOKEN = "<dán token vừa sinh>"
$env:VCF_PORT = "8001"                                        # MỘT biến cổng cho worker, web, tunnel
# chạy worker như mục 1 (cửa sổ khác), rồi mở tunnel tạm:
cloudflared tunnel --url "http://127.0.0.1:$env:VCF_PORT"     # in ra https://<x>.trycloudflare.com
```
Colab: mở [`model/notebooks/run_on_colab.ipynb`](../model/notebooks/run_on_colab.ipynb), chạy phần 1–4 rồi phần 9 (chế độ agent)
(nhập URL tunnel + token bằng `getpass`) rồi ô 4. Agent chạy `model/scripts/colab_agent.py`: `GET /remote/t1/next`
(mỗi 60 s khi hàng đợi rỗng) → tải bundle → `train_seed` + `infer_t1` → `POST /remote/t1/{id}/result`.
Test không GPU: thêm `--dry-run` (ghi `signals.parquet` giả).
Giao thức: `next` trả `leaseId` của lượt nhận việc; `heartbeat`/`result`/`fail` phải gửi header `X-Lease-Id` = `leaseId` đó,
sai hoặc thiếu ⇒ `409 lease_mismatch`. POST `/remote/*` bắt buộc có `Content-Length`: thiếu hoặc chunked ⇒ `411 length_required`,
quá giới hạn (result > `VCF_REMOTE_MAX_RESULT_MB` + 1 MiB, heartbeat/fail > 64 KiB) ⇒ `413 too_large`.
Agent Colab và worker phải cùng phiên bản >= 0.6.1.
Worker đếm byte thực tế khi nhận: từng tệp tối đa `VCF_REMOTE_MAX_RESULT_MB`, toàn body tối đa mức đó + 1 MiB; tệp vượt ngưỡng bị chặn trước khi ghi thêm vào tệp tạm, kể cả khi khai sai Content-Length.

Web: ở panel tham số bấm **"Chạy Tầng 1 trên Colab"** (chỉ hiện khi worker đã bật `VCF_REMOTE_TOKEN` và job
chưa có Tầng 1). Khi task xong, panel tự mở khoá Tầng 1. Tắt cầu nối: dừng cloudflared + bỏ biến
`VCF_REMOTE_TOKEN` (mọi `/remote/*` trả 404).

Ghi chú: URL quick-tunnel của cloudflared là công khai — token là lớp bảo vệ duy nhất, chỉ dùng **tạm**.
Lease mặc định 5400 s (`VCF_REMOTE_LEASE_SEC`), kết quả tải lên tối đa 200 MB (`VCF_REMOTE_MAX_RESULT_MB`).

## 6. Lỗi hay gặp

| Hiện tượng | Cách xử |
|---|---|
| Web báo không thấy upload / job dù worker có | `WORKSPACE` web và worker khác nhau (mục 0) |
| Web gọi nhầm cổng worker | đổi **một** biến `VCF_PORT` cho cả worker, web và tunnel |
| `UnicodeEncodeError cp1252` | `$env:PYTHONIOENCODING="utf-8"` |
| `.ps1` báo lỗi cú pháp ở chữ có dấu | file phải có BOM UTF-8 (PowerShell 5.1) |
| `tier_unavailable` trên web | chưa có `t1/signals.parquet` cho job; chạy Tầng 1 rồi chép vào, hoặc dùng mục 5c |
| Nút "Chạy Tầng 1 trên Colab" không hiện | worker chưa đặt `VCF_REMOTE_TOKEN` (khi đó `/remote/*` trả 404 `remote_disabled`) |
| Agent Colab báo 401 | sai token — agent dừng ngay, không retry |
| `npm ci` lỗi mạng/peer | xoá `web/node_modules`, dùng đúng `package-lock.json` đã có |
| Upload `.7z` báo thiếu 7z | cài 7-Zip và đặt `SEVENZIP_PATH`, hoặc dùng `.zip` |
