#!/usr/bin/env bash
# Đóng gói để mang đi thuê GPU (chạy trên máy local có Docker). SPEC-P04 §C.
#   bash scripts/cloud/pack.sh [--with-image]   → dist/vcf-cloud-<sha>.tar.gz (+ vcf-tier1.tar.gz)
set -euo pipefail
cd "$(dirname "$0")/../.."
SHA=$(if [ -e ../.git ]; then git rev-parse --short HEAD; else printf source; fi); OUT=dist; mkdir -p "$OUT"
tar --exclude=".venv" --exclude="__pycache__" --exclude=".pytest_cache" --exclude=".ruff_cache" --exclude="*.egg-info" --exclude=".env*" --exclude="*.pth" --exclude="*.pt" --exclude="*.ckpt" -czf "$OUT/vcf-cloud-$SHA.tar.gz" worker docker scripts
echo "mã nguồn: $OUT/vcf-cloud-$SHA.tar.gz ($(du -h "$OUT/vcf-cloud-$SHA.tar.gz" | cut -f1))"
if [ "${1:-}" = "--with-image" ]; then
  docker save vcuboidfit_pointpillars:0.1 | gzip -1 > "$OUT/vcf-tier1.tar.gz"
  echo "image: $OUT/vcf-tier1.tar.gz ($(du -h "$OUT/vcf-tier1.tar.gz" | cut -f1)) — giải nén cạnh repo rồi bootstrap.sh tự nạp"
fi
