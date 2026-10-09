# model/ - engine, service, GPU

```text
model/
  worker/      Python: c4/ (engine), service/ (FastAPI), configs/, tests/, pyproject.toml
  docker/      tier1/ (image vcuboidfit_pointpillars, GPU), worker/ (image vcuboidfit_worker, CPU),
               cloud/ (docker-compose cho máy thuê)
  scripts/     tier1.ps1 / tier1.sh (chạy Tầng 1), colab_agent.py + colab_setup.sh (Tầng 1 qua Colab),
               check_ports.py (bắt cổng ghi cứng), cloud/{pack,bootstrap}.sh, fetch_weights.py
  notebooks/   run_on_colab.ipynb (Colab), run_on_kaggle.ipynb (Kaggle)
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
