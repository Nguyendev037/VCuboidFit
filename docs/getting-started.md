# Mở dự án VCuboidFIT — bắt đầu từ đây

Dự án có **3 phần**, chạy ở 3 chỗ khác nhau:

| Phần | Là gì | Có giao diện? | Chạy bằng |
|---|---|---|---|
| **Web** (`web/`) | Website Next.js: nạp dữ liệu, chỉnh tham số, xem kết quả | **Có** — <http://localhost:3000> | `npm run dev` (KHÔNG có image Docker cho web) |
| **Worker** (`model/worker/`) | API FastAPI chạy Tầng 0 (CPU), cổng 8001 | Không — chỉ trả JSON (`/health`) | `dev_up.ps1` (Tầng 0 + Tầng 1) **hoặc** Docker (chỉ Tầng 0) |
| **Tầng 1** (`model/docker/tier1/`) | PointPillars trên GPU, chạy xong thì thoát | Không — chạy theo lượt | Docker `vcuboidfit_pointpillars:0.1` |

> Docker **không có UI** là đúng thiết kế. Muốn thấy giao diện thì luôn mở web bằng `npm run dev`.
> Web cần worker đang chạy ở cổng 8001 và **cả hai dùng chung thư mục dữ liệu** `model/workspace`.

Mọi lệnh dưới đây chạy trong PowerShell, đứng ở **thư mục gốc repo** (thư mục có `README.md`).

## Cách 1 — Worker native bằng `dev_up.ps1` + Web bằng npm (khi cần Tầng 1)

**Cửa sổ 1 — worker native (Python):**
```powershell
# chỉ lần đầu
python -m venv model\worker\.venv
model\worker\.venv\Scripts\pip install -e "model\worker[dev,service]"
# mỗi lần mở, từ gốc repo
powershell -File model\scripts\dev_up.ps1 -Port 8001
```
Script đặt `WORKSPACE=<repo>\model\workspace`, tự chọn thư mục mới nhất trong
`model/workspace/experiments/` có đủ `index.parquet`, `t1/cfg/pp_seed.yaml` và
`t1/ckpt/seed_latest.pth`. Có thể chọn seed cụ thể bằng `-Exp <thư mục thí nghiệm>`.
Nếu không có seed, worker vẫn chạy Tầng 0. `VCF_REMOTE_TOKEN` đã đặt trong môi trường được giữ nguyên.
Tầng 1 cục bộ cần Docker + GPU NVIDIA và image PointPillars ở mục "Thêm Tầng 1".

Script in cổng, workspace và seed; cổng bận thì in tên tiến trình đang giữ cổng và thoát mã **3**,
không dừng tiến trình/container nào. **Chỉ MỘT phiên quản worker cổng 8001**; phiên khác dùng cổng khác
và workspace riêng, không khởi động thêm worker vào dữ liệu của phiên hiện tại.

**Cửa sổ 2 — web:**
```powershell
cd web
if (-not (Test-Path .env.local)) { copy .env.example .env.local }   # chỉ lần đầu
npm ci                                                               # chỉ lần đầu / khi package-lock đổi
npm run dev                                                          # mở http://localhost:3000
```
`web/.env.local` phải có `WORKER_URL=http://127.0.0.1:8001` và `WORKSPACE=../model/workspace` (bản copy từ
`.env.example` đã đúng sẵn).

## Cách 2 — Worker Docker (chỉ Tầng 0)

Worker trong container không chạy được Tầng 1 cục bộ; trạng thái Tầng 1 báo `skipped` kèm lý do nhắc Docker.
Nếu cần Tầng 1 trên máy này, dùng worker native ở Cách 1.

```powershell
$env:WORKSPACE_DIR = "$PWD\model\workspace"
$env:VCF_PORT = "8001"
docker compose -f model\docker\worker\docker-compose.yml up -d --build worker
curl.exe http://127.0.0.1:8001/health        # đúng: {"ok":true,...}
```
Lần đầu build mất vài phút. Container tên `worker-worker-1`, cột Ports trong Docker Desktop phải là
`0.0.0.0:8001->8001/tcp`. Mở web như Cách 1 (cửa sổ 2). Không bật Docker worker khi cổng 8001 đang có worker.

## Dùng giao diện

1. Mở <http://localhost:3000>.
2. **Bước 1**: chọn **tất cả** file trong `dataset/01_small_3scenes/` (các `vcf_part_*.zip` + `vcf_manifest.json`),
   chờ tải lên.
3. Bấm chạy phân tích. Xong sẽ có danh sách 5 % frame được chọn, mở **Deep Review** / **Frame Viewer** để xem.
4. Lần chạy cũ nằm ở mục **Lần chạy gần đây** (xoá được từng lần hoặc tất cả).

Chưa có dữ liệu thật mà muốn xem giao diện ngay: trong `web/` chạy `$env:NEXT_PUBLIC_MOCK="1"; npm run dev`
(không cần worker).

## Thêm Tầng 1 (model AI, cần GPU NVIDIA)

Không có Tầng 1 thì web chỉ dùng tiêu chí "Hiếm trong dữ liệu"; hai thanh "Lạ với model" và "Model chưa chắc
chắn" bị khoá — đó là bình thường. Cách có Tầng 1:

```powershell
docker compose -f model\docker\tier1\docker-compose.yml run --rm pointpillars   # kiểm GPU: phải in "REPRO OK"
$env:NUSC = "H:\"                                                                # thư mục gốc nuScenes (có v1.0-mini\)
$env:EXP  = "$PWD\model\workspace\experiments\mini"                              # đã chạy Tầng 0 (có index.parquet)
docker compose -f model\docker\tier1\docker-compose.yml run --rm tier1           # train + infer -> $EXP\t1\signals.parquet
```
Để job LiDAR tự chạy Tầng 1, khởi động worker native bằng `dev_up.ps1` (tự tìm seed) hoặc truyền
`-Exp <thư mục thí nghiệm>`; không chép `signals.parquet` vào job bằng tay. Máy không có GPU: dùng Colab ([colab-dev-setup.md](colab-dev-setup.md)). Chi tiết thêm:
[run-local.md](run-local.md) mục 5.

## Kiểm nhanh khi "không thấy model"

| Triệu chứng | Nguyên nhân hay gặp | Sửa |
|---|---|---|
| Web báo không kết nối được worker / danh sách trống mãi | Worker chưa chạy, hoặc container chạy **không publish cổng** (bấm Run trong Docker Desktop mà không đặt port) | Dùng `dev_up.ps1` ở Cách 1 hoặc Docker ở Cách 2; kiểm `curl.exe http://127.0.0.1:8001/health` |
| Container worker có trong Docker nhưng cột Ports chỉ là `8001/tcp` | Thiếu `-p 8001:8001` | Xoá container đó, chạy lại bằng compose |
| Worker chạy nhưng web không thấy dữ liệu đã nạp | Worker và web dùng **hai thư mục dữ liệu khác nhau** (volume ẩn danh, hoặc `WORKSPACE` khác) | Worker native: script đặt `WORKSPACE`; Docker: `WORKSPACE_DIR=<repo>\model\workspace`; web: `WORKSPACE=../model/workspace` |
| `Method Not Allowed` khi xoá lần chạy | Worker đang chạy bản code cũ | Khởi động lại worker (Docker: thêm `--build`) |
| Hai thanh Tầng 1 khoá + lý do nhắc Docker | Worker đang chạy trong container | Dùng `dev_up.ps1` ở Cách 1 |
| Hai thanh Tầng 1 bị khoá | Lần chạy chưa có `t1\signals.parquet` | Mục "Thêm Tầng 1" ở trên |
| Cổng 8001 đã bị chiếm | Đã có tiến trình nghe cổng | `dev_up.ps1` in tên tiến trình và thoát 3; dùng worker hiện tại, không tự dừng worker của phiên khác |
