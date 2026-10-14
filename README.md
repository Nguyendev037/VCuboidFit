# VCuboidFIT

Chọn **5 % keyframe LiDAR đáng gán nhãn 3D nhất** từ một bộ dữ liệu nuScenes — chỉ dùng point cloud,
ego pose và timestamp (không camera, không nhãn). Có engine Python (CPU, thêm tầng PointPillars
tuỳ chọn trên GPU) và website Next.js để nạp dữ liệu, chỉnh tham số, xem kết quả, soi từng frame.

> **Repo này là ROOT duy nhất của dự án** (phiên bản v0.6.6). Mọi thay đổi
> code, tài liệu, Docker, notebook đều làm, commit và push thẳng tại đây — không sinh lại từ nơi khác.

## Bắt đầu nhanh sau khi clone

Yêu cầu: **Python 3.11+** (đã chạy 3.12), **Node 20+** (đã chạy 26), **Git** + **Git LFS**. Tuỳ chọn: 7-Zip (chỉ cho `.7z`/`.rar`),
Docker Desktop + WSL2 + GPU NVIDIA (Tầng 1 cục bộ), GPU CUDA (engine `rare_v24` profile `multisensor`).
Hướng dẫn viết cho Windows/PowerShell; Linux/macOS xem ghi chú trong [docs/getting-started.md](docs/getting-started.md) mục 0.

```powershell
git lfs install                                   # một lần cho mỗi máy, TRƯỚC khi clone
git clone https://github.com/Nguyendev037/VCuboidFit.git ; cd VCuboidFit
# (đã clone mà quên LFS: git lfs install ; git lfs pull)

python -m venv model\worker\.venv                                          # 1) engine + worker
model\worker\.venv\Scripts\pip install -e "model\worker[dev,service]"
cd web ; copy .env.example .env.local ; npm ci ; cd ..                      # 2) web
```
```powershell
# Cửa sổ A: worker (cổng 8001)
$env:WORKSPACE = "$PWD\model\workspace"; $env:VCF_PORT = "8001"; $env:PYTHONIOENCODING = "utf-8"
cd model\worker ; .venv\Scripts\python -m uvicorn service.main:create_app --factory --port 8001
```
```powershell
# Cửa sổ B: web, từ thư mục gốc repo -> http://localhost:3000
cd web ; npm run dev          # npm/npx bị chặn (NVM4306): node node_modules/next/dist/bin/next dev
```

Chi tiết, bảng lỗi và dữ liệu: [docs/getting-started.md](docs/getting-started.md).

**Sau clone bạn có gì, chưa có gì:**

| Mục | Sau clone |
|---|---|
| Trang chủ `/`, `/vi-sao`, `/huong-dan` | Phần giới thiệu chạy không cần worker; phương pháp và benchmark T ở `/vi-sao`. Mô phỏng mẫu cần dựng `web/public/mock-media/` (không commit), xem [docs/web.md](docs/web.md) |
| Giao diện với dữ liệu mẫu | `NEXT_PUBLIC_MOCK=1` (không cần worker), dữ liệu ở `web/mocks/` |
| `/dashboard`, `/review/**`, Frame Viewer thật | Cần worker + **dữ liệu nuScenes tự chuẩn bị** (repo không chứa; xem [dataset/README.md](dataset/README.md)) |
| Job demo (`m2_mini`, `night_v24`, `pool_v24`...) | **Không có** trong repo (`model/workspace/` bị gitignore); tự chạy lại theo [docs/model-workflow.md](docs/model-workflow.md) mục 10 |
| Seed Tầng 1 cục bộ (`index.parquet`, `pp_seed.yaml`, `seed_latest.pth`) | **Không có**; chỉ có 1 checkpoint 80 epoch qua Git LFS (~70 MB) dùng làm trọng số mặc định cho Colab. Tầng 1 cục bộ: tự train bằng Docker GPU hoặc dùng Colab |
| Trọng số YOLO/DINOv2/OpenCLIP | **Không có**; tải bằng `model/scripts/fetch_weights.py` khi cần `multisensor` |

## v2 (đang phát triển): rare_v24 + bối cảnh camera

Phiên bản v2 (đích 0.7.0) bổ sung engine `rare_v24` nhằm phát hiện tình huống hiếm RHCIO và đánh giá theo từng instance VRU.
Hệ thống tích hợp tầng bối cảnh ảnh camera kết hợp OpenCV và OpenCLIP pretrained (không dùng VLM) với hai profile `lidar_only` (thuần CPU) và `multisensor`.
Quy trình chọn lọc ưu tiên capture B (thu thập instance ở đúng khoảnh khắc dạng hiếm), áp dụng phạt track và MMR để chọn đúng B frame.
Toàn bộ quy trình được chuẩn hoá qua CLI và notebook Colab A100 phục vụ pitching và kiểm chứng.

| Lệnh | Mô tả |
|---|---|
| `python -m c4.cli.rare run` | Chạy engine `rare_v24` chấm điểm và chọn B frame theo profile `lidar_only` hoặc `multisensor`. |
| `python -m c4.cli.rare crops` | Cắt crop ảnh camera theo bounding box và trích xuất vector ngữ nghĩa OpenCLIP. |
| `python -m c4.cli.context cv` | Trích xuất 13 đặc trưng chất lượng hình ảnh (độ sáng, nhiễu, chói) bằng OpenCV. |
| `python -m c4.cli.context fit` | Khớp ngưỡng phân vị bối cảnh trên tập V để đóng băng luật phân loại. |
| `python -m c4.cli.context run` | Gán thẻ bối cảnh camera (chiếu sáng, thời tiết, chói) cho từng frame. |
| `python -m c4.cli.bench_pitch` | Benchmark so sánh các phương pháp chọn frame (IY, IRecall, oracle, random) trên mini/pool. |

Chi tiết luồng hoạt động xem tại [docs/model-workflow.md](docs/model-workflow.md) (mục "Engine rare_v24") và hướng dẫn chạy benchmark tại [docs/colab-dev-setup.md](docs/colab-dev-setup.md) (mục "Benchmark pitching").

Trạng thái (2026-10-14): chưa phát hành 0.7.0. Benchmark T (prereg `pitch-v2`) **đã chạy 2026-10-13** trên Colab A100:
M2 − M1 = −0,014 [−0,164; 0,084] ⇒ **chưa chứng minh** vượt baseline M1; số đo và kết luận chi tiết ở [docs/project-status.md](docs/project-status.md).
Engine mặc định của service vẫn là `c4_legacy`; chọn `rare_v24` ở dashboard (Chi tiết kỹ thuật → Engine) hoặc đặt `VCF_ENGINE_DEFAULT=rare_v24`.
Cài GPU cho `multisensor`: [docs/getting-started.md](docs/getting-started.md) mục "Bật engine rare_v24 / OpenCLIP (GPU)".

## Kiến trúc

```text
 Trình duyệt ──► web/ (Next.js, :3000) ──/api/**──► model/worker/service (FastAPI, :8001)
                    │  upload chunk 50 MB, media Range          │  job runner
                    └───────────── chung thư mục WORKSPACE ◄────┘  c4.lidar: index -> Tầng 0 (CPU)
                                   uploads/ datasets/ jobs/               -> [Tầng 1 PointPillars, GPU]
                                                                          -> chọn 5 % (MMR + quota)
```

* **Tầng 0** (bắt buộc, CPU): descriptor hình học -> PCA 64 -> Rarity k-NN khác scene -> MMR + quota.
* **Tầng 1** (tuỳ chọn, GPU): PointPillars train từ đầu trên seed -> novelty/uncertainty -> hybrid.
  Thiếu Tầng 1 thì mọi thứ vẫn chạy (chỉ dùng tiêu chí "Hiếm trong dữ liệu"; xem [docs/glossary.md](docs/glossary.md)).
* **Tầng 1 từ xa (Colab)** — máy không GPU vẫn có Tầng 1: Colab kéo việc từ worker qua tunnel, train rồi đẩy
  `signals.parquet` về (nút "Chạy Tầng 1 trên Colab"). Điền URL + token rồi **Run all**:
  [![Open in Colab](https://colab.research.google.com/assets/colab-badge.svg)](https://colab.research.google.com/github/Nguyendev037/VCuboidFit/blob/main/model/notebooks/vcf_colab_agent.ipynb)
  ([hướng dẫn](docs/colab-dev-setup.md), Cách 1).
* **Dev mới, không cần GPU/Docker**:
  [![Open in Colab](https://colab.research.google.com/assets/colab-badge.svg)](https://colab.research.google.com/github/Nguyendev037/VCuboidFit/blob/main/model/notebooks/vcf_dev_setup_colab.ipynb)
  — 4 ô đọc ZIP trong `MyDrive/datatest`, chạy CPU và lưu kết quả về Drive; GPU tùy chọn ([hướng dẫn](docs/colab-dev-setup.md)).
* **Giao diện**: xoá lịch sử chạy, thanh thời gian xét tệp upload, nút "Rút gọn" danh sách zip, panel tham số
  hoạt động cả khi job chỉ có Tầng 0.

## Cấu trúc thư mục

```text
VCuboidFit/
├── web/                 Website Next.js 16 + React 19 (Chọn 5 %, Deep Review, Frame Viewer)
│   ├── app/             trang + route /api/** proxy sang worker
│   ├── components/ lib/ UI và logic phía client (kèm *.test.ts)
│   ├── e2e/ mocks/      Playwright e2e + dữ liệu mock (NEXT_PUBLIC_MOCK=1)
│   └── design/          token màu + mock HTML thiết kế
├── model/
│   ├── worker/          Python: c4/ (engine), service/ (FastAPI), configs/, tests/
│   ├── docker/          tier1/ (PointPillars GPU), worker/ (worker CPU), cloud/ (máy thuê)
│   ├── scripts/         chạy Tầng 1, agent + setup Colab, check_ports, cloud/
│   └── notebooks/       Colab chạy Tầng 1 cho worker; Colab tự chạy từ ZIP Drive
├── dataset/             hướng dẫn + manifest nuScenes-mini (zip bị gitignore, tự đóng gói)
├── tools/vcf-pack/      CLI chia nuScenes thành part zip <= 50 MB + manifest
└── docs/                hướng dẫn chạy, thuê GPU, Colab, quy trình model, thuật ngữ
```

| Thư mục | Nội dung |
|---|---|
| [`web/`](web/) | Website Next.js 16 + React 19 (3 màn: Chọn 5 %, Deep Review, Frame Viewer) |
| [`model/`](model/README.md) | Engine `c4` + service FastAPI + cấu hình + test, Docker, script, notebook |
| [`dataset/`](dataset/README.md) | Cách có bộ zip nuScenes-mini để thử upload (zip không commit; chỉ có manifest) |
| [`tools/vcf-pack/`](tools/vcf-pack/) | CLI chia thư mục nuScenes thành các part zip <= 50 MB + manifest |
| [`docs/`](docs/) | Hướng dẫn chạy local, thuê GPU, Colab, quy trình model, thuật ngữ |

## Quickstart chi tiết (Windows, chỉ CPU)

Cần Python 3.11+ và Node 20+. Từ thư mục gốc repo (PowerShell):

```powershell
# 1) Engine + worker
python -m venv model\worker\.venv
model\worker\.venv\Scripts\pip install -e "model\worker[dev,service]"
$env:WORKSPACE = "$PWD\model\workspace"
cd model\worker ; .venv\Scripts\python -m uvicorn service.main:create_app --factory --port 8001
```
```powershell
# 2) Web (cửa sổ khác, từ thư mục gốc repo)
cd web ; copy .env.example .env.local ; npm ci ; npm run dev       # http://localhost:3000
```
3) Mở <http://localhost:3000>, ở Bước 1 chọn **tất cả** file `vcf_part_*.zip` + `vcf_manifest.json` của một bộ dữ liệu,
chờ upload, rồi bấm chạy phân tích. Clone **không** kèm các zip: tự tạo bằng `tools/vcf-pack` từ nuScenes-mini
([dataset/README.md](dataset/README.md)).

Worker bằng Docker thay cho bước 1 (CPU, đã có 7-Zip để giải nén `.rar`/`.7z`):

```powershell
docker build -f model/docker/worker/Dockerfile -t vcuboidfit_worker:0.1 .
docker run -d --name vcuboidfit-worker -e VCF_PORT=8001 -p 8001:8001 -v "$PWD\model\workspace:/data/workspace" vcuboidfit_worker:0.1
```

Muốn xem giao diện ngay không cần worker: trong `web/` chạy `$env:NEXT_PUBLIC_MOCK="1"; npm run dev`.
Chi tiết từng bước và xử lý lỗi: [docs/run-local.md](docs/run-local.md).

## Tài liệu

* [docs/run-local.md](docs/run-local.md) - chạy local (CPU, Docker GPU RTX 4060, worker Docker, Tầng 1 qua Colab)
* [docs/gpu-rental.md](docs/gpu-rental.md) - thuê GPU, chạy trên trainval
* [docs/getting-started.md](docs/getting-started.md) - mở dự án sau clone: yêu cầu, dữ liệu, web, worker, Tầng 1, rare_v24/GPU, kiểm thử, lỗi hay gặp
* [docs/colab-dev-setup.md](docs/colab-dev-setup.md) - Google Colab: chạy Tầng 1 cho máy bạn (Run all), hoặc tự chạy từ ZIP
* [docs/model-workflow.md](docs/model-workflow.md) - model chọn 5% frame chạy như thế nào (từng bước)
* [docs/glossary.md](docs/glossary.md) - "hiếm" là gì, ý nghĩa từng chỉ số và tham số
* [docs/project-status.md](docs/project-status.md) - tình trạng dự án, số đo hiện có và kế hoạch còn lại theo phase
* [docs/web.md](docs/web.md) - trang chủ, phương pháp kiểm chứng, typography, media mẫu và bàn giao agent frontend

## Biến môi trường

| Biến | Bên | Mặc định | Ý nghĩa |
|---|---|---|---|
| `WORKSPACE` | worker + web | worker `../workspace`, web `<repo>/workspace` | Thư mục dữ liệu chạy (`uploads/ datasets/ jobs/`); hai bên PHẢI trỏ cùng chỗ |
| `VCF_PORT` | worker + web + tunnel | `8001` | Cổng worker nghe/publish; web suy `http://127.0.0.1:${VCF_PORT}` khi không có `WORKER_URL` |
| `VCF_REMOTE_TOKEN` | worker | rỗng (tắt) | Bật cầu nối Colab; thiếu biến thì mọi `/remote/*` trả 404 `remote_disabled` |
| `VCF_REMOTE_LEASE_SEC` | worker | `5400` | Hạn giữ việc Tầng 1 từ xa trước khi trả về hàng đợi |
| `VCF_REMOTE_MAX_RESULT_MB` | worker | `200` | Dung lượng tối đa của `signals.parquet` Colab tải lên |
| `VCF_ENGINE_DEFAULT` | worker | `c4_legacy` | Engine khi request `/jobs/{id}/select` không gửi `engineVersion` (`c4_legacy` / `rare_v24`) |
| `C4_WEIGHTS_DIR` | worker | `model/workspace/weights` | Thư mục trọng số YOLO/DINOv2/OpenCLIP (cần cho `multisensor`; tải bằng `model/scripts/fetch_weights.py`) |
| `VCF_T1_EXP` | worker | tự dò `model/workspace/experiments` | Thí nghiệm có trọng số seed gửi kèm việc Colab (bỏ train); `none` = tắt. Không có thì Colab dùng trọng số mặc định trên GitHub |

Chi tiết đầy đủ: `model/worker/.env.example` và `web/.env.example`.

## Dữ liệu và giấy phép dữ liệu

nuScenes thuộc CC BY-NC-SA 4.0 (chỉ phi thương mại, cần ghi nguồn). Repo **không** chứa dữ liệu nuScenes;
các zip trong `dataset/` bị gitignore. Cách có dữ liệu: [dataset/README.md](dataset/README.md).
