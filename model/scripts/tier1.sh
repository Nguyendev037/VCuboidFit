#!/usr/bin/env bash
# Tầng 1 (SPEC-P02 §4) — dùng chung cho Docker local (WSL2/4060), GPU thuê, Colab.
#   scripts/tier1.sh <nuscenes_root> <exp_dir> [--sweeps N] [--epochs E] [--batch B] [--no-docker]
# --no-docker: chạy thẳng trong môi trường đã có pcdet (Colab sau khi cài theo docs).
# Yêu cầu: <exp_dir>/index.parquet đã có (chạy Tầng 0 trước: c4.cli.lidar_experiment).
set -euo pipefail
DATA=$(cd "$1" && pwd); EXP=$(mkdir -p "$2" && cd "$2" && pwd); shift 2
SWEEPS=10; EPOCHS=20; BATCH=2; DOCKER=1; IMAGE=${VCF_TIER1_IMAGE:-vcuboidfit_pointpillars:0.1}
while [ $# -gt 0 ]; do case "$1" in
  --sweeps) SWEEPS=$2; shift 2;; --epochs) EPOCHS=$2; shift 2;; --batch) BATCH=$2; shift 2;;
  --no-docker) DOCKER=0; shift;; *) echo "tham số lạ: $1" >&2; exit 2;; esac; done
REPO=$(cd "$(dirname "$0")/.." && pwd)
[ -f "$EXP/index.parquet" ] || { echo "thiếu $EXP/index.parquet — chạy Tầng 0 trước" >&2; exit 4; }
run() {
  if [ "$DOCKER" = 1 ]; then
    docker run --rm --gpus all --shm-size 8g -v "$DATA":/nusc:ro -v "$EXP":/exp \
      -v "$REPO/worker":/work/worker -w /work/worker "$IMAGE" python -m "$@"
  else
    (cd "$REPO/worker" && python -m "$@" )
  fi
}
if [ "$DOCKER" = 0 ]; then
  # train_seed/infer_t1 đọc PCDET_ROOT (mặc định /opt/OpenPCDet = đường của image) và BUILD_COMMIT
  : "${PCDET_ROOT:?--no-docker cần export PCDET_ROOT=<thư mục OpenPCDet đã build>}"
  export PCDET_ROOT
  [ -f "$PCDET_ROOT/BUILD_COMMIT" ] || { echo "thiếu $PCDET_ROOT/BUILD_COMMIT — echo <commit> > nó (Dockerfile tự ghi; train_seed đọc cuối bước)" >&2; exit 4; }
fi
if [ "$DOCKER" = 1 ]; then A_EXP=/exp; A_NUSC=/nusc; else A_EXP=$EXP; A_NUSC=$DATA; fi
time run c4.lidar.tier1.train_seed --exp "$A_EXP" --nusc "$A_NUSC" --sweeps "$SWEEPS" \
  --epochs "$EPOCHS" --batch "$BATCH"
time run c4.lidar.tier1.infer_t1 --exp "$A_EXP" --batch "$BATCH"
echo "xong Tầng 1 → $EXP/t1 ; chạy tiếp: python -m c4.cli.lidar_experiment --data-root $DATA --out $EXP --split V --tune"
