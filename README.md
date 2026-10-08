# VCuboidFIT

Chọn **5 % keyframe LiDAR đáng gán nhãn 3D nhất** từ một bộ dữ liệu nuScenes — chỉ dùng point cloud,
ego pose và timestamp (không camera, không nhãn). Có engine Python (CPU, thêm tầng PointPillars
tuỳ chọn trên GPU) và website Next.js để nạp dữ liệu, chỉnh tham số, xem kết quả, soi từng frame.

> **Repo này là ROOT duy nhất của dự án** (bản hoàn chỉnh nhất, phiên bản hiện tại v0.6.1). Mọi thay đổi
> code, tài liệu, Docker, notebook đều làm, commit và push thẳng tại đây — không sinh lại từ nơi khác.

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
  `signals.parquet` về (nút "Chạy Tầng 1 trên Colab"). Xem [docs/run-local.md](docs/run-local.md) mục 5c.
* **Dev mới, không cần GPU/Docker**:
  [![Open in Colab](https://colab.research.google.com/assets/colab-badge.svg)](https://colab.research.google.com/github/Nguyendev037/VCuboidFit/blob/main/model/notebooks/vcf_dev_setup_colab.ipynb)
  — notebook dựng sẵn môi trường Tầng 0 + Tầng 1 ([hướng dẫn](docs/colab-dev-setup.md)).
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
│   └── notebooks/       Kaggle/Colab Tầng 1, agent Colab, setup dev mới
├── dataset/             zip nuScenes-mini để thử upload (zip bị gitignore)
├── tools/vcf-pack/      CLI chia nuScenes thành part zip <= 50 MB + manifest
└── docs/                hướng dẫn chạy, thuê GPU, Colab, quy trình model, thuật ngữ
```

| Thư mục | Nội dung |
|---|---|
| [`web/`](web/) | Website Next.js 16 + React 19 (3 màn: Chọn 5 %, Deep Review, Frame Viewer) |
| [`model/`](model/README.md) | Engine `c4` + service FastAPI + cấu hình + test, Docker, script, notebook |
| [`dataset/`](dataset/README.md) | Bộ zip nuScenes-mini đã đóng gói để thử upload (zip không commit) |
| [`tools/vcf-pack/`](tools/vcf-pack/) | CLI chia thư mục nuScenes thành các part zip <= 50 MB + manifest |
| [`docs/`](docs/) | Hướng dẫn chạy local, thuê GPU, Kaggle/Colab, quy trình model, thuật ngữ |

## Quickstart 5 phút (Windows, chỉ CPU)

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
3) Mở <http://localhost:3000>, ở Bước 1 chọn **tất cả** file trong `dataset/01_small_3scenes/`
(các `vcf_part_*.zip` + `vcf_manifest.json`), chờ upload, rồi bấm chạy phân tích.

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
* [docs/kaggle-colab.md](docs/kaggle-colab.md) - notebook Kaggle / Colab Pro + agent Colab
* [docs/colab-dev-setup.md](docs/colab-dev-setup.md) - dev mới: môi trường chạy được trên Colab (không GPU, không Docker)
* [docs/model-workflow.md](docs/model-workflow.md) - model chọn 5% frame chạy như thế nào (từng bước)
* [docs/glossary.md](docs/glossary.md) - "hiếm" là gì, ý nghĩa từng chỉ số và tham số

## Biến môi trường

| Biến | Bên | Mặc định | Ý nghĩa |
|---|---|---|---|
| `WORKSPACE` | worker + web | worker `../workspace`, web `<repo>/workspace` | Thư mục dữ liệu chạy (`uploads/ datasets/ jobs/`); hai bên PHẢI trỏ cùng chỗ |
| `VCF_PORT` | worker + web + tunnel | `8001` | Cổng worker nghe/publish; web suy `http://127.0.0.1:${VCF_PORT}` khi không có `WORKER_URL` |
| `VCF_REMOTE_TOKEN` | worker | rỗng (tắt) | Bật cầu nối Colab; thiếu biến thì mọi `/remote/*` trả 404 `remote_disabled` |
| `VCF_REMOTE_LEASE_SEC` | worker | `5400` | Hạn giữ việc Tầng 1 từ xa trước khi trả về hàng đợi |
| `VCF_REMOTE_MAX_RESULT_MB` | worker | `200` | Dung lượng tối đa của `signals.parquet` Colab tải lên |

Chi tiết đầy đủ: `model/worker/.env.example` và `web/.env.example`.

## Dữ liệu và giấy phép dữ liệu

nuScenes thuộc CC BY-NC-SA 4.0 (chỉ phi thương mại, cần ghi nguồn). Repo **không** chứa dữ liệu nuScenes;
các zip trong `dataset/` bị gitignore.
