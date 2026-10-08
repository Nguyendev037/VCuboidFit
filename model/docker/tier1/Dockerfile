# Tầng 1 (M4/M5): PointPillars huấn luyện từ đầu trên seed S bằng OpenPCDet.
# Một image cho cả 3 nơi chạy: RTX 4060 local (WSL2), GPU thuê, Kaggle/Colab (dùng script giống hệt).
# CUDA 11.8 + sm_75..sm_90: T4, A10/3090, 4060/4090/L4, A100, H100.
FROM pytorch/pytorch:2.1.2-cuda11.8-cudnn8-devel

ENV TORCH_CUDA_ARCH_LIST="7.5;8.0;8.6;8.9;9.0+PTX" \
    PIP_NO_CACHE_DIR=1 \
    PYTHONUNBUFFERED=1

# KHÔNG dùng apt/git: mạng local chặn archive.ubuntu.com:80 (đo 2026-10-08). Image devel đã có
# gcc/g++/nvcc; mọi thứ khác qua pip/HTTPS.
# Phiên bản ghim: đổi ở đây là đổi môi trường thí nghiệm, phải ghi vào changelog.
RUN pip install "ninja==1.11.1.1" "numpy==1.26.4" "spconv-cu118==2.3.6" "numba==0.58.1" \
        "llvmlite==0.41.1" "nuscenes-devkit==1.1.11" "easydict==1.13" "tensorboardX==2.6.2.2" \
        "pyyaml==6.0.1" "scikit-image==0.22.0" "tqdm" \
        "opencv-python-headless==4.9.0.80" "pyquaternion==0.9.9" "kornia==0.6.12" \
        "pandas==2.2.2" "pyarrow==15.0.2" "scikit-learn==1.4.2" "joblib==1.4.2" \
        "pillow==10.3.0" "filelock==3.13.4"

ARG OPENPCDET_REF=233f849829b6ac19afb8af8837a0246890908755
RUN python -c "import urllib.request,tarfile,io,os; \
d=urllib.request.urlopen('https://github.com/open-mmlab/OpenPCDet/archive/${OPENPCDET_REF}.tar.gz').read(); \
tarfile.open(fileobj=io.BytesIO(d)).extractall('/opt'); \
os.rename('/opt/OpenPCDet-${OPENPCDET_REF}', '/opt/OpenPCDet')" \
    && cd /opt/OpenPCDet && echo ${OPENPCDET_REF} > BUILD_COMMIT \
    && sed -i '/^av2/d;/^kornia/d;/^numpy/d;/^spconv/d' requirements.txt \
    && python setup.py develop


# nuscenes-devkit kéo opencv-python (cần libGL, không có vì không apt) ⇒ thay bằng bản headless
RUN pip uninstall -y opencv-python && pip install --force-reinstall --no-deps \
        "opencv-python-headless==4.9.0.80"

# Vá mã nguồn OpenPCDet cho môi trường này (không đổi thuật toán):
# - bỏ import cứng Argo2 (cần av2, nặng, không dùng)
# - alias numpy đã bị xoá: np.int / np.float / np.bool (KHÔNG chạm np.int32, np.float64, np.bool_)
COPY patch_pcdet.py /tmp/patch_pcdet.py
RUN python /tmp/patch_pcdet.py /opt/OpenPCDet && python -c "import pcdet.datasets"

WORKDIR /work
# worker/ được mount vào /work/worker khi chạy (không bake để code luôn mới nhất).
ENV PYTHONPATH=/work/worker:/opt/OpenPCDet
CMD ["bash"]

LABEL org.opencontainers.image.title="VCuboidFit_PointPillars" \
      org.opencontainers.image.version="0.1" \
      org.opencontainers.image.revision="${OPENPCDET_REF}"
