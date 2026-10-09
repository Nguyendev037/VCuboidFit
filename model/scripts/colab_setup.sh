#!/usr/bin/env bash
# Setup moi truong Tang 1 tren Colab cho dev moi (SPEC-P02 §6b). Idempotent, khong can Docker.
#   bash model/scripts/colab_setup.sh [--cpu-only]
# --cpu-only: bo buoc 3 (OpenPCDet) va coi loi spconv la canh bao (may khong GPU chi chay Tang 0).
# Bien: VCF_HOME (mac dinh $HOME/vcf) giu build OpenPCDet + marker cache qua cac phien.
set -euo pipefail
CPU_ONLY=0
for a in "$@"; do case "$a" in --cpu-only) CPU_ONLY=1;; *) echo "tham so la: $a" >&2; exit 2;; esac; done
REPO=$(cd "$(dirname "$0")/../.." && pwd)
VCF_HOME=${VCF_HOME:-$HOME/vcf}; mkdir -p "$VCF_HOME"
PCDET_COMMIT=233f849829b6ac19afb8af8837a0246890908755
PY=${PYTHON:-python3}
command -v "$PY" >/dev/null || PY=python
"$PY" -c 'import sys; sys.exit(0 if sys.version_info >= (3,10) else 1)' \
  || { echo "can Python 3.10+" >&2; exit 1; }

echo "== [1/5] GPU"
GPU=none; CUDA_MAJOR=12
if command -v nvidia-smi >/dev/null 2>&1 && nvidia-smi -L >/dev/null 2>&1; then
  GPU=$(nvidia-smi --query-gpu=name --format=csv,noheader | head -1)
  CUDA_MAJOR=$(nvidia-smi | sed -n 's/.*CUDA Version: \([0-9]*\)\..*/\1/p' | head -1)
  CUDA_MAJOR=${CUDA_MAJOR:-12}
  echo "GPU: $GPU (CUDA $CUDA_MAJOR)"
else
  echo "CANH BAO: khong thay GPU (nvidia-smi) - van cai phan CPU"
fi
if [ "$CUDA_MAJOR" -ge 12 ]; then SPCONV=spconv-cu120; else SPCONV=spconv-cu118; fi

echo "== [2/5] pip pinned set"
PINS="$SPCONV|numpy<2|nuscenes-devkit|easydict|tensorboardX|kornia==0.6.12|scikit-learn|joblib|pyarrow|pandas|pyyaml|opencv-python-headless|requests"
PIN_HASH=$(printf '%s' "$PINS" | "$PY" -c 'import sys,hashlib;print(hashlib.sha256(sys.stdin.read().encode()).hexdigest()[:16])')
# Marker pip PHAI nam o runtime (/tmp), khong tren Drive: phien Colab moi mat goi pip nhung Drive van con marker.
PIN_MARK=${VCF_RUNTIME_DIR:-/tmp}/.vcf_pins_$PIN_HASH
if [ -f "$PIN_MARK" ]; then
  echo "cache: bo pip da cai (marker $PIN_HASH)"
else
  IFS='|' read -r -a PKGS <<< "$PINS"
  if [ "$CPU_ONLY" = 1 ]; then
    "$PY" -m pip -q install "${PKGS[@]:1}"
    "$PY" -m pip -q install "$SPCONV" || echo "CANH BAO: khong cai duoc $SPCONV (--cpu-only)"
  else
    "$PY" -m pip -q install "${PKGS[@]}"
  fi
  touch "$PIN_MARK"
fi

echo "== [3/5] OpenPCDet"
if [ "$CPU_ONLY" = 1 ]; then
  echo "bo qua (--cpu-only)"
elif [ -f "$VCF_HOME/OpenPCDet/.built" ] && [ "$(cat "$VCF_HOME/OpenPCDet/BUILD_COMMIT" 2>/dev/null)" = "$PCDET_COMMIT" ]; then
  echo "cache: OpenPCDet da build o $VCF_HOME/OpenPCDet"
else
  T=$(mktemp -d)
  rm -rf "$VCF_HOME/OpenPCDet"
  "$PY" - "$T/pcdet.tgz" "$PCDET_COMMIT" <<'PYEOF'
import sys, urllib.request
urllib.request.urlretrieve(f"https://github.com/open-mmlab/OpenPCDet/archive/{sys.argv[2]}.tar.gz", sys.argv[1])
PYEOF
  tar xzf "$T/pcdet.tgz" -C "$T"
  mv "$T/OpenPCDet-$PCDET_COMMIT" "$VCF_HOME/OpenPCDet"
  rm -rf "$T"
  echo "$PCDET_COMMIT" > "$VCF_HOME/OpenPCDet/BUILD_COMMIT"
  "$PY" "$REPO/model/docker/tier1/patch_pcdet.py" "$VCF_HOME/OpenPCDet"
  (cd "$VCF_HOME/OpenPCDet" && TORCH_CUDA_ARCH_LIST="7.5;8.0;8.6;8.9" "$PY" -m pip install -q --no-build-isolation -e .)
  touch "$VCF_HOME/OpenPCDet/.built"
fi

echo "== [4/5] phu thuoc worker"
"$PY" -m pip -q install -e "$REPO/model/worker[service,dev]"

echo "== [5/5] tom tat"
"$PY" --version
"$PY" - <<'PYEOF'
import importlib
for m in ("numpy", "pandas", "pyarrow", "sklearn", "kornia", "spconv", "torch", "pcdet"):
    try:
        mod = importlib.import_module(m)
        print(f"  {m:8s} {getattr(mod, '__version__', 'ok')}")
    except Exception as e:
        print(f"  {m:8s} -- ({type(e).__name__})")
PYEOF
echo "export VCF_HOME=$VCF_HOME PCDET_ROOT=$VCF_HOME/OpenPCDet PYTHONPATH=$REPO/model/worker:$VCF_HOME/OpenPCDet"
echo "SETUP OK"
