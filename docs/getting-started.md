# Mở dự án VCuboidFIT — bắt đầu từ đây

## 0. Yêu cầu & clone

| Thành phần | Bản | Dùng cho |
|---|---|---|
| Git + **Git LFS** | Git LFS 3.x | clone checkpoint PointPillars (`*.pth` theo `.gitattributes`) |
| Python | 3.11+ (đã chạy 3.12) | worker + engine `c4` |
| Node.js | 20+ (đã chạy 26) | web |
| 7-Zip | tuỳ chọn | chỉ khi upload `.7z`/`.rar` (`SEVENZIP_PATH`); `.zip` không cần |
| Docker Desktop + WSL2 + GPU NVIDIA | tuỳ chọn | Tầng 1 cục bộ (image `vcuboidfit_pointpillars:0.1`, ~18.9 GB, build ~15 phút; xem [run-local.md](run-local.md) mục 5) |
| GPU CUDA + PyTorch | tuỳ chọn | engine `rare_v24` profile `multisensor` (mục "Bật engine rare_v24 / OpenCLIP" bên dưới) |

```powershell
git lfs install                       # MỘT lần mỗi máy, trước khi clone
git clone https://github.com/Nguyendev037/VCuboidFit.git
cd VCuboidFit
git lfs ls-files                      # phải thấy checkpoint_epoch_80.pth (dấu "*" sau mã = đã tải, "-" = mới là con trỏ)
```
Đã clone mà quên LFS: `git lfs install ; git lfs pull`. Không có LFS thì `*.pth` chỉ là file text con trỏ (vài trăm byte);
web, worker và Tầng 0 vẫn chạy, chỉ riêng checkpoint là không dùng được.

**Sau clone bạn có và không có:**

| Có | Không có (tự chuẩn bị) |
|---|---|
| Toàn bộ code, test, docs, `web/public/demo/bench_pitch.json` + 3 PNG (trang chủ, `/vi-sao`) | Dữ liệu nuScenes và các `vcf_part_*.zip` (xem mục "Dữ liệu nuScenes" bên dưới) |
| `dataset/01_small_3scenes/vcf_manifest.json` (chỉ manifest) | Job demo `m2_mini`, `night_v24`, `pool_v24`... (`model/workspace/` bị gitignore; không phải lỗi) |
| 1 checkpoint 80 epoch: `model/workspace/experiments/mini-e80/t1/pcdet_output/exp/t1/cfg/pp_seed/seed_c6b39360/ckpt/checkpoint_epoch_80.pth` (LFS, ~70 MB) | Seed Tầng 1 đúng bố cục mà `dev_up.ps1` và `c4.cli.lidar_t1` đòi: `index.parquet`, `t1/cfg/pp_seed.yaml`, `t1/ckpt/seed_latest.pth`. Thí nghiệm `mini-e80` chỉ có checkpoint trên nên `dev_up.ps1` KHÔNG chọn nó và worker chạy Tầng 0. Checkpoint này là trọng số mặc định cho Colab (`model/scripts/colab_agent.py` tải từ GitHub) |
| | Trọng số YOLO11 / DINOv2 / OpenCLIP (`model/workspace/weights/`; tải bằng `fetch_weights.py`) |

**Linux/macOS:** thay `.venv\Scripts\python` bằng `.venv/bin/python`, `copy` bằng `cp`, `$env:X = "v"` bằng `export X=v`,
dấu `\` trong đường dẫn bằng `/`. `dev_up.ps1` chỉ có cho PowerShell: trên Linux/macOS đặt `WORKSPACE`, `VCF_PORT`
(và tuỳ chọn `VCF_T1_EXP`) bằng `export` rồi chạy `python -m uvicorn service.main:create_app --factory --port 8001` trong `model/worker`.

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
Nếu không có seed (bản vừa clone chưa có), worker vẫn chạy Tầng 0. `VCF_REMOTE_TOKEN` đã đặt trong môi trường được giữ nguyên.
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

## Dữ liệu nuScenes (repo không kèm)

Repo chỉ giữ `dataset/01_small_3scenes/vcf_manifest.json`; các `vcf_part_*.zip` bị gitignore và manifest đó chỉ khớp
SHA-256 của zip gốc của chủ dự án. Bạn tự tạo bộ part từ nuScenes-mini (cần tài khoản nuscenes.org miễn phí, dữ liệu phi thương mại):

1. Tải **v1.0-mini** (~4 GB) tại <https://www.nuscenes.org/nuscenes#download>, giải nén (`tar -xzf v1.0-mini.tgz -C D:\nuscenes`)
   thành `D:\nuscenes\v1.0-mini\`, `samples\`, `sweeps\`, `maps\`.
2. Đóng gói part (<= 50 MB mỗi part + `vcf_manifest.json`) bằng `tools/vcf-pack`:
```powershell
model\worker\.venv\Scripts\pip install -e tools\vcf-pack
model\worker\.venv\Scripts\python -m vcf_pack D:\nuscenes --out dataset\mini --scenes 3 --include-sweeps
```
   Lệnh in số part/scene/frame. **KHÔNG** đặt `--out dataset\01_small_3scenes` (sẽ ghi đè manifest đang được git theo dõi).
   Bỏ `--scenes 3` để đóng cả 10 scene. Cờ khác: `--part-size`, `--version`, `--include-maps` (xem `python -m vcf_pack --help`).
3. Upload ở Bước 1: chọn TẤT CẢ file trong thư mục `dataset\mini`. Chi tiết: [dataset/README.md](../dataset/README.md).

Chạy bằng CLI không cần web: `--data-root D:\nuscenes` (thư mục chứa `v1.0-mini/`), xem [run-local.md](run-local.md) mục 4.

Trang chạy được ngay sau clone (không dữ liệu): `/`, `/vi-sao`, `/huong-dan` (đọc `web/public/demo/`). Các trang còn lại
cần dữ liệu + worker, hoặc `NEXT_PUBLIC_MOCK=1` để xem giao diện với dữ liệu mẫu.

## Dùng giao diện

1. Mở <http://localhost:3000>.
2. **Bước 1**: chọn **tất cả** file của bộ dữ liệu bạn đã đóng gói (các `vcf_part_*.zip` + `vcf_manifest.json`),
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

## Bật engine rare_v24 / OpenCLIP (GPU)

Service có hai engine: `c4_legacy` (mặc định) và `rare_v24`. Chọn trên web: dashboard → **Chi tiết kỹ thuật** → ô
**Engine** (`C4 hiện tại` / `Rare v2.4`) và ô **Profile** (`Chỉ LiDAR` / `LiDAR + camera`). Chọn qua API: `POST /jobs/{id}/select`
với `engineVersion` (`c4_legacy` | `rare_v24`) và `profile` (`lidar_only` | `multisensor`); thiếu `engineVersion` thì dùng biến
`VCF_ENGINE_DEFAULT` (mặc định `c4_legacy`). Id lạ trả 422 `UNKNOWN_ENGINE`.

* **`lidar_only`**: chạy CPU, không cần cài thêm ngoài `[dev,service]`.
* **`multisensor`** (OpenCLIP ViT-B-16 `openai` + YOLO11 + OpenCV): cần GPU CUDA và extra `[gpu]` (~2 GB). Cài PyTorch bản CUDA TRƯỚC:

```powershell
model\worker\.venv\Scripts\pip install torch torchvision --index-url https://download.pytorch.org/whl/cu124
model\worker\.venv\Scripts\pip install -e "model\worker[dev,service,gpu]"
cd model\worker
$env:PYTHONIOENCODING = "utf-8"
.venv\Scripts\python ..\scripts\fetch_weights.py --dir ..\workspace\weights    # YOLO11 m/s, DINOv2, OpenCLIP; cần mạng, một lần
```
Trọng số OpenCLIP nằm ở `<C4_WEIGHTS_DIR>/open_clip` (mặc định `model/workspace/weights/open_clip`; đổi chỗ bằng `C4_WEIGHTS_DIR`).
Khi chạy job, code đặt `HF_HUB_OFFLINE=1` (không dùng mạng) nên PHẢI tải trước bằng `fetch_weights.py`; thiếu thì lệnh
thoát mã 4 kèm gợi ý chạy `fetch_weights.py`. Cache OpenCLIP đi theo `C4_WEIGHTS_DIR`, không theo `HF_HOME`. Chạy thử không cần
trọng số/GPU: `C4_FAKE_MODELS=1` (embedding giả, chỉ để test).

Chuỗi lệnh từ dữ liệu đến `multisensor` (index, Tầng 0, `rare run`, `extract_clip`, `context cv/fit/run`, `rare crops`):
[model-workflow.md](model-workflow.md) mục 10; cờ từng lệnh: `python -m c4.cli.rare run --help`. `multisensor` cần
`context_frame` và cache `crops` tạo trước; chưa có thì chọn `lidar_only`.

## Chạy kiểm thử (cho người đóng góp)

Số đo 2026-10-14 (đều xanh): worker 383 pass / 5 skip, web vitest 221, e2e 9.

```powershell
# worker
cd model\worker
.venv\Scripts\python -m pytest -q
# web
cd ..\..\web
node node_modules/typescript/bin/tsc --noEmit
node node_modules/eslint/bin/eslint.js .
node node_modules/vitest/vitest.mjs run
# e2e: cần worker :8001 và web :3000 đang chạy, cùng WORKSPACE
node node_modules/playwright/cli.js install chromium        # một lần
node node_modules/@playwright/test/cli.js test
```
Gọi `node ...` trực tiếp thay `npm`/`npx` để tránh lỗi NVM4306 (xem bảng cuối trang). Spec e2e `demo-flow` (A6) cố ý dừng worker:
chạy xong phải khởi động lại worker. Test GPU tự skip nếu thiếu CUDA/trọng số.

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
| `npm`/`npx` báo lỗi `NVM4306` (Windows, nvm-windows) | nvm chặn lệnh khi chưa chọn bản Node | Gọi node trực tiếp: `node node_modules/next/dist/bin/next dev` (cần `node_modules` đã có) |
| `UnicodeEncodeError: 'charmap'/cp1252` khi in tiếng Việt | Console Windows không phải UTF-8 | `$env:PYTHONIOENCODING = "utf-8"` trước khi chạy Python |
| Web mở được nhưng danh sách trống dù worker chạy | `WORKSPACE` hoặc `VCF_PORT` của web khác worker (biến môi trường không đi theo giữa các cửa sổ) | Đặt lại cả hai biến ở MỖI cửa sổ hoặc trong `web/.env.local`; mặc định worker `model/workspace`, web `<repo>/workspace` |
| `git lfs ls-files` có dấu `-` hoặc file `.pth` chỉ vài trăm byte | Clone khi chưa cài Git LFS | `git lfs install ; git lfs pull` |
| `thiếu trọng số ... chạy: python scripts/fetch_weights.py` | Chưa tải YOLO/DINO/OpenCLIP | `python model/scripts/fetch_weights.py --dir model/workspace/weights` (mục "Bật engine rare_v24") |
| `ModuleNotFoundError: torch` / `open_clip` | Chưa cài extra `[gpu]` (hoặc torch bản CPU) | Cài torch CUDA từ `download.pytorch.org/whl/cu124` trước, rồi `pip install -e "model\worker[dev,service,gpu]"` |
| Worker chết sau khi chạy e2e | Spec `demo-flow` A6 cố ý dừng worker | Chạy lại worker |
| `/dashboard`, `/review` không có job nào | Repo không kèm job demo | Tự upload dữ liệu và chạy job (mục "Dữ liệu nuScenes") |
| Muốn Tầng 1 cục bộ nhưng `dev_up.ps1` in `seed: không có` | Bản clone không có `index.parquet`/`pp_seed.yaml`/`seed_latest.pth` | Train seed bằng Docker (mục "Thêm Tầng 1") hoặc dùng Colab |
