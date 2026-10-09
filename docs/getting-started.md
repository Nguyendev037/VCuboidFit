# Mở dự án VCuboidFIT — bắt đầu từ đây

Dự án có **3 phần**, chạy ở 3 chỗ khác nhau:

| Phần | Là gì | Có giao diện? | Chạy bằng |
|---|---|---|---|
| **Web** (`web/`) | Website Next.js: nạp dữ liệu, chỉnh tham số, xem kết quả | **Có** — <http://localhost:3000> | `npm run dev` (KHÔNG có image Docker cho web) |
| **Worker** (`model/worker/`) | API FastAPI chạy Tầng 0 (CPU), cổng 8001 | Không — chỉ trả JSON (`/health`) | Python venv **hoặc** Docker `vcuboidfit_worker:0.1` |
| **Tầng 1** (`model/docker/tier1/`) | PointPillars trên GPU, chạy xong thì thoát | Không — chạy theo lượt | Docker `vcuboidfit_pointpillars:0.1` |

> Docker **không có UI** là đúng thiết kế. Muốn thấy giao diện thì luôn mở web bằng `npm run dev`.
> Web cần worker đang chạy ở cổng 8001 và **cả hai dùng chung thư mục dữ liệu** `model/workspace`.

Mọi lệnh dưới đây chạy trong PowerShell, đứng ở **thư mục gốc repo** (thư mục có `README.md`).

## Cách 1 — Worker bằng Docker + Web bằng npm (khuyên dùng)

**Cửa sổ 1 — worker (Docker):**
```powershell
$env:WORKSPACE_DIR = "$PWD\model\workspace"
$env:VCF_PORT = "8001"
docker compose -f model\docker\worker\docker-compose.yml up -d --build worker
curl.exe http://127.0.0.1:8001/health        # đúng: {"ok":true,...}
```
Lần đầu build mất vài phút. Container tên `worker-worker-1`, cột Ports trong Docker Desktop phải là
`0.0.0.0:8001->8001/tcp`.

**Cửa sổ 2 — web:**
```powershell
cd web
if (-not (Test-Path .env.local)) { copy .env.example .env.local }   # chỉ lần đầu
npm ci                                                               # chỉ lần đầu / khi package-lock đổi
npm run dev                                                          # mở http://localhost:3000
```
`web/.env.local` phải có `WORKER_URL=http://127.0.0.1:8001` và `WORKSPACE=../model/workspace` (bản copy từ
`.env.example` đã đúng sẵn).

**Tắt:** Ctrl+C ở cửa sổ web; `docker compose -f model\docker\worker\docker-compose.yml down` cho worker.

## Cách 2 — Không dùng Docker (worker bằng Python)

```powershell
# lần đầu
python -m venv model\worker\.venv
model\worker\.venv\Scripts\pip install -e "model\worker[dev,service]"
# mỗi lần mở
$env:WORKSPACE = "$PWD\model\workspace"
cd model\worker
.venv\Scripts\python -m uvicorn service.main:create_app --factory --port 8001
```
Rồi mở cửa sổ khác chạy web như Cách 1 (cửa sổ 2). **Chỉ chạy MỘT worker**: đang chạy worker Docker thì đừng
bật thêm worker Python ở cổng 8001 (và ngược lại).

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
Để job LiDAR tự chạy Tầng 1, đặt `VCF_T1_EXP` trỏ tới thư mục thí nghiệm này rồi khởi động worker; không
cần chép file tay. Máy không có GPU: dùng Colab ([colab-dev-setup.md](colab-dev-setup.md)). Chi tiết thêm:
[run-local.md](run-local.md) mục 5.

## Kiểm nhanh khi "không thấy model"

| Triệu chứng | Nguyên nhân hay gặp | Sửa |
|---|---|---|
| Web báo không kết nối được worker / danh sách trống mãi | Worker chưa chạy, hoặc container chạy **không publish cổng** (bấm Run trong Docker Desktop mà không đặt port) | Dùng đúng lệnh `docker compose ... up -d worker` ở Cách 1; kiểm `curl.exe http://127.0.0.1:8001/health` |
| Container worker có trong Docker nhưng cột Ports chỉ là `8001/tcp` | Thiếu `-p 8001:8001` | Xoá container đó, chạy lại bằng compose |
| Worker chạy nhưng web không thấy dữ liệu đã nạp | Worker và web dùng **hai thư mục dữ liệu khác nhau** (volume ẩn danh, hoặc `WORKSPACE` khác) | Worker: `WORKSPACE_DIR=<repo>\model\workspace`; web: `WORKSPACE=../model/workspace` |
| `Method Not Allowed` khi xoá lần chạy | Worker đang chạy bản code cũ | Khởi động lại worker (Docker: thêm `--build`) |
| Hai thanh Tầng 1 bị khoá | Lần chạy chưa có `t1\signals.parquet` | Mục "Thêm Tầng 1" ở trên |
| Cổng 8001 đã bị chiếm | Đang có 2 worker (Python + Docker) | Tắt một bên |
