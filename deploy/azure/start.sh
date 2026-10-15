#!/usr/bin/env bash
set -euo pipefail
mkdir -p "$WORKSPACE/uploads" "$WORKSPACE/datasets" "$WORKSPACE/jobs"
cd /app/model/worker
python -m uvicorn service.main:create_app --factory --host 127.0.0.1 --port "$VCF_PORT" &
cd /app/web
node server.js &
wait -n
exit 1
