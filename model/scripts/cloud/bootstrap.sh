#!/usr/bin/env bash
# Chạy MỘT LẦN trên máy GPU thuê (Ubuntu 22.04, đã có NVIDIA driver). SPEC-P04 §C.
#   bash scripts/cloud/bootstrap.sh            # cài Docker + nvidia-container-toolkit nếu thiếu, nạp image
set -euo pipefail
cd "$(dirname "$0")/../.."
if ! command -v docker >/dev/null; then
  curl -fsSL https://get.docker.com | sh
fi
if ! docker info 2>/dev/null | grep -q nvidia; then
  distribution=$(. /etc/os-release; echo $ID$VERSION_ID)
  curl -fsSL https://nvidia.github.io/libnvidia-container/gpgkey | sudo gpg --dearmor -o /usr/share/keyrings/nvidia-container-toolkit-keyring.gpg
  curl -fsSL https://nvidia.github.io/libnvidia-container/stable/deb/nvidia-container-toolkit.list \
    | sed 's#deb https://#deb [signed-by=/usr/share/keyrings/nvidia-container-toolkit-keyring.gpg] https://#g' \
    | sudo tee /etc/apt/sources.list.d/nvidia-container-toolkit.list
  sudo apt-get update && sudo apt-get install -y nvidia-container-toolkit
  sudo nvidia-ctk runtime configure --runtime=docker && sudo systemctl restart docker
fi
if [ -f vcf-tier1.tar.gz ]; then
  echo "nạp image từ vcf-tier1.tar.gz"; gunzip -c vcf-tier1.tar.gz | docker load
else
  echo "build image (≈15–25 phút)"; docker build -t vcf-tier1:0.1 docker/tier1
fi
docker run --rm --gpus all vcf-tier1:0.1 python -c "import torch,pcdet;print('GPU', torch.cuda.get_device_name(0))"
echo "OK. Tiếp: tải nuScenes trainval vào \$NUSC (docs/gpu-rental.md §3) rồi chạy compose."
