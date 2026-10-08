# model/ - engine, service, GPU

```text
model/
  worker/      Python: c4/ (engine), service/ (FastAPI), configs/, tests/, pyproject.toml
  docker/      tier1/ (image PointPillars/OpenPCDet), cloud/ (docker-compose cho máy thuê)
  scripts/     tier1.ps1 / tier1.sh (chạy Tầng 1), cloud/{pack,bootstrap}.sh, fetch_weights.py
  notebooks/   vcf_tier01_kaggle_colab.ipynb
```

## Chạy ở máy cá nhân (CPU)

```powershell
cd model\worker
python -m venv .venv
.venv\Scripts\pip install -e ".[dev,service]"
.venv\Scripts\python -m pytest -q -m "not perf and not gpu" tests/lidar tests/service/test_lidar.py tests/service/test_models.py
$env:WORKSPACE = "..\workspace"        # = model/workspace, web phải trỏ cùng chỗ
.venv\Scripts\python -m uvicorn service.main:create_app --factory --port 8001
```

Thí nghiệm không qua web (CLI): `python -m c4.cli.lidar_experiment --data-root <nuScenes> --out ..\workspace\experiments\mini --split V --tune`.

Tầng 1 (Docker + GPU), máy thuê, Kaggle: xem [docs/run-local.md](../docs/run-local.md),
[docs/gpu-rental.md](../docs/gpu-rental.md), [docs/kaggle-colab.md](../docs/kaggle-colab.md).
Các biến môi trường: [`worker/.env.example`](worker/.env.example) (worker không tự đọc `.env`,
hãy đặt biến trong shell).
