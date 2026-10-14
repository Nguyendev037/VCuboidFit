# Model, worker và GPU VCuboidFIT

```text
model/
├── worker/       c4/ engine, service/ FastAPI, configs/, tests/, pyproject.toml
├── scripts/      dev_up.ps1, tier1.ps1/sh, fetch_weights.py, Colab và cloud
├── docker/       worker CPU, tier1 GPU, gói cloud
├── notebooks/    bridge Colab, Drive ZIP, benchmark A100
└── workspace/    local ignored: uploads/datasets/jobs/experiments/weights
```

## Cài và chạy backend

Từ root repo, Windows PowerShell:

```powershell
python -m venv model\worker\.venv
model\worker\.venv\Scripts\python -m pip install -e "model\worker[dev,service]"
powershell -NoProfile -ExecutionPolicy Bypass -File model/scripts/dev_up.ps1
```

Script đặt `WORKSPACE=<repo>/model/workspace` và cổng 8001; nếu cổng đã bận thì không dừng listener hiện có. Seed tự dò phải có đủ index, cfg và checkpoint đúng bố cục; checkpoint LFS sau clone chưa đủ để được nhận làm seed local. Backend không tự đọc `.env`, xem [mẫu biến](worker/.env.example). Frontend chạy terminal riêng, cùng workspace: [README chính](../README.md).

Health: `http://127.0.0.1:8001/health`; API docs: `http://127.0.0.1:8001/docs`. Legacy `c4_legacy` là default; `rare_v24` có `lidar_only` và `multisensor` OpenCV/OpenCLIP. CPU đủ cho legacy Tầng 0 và bộ cụm LiDAR; PointPillars/CLIP cần môi trường tương ứng, không tự được tải khi chỉ clone code.

## Model, đánh giá và dữ liệu

PointPillars đã chạy local trên mini. Tầng 1 trong Docker, GPU thuê và Colab có cách chuẩn bị riêng. Benchmark T A100 của `pitch-v2` đã xong nhưng chưa chứng minh hơn baseline; không chạy lại T để thử hướng dẫn hoặc gán số đó cho detector mới.

Các job demo và dataset/trọng số ngoài checkpoint LFS không đi kèm Git. Người dùng đã xoá lịch sử ba job demo ngày 14/10; tạo job mới để dùng Review. Không sửa `job.json` thành done khi pipeline thực tế chưa chạy.

CLI/config, freeze, contract bảng và ranh giới nhãn: [model-workflow](../docs/model-workflow.md). Cài GPU và kiểm thử theo [getting-started](../docs/getting-started.md); vận hành [run-local](../docs/run-local.md), [gpu-rental](../docs/gpu-rental.md), [colab-dev-setup](../docs/colab-dev-setup.md). Số đo/cổng còn lại: [project-status](../docs/project-status.md).
