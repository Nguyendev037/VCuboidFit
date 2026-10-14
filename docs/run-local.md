# Chạy local - Windows, CPU và Docker GPU

Mọi lệnh chạy từ **thư mục gốc repo** (`VCuboidFit/`) trừ khi ghi `cd`. PowerShell. Yêu cầu: Python 3.11+
(đã thử 3.12), Node 20+ (đã thử 26), Git + **Git LFS** (`git lfs install` trước `git clone`). Tuỳ chọn: 7-Zip (chỉ cần cho .7z/.rar),
Docker Desktop + WSL2 + NVIDIA (Tầng 1), GPU CUDA + `.[gpu]` (engine `rare_v24` profile `multisensor`).
Mới clone repo? Đọc [getting-started.md](getting-started.md) mục 0 (clone, cái gì có/không có sau clone, dữ liệu, Linux/macOS)
trước; file này là tham chiếu chi tiết từng lệnh. Dữ liệu nuScenes: [../dataset/README.md](../dataset/README.md).

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

Các biến khác: worker `SEVENZIP_PATH` (mặc định `7z`), `C4_PROFILE` (`local-4060`/`cloud`), `C4_WEIGHTS_DIR`
(mặc định `model/workspace/weights`), `C4_FAKE_MODELS`, `VCF_ENGINE_DEFAULT` (`c4_legacy` mặc định | `rare_v24`), và nhóm cầu nối Colab `VCF_REMOTE_TOKEN` / `VCF_REMOTE_LEASE_SEC` (5400 s) /
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
Không cài `.[gpu]` nếu chỉ chạy đường LiDAR Tầng 0 hoặc `rare_v24` profile `lidar_only` (không cần torch). Engine `rare_v24`
profile `multisensor` (OpenCLIP, YOLO, OpenCV): cài torch CUDA từ `https://download.pytorch.org/whl/cu124`, rồi
`pip install -e "model\worker[dev,service,gpu]"` và `model/scripts/fetch_weights.py` — từng bước ở
[getting-started.md](getting-started.md) mục "Bật engine rare_v24 / OpenCLIP (GPU)". Máy vừa clone chưa có seed Tầng 1 cục bộ
(`index.parquet`, `t1/cfg/pp_seed.yaml`, `t1/ckpt/seed_latest.pth`) nên worker chạy Tầng 0; xem mục 5 để có seed.

## 2. Web (Next.js)

```powershell
cd web
copy .env.example .env.local        # WORKER_URL=http://127.0.0.1:8001, WORKSPACE=../model/workspace
npm ci
npm run dev                         # http://localhost:3000
```
Kiểm: `node node_modules/typescript/bin/tsc --noEmit` và `node node_modules/vitest/vitest.mjs run` (đủ bộ lệnh kiểm thử + e2e:
[getting-started.md](getting-started.md) mục "Chạy kiểm thử"). Chạy không cần worker (dữ liệu mẫu):
`$env:NEXT_PUBLIC_MOCK="1"; node node_modules/next/dist/bin/next dev`.

## 2b. Chạy demo local (Demo UI 15 phút — OPERATIONS §3)

Thực hiện theo `OPERATIONS.md` §3 và §6 cho buổi trình chiếu demo:

### 1. Khởi động Worker và Web
Worker và Web phải có `WORKSPACE` khớp nhau và chung biến `VCF_PORT`:
```powershell
# Cửa sổ 1: Worker (Python)
cd model\worker
$env:WORKSPACE = (Resolve-Path ..).Path + "\workspace"     # = model\workspace
$env:VCF_PORT = "8001"
.venv\Scripts\python -m uvicorn service.main:create_app --factory --port $env:VCF_PORT
# Kiểm tra sức khoẻ worker trước demo:
curl.exe "http://127.0.0.1:8001/health"                    # phải trả {"ok":true,...}

# Cửa sổ 2: Web (Next.js - dùng node trực tiếp vì lỗi NVM4306 của npm)
cd web
$env:WORKSPACE = (Resolve-Path ..\model\workspace).Path   # biến môi trường KHÔNG đi theo từ cửa sổ 1
$env:VCF_PORT = "8001"
$env:PORT = "3000"
node node_modules/next/dist/bin/next dev
```
Truy cập giao diện tại:
- Chế độ trình chiếu (khuyên dùng khi pitch): <http://localhost:3000/?present=1> (phóng to cỡ chữ 18px, ẩn bớt chi tiết rườm rà).
- Màn hình duyệt bối cảnh: <http://localhost:3000/review/context>.
- Bảng điều khiển phân tích: <http://localhost:3000/dashboard>.

### 2. Đăng ký Job sẵn có bằng `job.json`
> Chỉ dành cho máy chủ dự án: các job `m2_mini`, `night_v24`, `pool_v24` **không có trong repo** (`model/workspace/` bị gitignore). Người mới clone
> tự tạo job bằng upload dữ liệu trên web hoặc CLI ([getting-started.md](getting-started.md) mục "Dữ liệu nuScenes"); bỏ qua tiểu mục 2 và 3 của phần 2b này.

Để giao diện web và API worker nhận diện được các job đã chạy trước (tránh lỗi 404/500 khi mở hoặc xuất ảnh), tạo tệp `job.json` và `status.json` trong thư mục job tương ứng (`model/workspace/jobs/<job_id>/`):

Ví dụ với job `m2_mini` (`model/workspace/jobs/m2_mini/job.json`):
```json
{
  "jobId": "m2_mini",
  "datasetId": "d98cf3321dff",
  "pipeline": "lidar",
  "createdAt": "2026-10-13T14:29:23",
  "state": "done"
}
```
Và `model/workspace/jobs/m2_mini/status.json`:
```json
{
  "state": "done",
  "stage": "done",
  "progress": 1.0,
  "done": 404,
  "total": 404
}
```

Tương tự cho job `night_v24` (`model/workspace/jobs/night_v24/job.json`):
```json
{
  "jobId": "night_v24",
  "datasetId": "nuscenes_trainval",
  "pipeline": "lidar",
  "createdAt": "2026-10-13T22:57:24",
  "state": "done"
}
```

### 3. Liên kết dữ liệu ảnh tạm qua Junction (OPERATIONS §6)
Màn duyệt bối cảnh của job `night_v24` yêu cầu ảnh camera nuScenes trainval. Tạo junction trỏ từ workspace dataset tới thư mục dữ liệu thật trên ổ `E:\`:
```powershell
New-Item -ItemType Junction -Path model\workspace\datasets\nuscenes_trainval\data -Target E:\nuscenes_trainval
```
> **Lưu ý dọn dẹp:** Khi hoàn tất demo hoặc trước khi xoá ổ `E:`, chỉ gỡ liên kết junction (không làm mất dữ liệu gốc trên `E:`):
> ```powershell
> Remove-Item model\workspace\datasets\nuscenes_trainval\data -Force
> ```

## 3. Upload một bộ zip

1. Chuẩn bị bộ part zip (repo không kèm zip; tự đóng gói bằng `tools/vcf-pack`, xem [dataset/README.md](../dataset/README.md)).
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
docker compose -f model\docker\tier1\docker-compose.yml build     # ~15 phút lần đầu, ~18.9 GB
docker compose -f model\docker\tier1\docker-compose.yml run --rm pointpillars   # selfcheck: phải in "REPRO OK"
model\scripts\tier1.ps1 -Data D:\nuscenes -Exp model\workspace\experiments\mini -Sweeps 10 -Epochs 20 -Batch 2
# rồi chạy lại bước 4: ma trận có thêm hybrid_mmr, t1_*_mmr, entropy_only
```
Hoặc chỉ dùng compose (project `vcuboidfit-tier1`; service `train`, `infer`, `tier1` = train + infer):
```powershell
$env:NUSC = "D:\nuscenes"; $env:EXP = "$PWD\model\workspace\experiments\mini"
$env:EPOCHS = "20"; $env:SWEEPS = "10"; $env:BATCH = "2"          # mặc định; hết VRAM: BATCH=1 rồi SWEEPS=1
docker compose -f model\docker\tier1\docker-compose.yml run --rm tier1   # -> <EXP>\t1\signals.parquet
```
Dùng image khác (bản cũ, máy thuê, thử nghiệm): đặt `$env:VCF_TIER1_IMAGE = "<tên-image>"` — `tier1.ps1` và
mọi compose (`tier1`, `cloud`, `worker`) đều đọc biến này. Hết VRAM: `-Batch 1`, rồi `-Sweeps 1` (dùng cùng
số sweeps cho downstream). Image không dùng apt/git (mọi gói qua pip/HTTPS). Muốn job LiDAR tự chạy Tầng 1: đặt `$env:VCF_T1_EXP` = đường dẫn tuyệt đối tới thư mục thí nghiệm đã train
(chứa `index.parquet`, `t1/cfg/pp_seed.yaml`, `t1/ckpt/seed_latest.pth`), rồi khởi động worker. Job LiDAR tự chạy
stage `t1` sau `t0` và ghi `t1/signals.parquet` vào job. Không đặt `VCF_T1_EXP` ⇒ job chỉ có Tầng 0.

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
Colab: mở [`model/notebooks/vcf_colab_agent.ipynb`](../model/notebooks/vcf_colab_agent.ipynb), chạy ô 1-3
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
| `tier_unavailable` trên web | chưa có `t1/signals.parquet` cho job; đặt `VCF_T1_EXP` (mục 5) rồi chạy job, hoặc dùng mục 5c |
| Nút "Chạy Tầng 1 trên Colab" không hiện | worker chưa đặt `VCF_REMOTE_TOKEN` (khi đó `/remote/*` trả 404 `remote_disabled`) |
| Agent Colab báo 401 | sai token — agent dừng ngay, không retry |
| `npm ci` lỗi mạng/peer | xoá `web/node_modules`, dùng đúng `package-lock.json` đã có |
| `npm`/`npx` báo `NVM4306` | gọi node trực tiếp: `node node_modules/next/dist/bin/next dev` |
| `*.pth` chỉ vài trăm byte | clone khi chưa cài Git LFS: `git lfs install ; git lfs pull` |
| Thiếu trọng số YOLO/DINO/OpenCLIP | `python model/scripts/fetch_weights.py --dir model/workspace/weights` ([getting-started.md](getting-started.md)) |
| Chạy e2e xong worker biến mất | spec `demo-flow` A6 cố ý dừng worker: chạy lại worker |
| Upload `.7z` báo thiếu 7z | cài 7-Zip và đặt `SEVENZIP_PATH`, hoặc dùng `.zip` |
