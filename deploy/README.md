# Deploy VCuboidFIT

Nơi tập trung mọi tài liệu về quy trình deploy. Cập nhật **15/10/2026** · phiên bản cấu hình **0.11.0**.

## Hiện trạng

| Môi trường | Trạng thái | Tài liệu |
|---|---|---|
| Local (Windows, web 3000 + worker 8001) | ✅ Đang dùng cho dev và demo | [run-local](../docs/run-local.md), [getting-started](../docs/getting-started.md) |
| Docker worker (Tầng 0, CPU) | ✅ Có image và compose | [model/docker/worker](../model/docker/worker/docker-compose.yml) |
| GPU thuê theo đợt (Tầng 1 PointPillars) | ✅ Có gói `pack.sh` / `bootstrap.sh` | [gpu-rental](../docs/gpu-rental.md) |
| Google Colab | ✅ Benchmark T đã chạy trên A100 | [colab-dev-setup](../docs/colab-dev-setup.md) |
| CI (GitHub Actions) | ⬜ Chưa có | — |
| Image web Next.js | ⬜ Chưa có Dockerfile | — |
| Cloud Azure Lite | 🟠 Đã có image/profile/runbook, chưa chạy Azure | [azure/README](azure/README.md), [azure-media-storage](azure-media-storage.md) |

## Lưu ý đang mở

- [azure-media-storage.md](azure-media-storage.md): đã chốt lưu dữ liệu đủ trong phiên và xoá khi kết thúc/TTL 24 giờ (hồ sơ 20, D11).

## Quy ước

- File mới về deploy đặt trong thư mục này; tài liệu chạy local vẫn ở `docs/`.
- Ghi rõ trạng thái theo môi trường (`✅ local / ⬜ cloud`); chưa đo thì ghi "chưa đo", không ghi ước lượng thành số thật.
