# VCuboidFIT

Chọn **5 % keyframe LiDAR đáng gán nhãn 3D nhất** từ một bộ dữ liệu nuScenes — chỉ dùng point cloud,
ego pose và timestamp (không camera, không nhãn). Có engine Python (CPU, thêm tầng PointPillars
tuỳ chọn trên GPU) và website Next.js để nạp dữ liệu, chỉnh tham số, xem kết quả, soi từng frame.

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
  Thiếu Tầng 1 thì mọi thứ vẫn chạy.

## Cấu trúc thư mục

| Thư mục | Nội dung |
|---|---|
| [`web/`](web/) | Website Next.js 16 + React 19 (3 màn: Chọn 5 %, Deep Review, Frame Viewer) |
| [`model/`](model/README.md) | Engine `c4` + service FastAPI + cấu hình + test, Docker, script, notebook |
| [`dataset/`](dataset/README.md) | Bộ zip nuScenes-mini đã đóng gói để thử upload (zip không commit) |
| [`tools/vcf-pack/`](tools/vcf-pack/) | CLI chia thư mục nuScenes thành các part zip <= 50 MB + manifest |
| [`docs/`](docs/) | Hướng dẫn chạy, thuê GPU, Kaggle/Colab, kiến trúc + PDF thiết kế |

## Quickstart 5 phút (Windows, chỉ CPU)

Cần Python 3.11+ và Node 20+. Từ thư mục gốc repo (PowerShell):

```powershell
# 1) Engine + worker
python -m venv model\worker\.venv
model\worker\.venv\Scripts\pip install -e "model\worker[dev,service]"
$env:WORKSPACE = "$PWD\model\workspace"
cd model\worker ; ..\..\model\worker\.venv\Scripts\python -m uvicorn service.main:create_app --factory --port 8001
```
```powershell
# 2) Web (cửa sổ khác, từ thư mục gốc repo)
cd web ; copy .env.example .env.local ; npm ci ; npm run dev       # http://localhost:3000
```
3) Mở <http://localhost:3000>, ở Bước 1 chọn **tất cả** file trong `dataset/01_small_3scenes/`
(các `vcf_part_*.zip` + `vcf_manifest.json`), chờ upload, rồi bấm chạy phân tích.

Muốn xem giao diện ngay không cần worker: trong `web/` chạy `$env:NEXT_PUBLIC_MOCK="1"; npm run dev`.
Chi tiết từng bước và xử lý lỗi: [docs/run-local.md](docs/run-local.md).

## Tài liệu

* [docs/run-local.md](docs/run-local.md) - chạy local (CPU, Docker GPU RTX 4060)
* [docs/gpu-rental.md](docs/gpu-rental.md) - thuê GPU, chạy trên trainval
* [docs/kaggle-colab.md](docs/kaggle-colab.md) - notebook Kaggle / Colab Pro
* [docs/architecture.md](docs/architecture.md) - thiết kế + engine LiDAR; PDF gốc cạnh đó

## Dữ liệu và giấy phép dữ liệu

nuScenes thuộc CC BY-NC-SA 4.0 (chỉ phi thương mại, cần ghi nguồn). Repo **không** chứa dữ liệu nuScenes;
các zip trong `dataset/` bị gitignore.
