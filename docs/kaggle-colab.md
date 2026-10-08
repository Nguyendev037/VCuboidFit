# Chạy tạm trên Kaggle / Colab Pro

Dùng khi chưa thuê được máy GPU. Xem thêm [gpu-rental.md](gpu-rental.md) (bản đầy đủ trên máy thuê) và [run-local.md](run-local.md).

## 4. K · kế hoạch tạm Kaggle / Colab Pro

Không có Docker ⇒ cài OpenPCDet trực tiếp vào notebook rồi gọi đúng các module Python như trên
(`scripts/tier1.sh --no-docker`). Dùng **`--sweeps 1`** để chỉ cần keyframe (không cần ~240 GB
sweeps) — ghi rõ trong báo cáo và dùng cùng giá trị cho downstream.

| | Kaggle | Colab Pro / Pro+ |
|---|---|---|
| GPU | T4 ×2 (16 GB) — **không dùng P100** (sm_60 ngoài danh sách arch) | T4 / L4 / A100 tuỳ lượt |
| Thời lượng | 12 h/phiên, ~30 h GPU/tuần | ~24 h/phiên (Pro+), có thể bị ngắt |
| Đĩa | `/kaggle/working` 20 GB, input dataset riêng tư lớn hơn | ~100–200 GB tạm + Google Drive |
| Dữ liệu | upload keyframe LIDAR_TOP + meta thành Kaggle Dataset riêng tư | để trên Drive, copy vào `/content` |

**Notebook làm sẵn toàn bộ các bước dưới đây:** [`notebooks/vcf_tier01_kaggle_colab.ipynb`](../model/notebooks/vcf_tier01_kaggle_colab.ipynb).

**Ô lệnh chung** (Colab / Kaggle, CUDA 12.x có sẵn):
```bash
pip -q install spconv-cu120 "numpy<2" nuscenes-devkit easydict tensorboardX kornia==0.6.12 \
    scikit-learn joblib pyarrow pandas pyyaml opencv-python-headless
wget -qO pcdet.tgz https://github.com/open-mmlab/OpenPCDet/archive/233f849829b6ac19afb8af8837a0246890908755.tar.gz
tar xzf pcdet.tgz && mv OpenPCDet-233f849829b6ac19afb8af8837a0246890908755 OpenPCDet
echo 233f849829b6ac19afb8af8837a0246890908755 > OpenPCDet/BUILD_COMMIT   # train_seed đọc file này (Dockerfile tự ghi)
python vcf/docker/tier1/patch_pcdet.py OpenPCDet   # bỏ import Argo2 + alias np.int/np.float/np.bool
cd OpenPCDet && TORCH_CUDA_ARCH_LIST="7.5;8.0;8.6;8.9" python setup.py develop && cd ..
export PCDET_ROOT=$PWD/OpenPCDet PYTHONPATH=$PWD/vcf/worker:$PWD/OpenPCDet
python -m c4.cli.lidar_experiment --data-root $NUSC --out $EXP --split V --tune
bash vcf/scripts/tier1.sh $NUSC $EXP --no-docker --sweeps 1 --epochs 20 --batch 4
python -m c4.cli.lidar_experiment --data-root $NUSC --out $EXP --split V --tune
```
Lưu `$EXP` (nhất là `t1/ckpt`, `t1/*.pkl`, `features/`) ra Drive / Kaggle Output sau mỗi bước
để phiên bị ngắt không mất kết quả — mọi bước đều bỏ qua phần đã có.

**Thứ tự ưu tiên khi tài nguyên ít:** (1) Tầng 0 trainval trên CPU (Kaggle CPU cũng chạy được) →
(2) Tầng 1 với `--sweeps 1` → (3) downstream (stretch).

