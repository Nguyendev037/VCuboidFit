#!/bin/sh
# Worker (tiến trình chính, exec để nhận tín hiệu dừng). Cổng: MỘT biến VCF_PORT (SPEC-P01 §2b).
set -e
mkdir -p "$WORKSPACE/uploads" "$WORKSPACE/datasets" "$WORKSPACE/jobs"
cd /app/model/worker
exec python -m uvicorn service.main:create_app --factory --host 0.0.0.0 --port "${VCF_PORT:-8001}"
