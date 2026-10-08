# Dev mới: chạy model trên Google Colab (không cần GPU, không cần Docker)

Mở notebook, chạy lần lượt các ô là có môi trường chạy được Tầng 0 + Tầng 1.

[Open in Colab](https://colab.research.google.com/github/Nguyendev037/VCuboidFit/blob/main/model/notebooks/vcf_dev_setup_colab.ipynb)
(chọn Runtime > Change runtime type > GPU, T4 là đủ).

## Các ô và thời gian dự kiến
| Ô | Việc | Thời gian |
|---|---|---|
| 1 | Mount Google Drive, đặt `VCF_HOME=/content/drive/MyDrive/vcf` (giữ dữ liệu + bản build qua các phiên) | ~1 phút |
| 2 | Clone repo (hoặc `git pull`) | < 1 phút |
| 3 | `bash model/scripts/colab_setup.sh` (pip + build OpenPCDet) | 10-15 phút lần đầu, ~1 phút khi có cache |
| 4 | Smoke test `pytest -m "not perf and not gpu" tests/lidar` | 1-3 phút |
| 5 | (Tuỳ chọn) đặt nuScenes-mini vào Drive: tải tay từ nuscenes.org (cần tài khoản), giải nén vào `$VCF_HOME/nuscenes`. Không nhúng credential vào notebook | tuỳ mạng |
| 6 | Tầng 0 mini (CPU) | vài phút |
| 7 | Tầng 1 mini (`tier1.sh --no-docker --sweeps 1 --epochs 20 --batch 4`) | 20-60 phút trên T4 |
| 8 | Chế độ agent: nhận việc Tầng 1 từ worker máy yếu (xem [colab-agent](#chế-độ-agent)) | chạy liên tục |

Chạy script riêng (ngoài notebook): `bash model/scripts/colab_setup.sh [--cpu-only]`. `--cpu-only` bỏ bước
OpenPCDet, dùng cho máy không GPU chỉ chạy Tầng 0. Script idempotent: chạy lại in dòng `cache` và kết thúc bằng `SETUP OK`.

## Chế độ agent
Worker máy yếu bật `VCF_REMOTE_TOKEN`, mở tunnel (cloudflared) tới worker. Trên Colab, ô 8 hỏi URL tunnel + token
(`getpass`, không hiển thị) rồi chạy `model/scripts/colab_agent.py`: kéo việc, train + suy luận, đẩy `signals.parquet` về.
Thử không GPU: thêm `--dry-run`. Notebook chuyên cho agent: `model/notebooks/vcf_colab_agent.ipynb` (4 ô).

## Lỗi hay gặp
- **Hết quota GPU / không cấp được GPU**: đổi runtime sang CPU (chỉ chạy được Tầng 0, ô 1-6) hoặc thử lại sau vài giờ.
- **Phiên bị ngắt**: kết nối lại, chạy lại ô 1-3. Build OpenPCDet và dữ liệu nằm trong `VCF_HOME` trên Drive nên dùng cache.
- **`agent` báo 401**: sai token, agent dừng ngay (không retry). **404 remote_disabled**: worker chưa đặt `VCF_REMOTE_TOKEN`.
- **P100 (Kaggle)**: không dùng, sm_60 nằm ngoài danh sách arch đã build.
