# Chạy VCuboidFIT trên Google Colab

Có 2 cách. **Cách 1** là cách chính: máy bạn chạy web, Colab chỉ làm phần nặng (Tầng 1, cần GPU).

| Cách | Dùng khi | Notebook |
|---|---|---|
| **1. Colab chạy Tầng 1 cho máy bạn** | Máy bạn chạy web + worker nhưng không có GPU | [vcf_colab_agent.ipynb](../model/notebooks/vcf_colab_agent.ipynb) |
| **2. Colab tự chạy từ ZIP** | Không chạy web, chỉ muốn danh sách 5 % từ file ZIP trên Drive | [vcf_dev_setup_colab.ipynb](../model/notebooks/vcf_dev_setup_colab.ipynb) |

## Cách 1 — Colab chạy Tầng 1 cho máy bạn

```text
Máy bạn: web :3000 + worker :8001 + cloudflared  ──https://<tên>.trycloudflare.com──►  Colab (GPU T4)
```

### Bước 1 — Máy bạn: MỘT lệnh

Bật Docker Desktop, rồi ở thư mục gốc repo (PowerShell):
```powershell
powershell -ExecutionPolicy Bypass -File .\model\scripts\colab_bridge.ps1
```
Script tự làm hết: tải `cloudflared` (không cần cài), tạo TOKEN, khởi động lại worker có token, mở tunnel,
rồi in ra và chép sẵn vào clipboard:
```text
SERVER_URL = https://<tên-ngẫu-nhiên>.trycloudflare.com
TOKEN      = <chuỗi dài>
```
- Worker chạy bằng Python thay vì Docker: thêm `-Python`.
- Tắt tunnel: `powershell -ExecutionPolicy Bypass -File .\model\scripts\colab_bridge.ps1 -Stop`.
- Chạy web như thường ở cửa sổ khác: `cd web; npm run dev` ([getting-started.md](getting-started.md)).
- Mỗi lần chạy lại script, URL đổi → dán lại vào Colab.

### Bước 2 — Colab: điền 2 ô rồi Run all

1. Mở [vcf_colab_agent.ipynb trên Colab](https://colab.research.google.com/github/Nguyendev037/VCuboidFit/blob/main/model/notebooks/vcf_colab_agent.ipynb)
   (notebook đã đặt sẵn GPU T4).
2. Ô **1**: dán `SERVER_URL` (URL ở bước 1) và `TOKEN`.
3. **Runtime → Run all.**
   - Ô 2 kiểm GPU, URL, token trong vài giây — sai là dừng ngay kèm lời nhắn cách sửa.
   - Ô 3 cài môi trường: lần đầu mỗi phiên ~10–15 phút, kết thúc bằng `SETUP OK` / `✅ Cài xong`.
   - Ô 4 chạy liên tục, chờ việc.

### Bước 3 — Web: giao việc

Mở lần chạy trên web → **Tham số nâng cao** → **"Chạy Tầng 1 trên Colab"**. Log ô 4:

| Log | Nghĩa |
|---|---|
| `khong co viec` | Đang chờ (chưa bấm nút trên web) |
| `nhan viec t1_...` | Đã nhận việc |
| `cache miss: da tai data/` | Đang tải dữ liệu từ máy bạn qua tunnel (lần đầu có thể lâu) |
| `da gui ket qua t1_...` | **Xong** — web tự mở khoá Tầng 1 |

Dừng: bấm ■ ở ô 4. Tắt cầu nối: đóng cloudflared, chạy lại worker không có `VCF_REMOTE_TOKEN`.
URL tunnel là công khai, token là lớp bảo vệ duy nhất — đừng chia sẻ token.

### Lỗi hay gặp (Cách 1)

| Ô báo | Sửa |
|---|---|
| `SERVER_URL chưa đúng` | Dán đúng dòng `SERVER_URL` do `colab_bridge.ps1` in ra, không dán ví dụ `xxxx` |
| `Chưa có GPU` | Runtime → Change runtime type → T4 GPU → Save, Run all lại |
| `Không gọi được ...` | Tunnel đã tắt hoặc URL đổi: chạy lại `colab_bridge.ps1`, dán URL mới |
| `Sai TOKEN` | TOKEN phải trùng `VCF_REMOTE_TOKEN` lúc khởi động worker |
| `Worker chưa bật cầu nối` | Chạy lại `colab_bridge.ps1` (nó khởi động lại worker có token) |
| `Lỗi khi chạy: bash .../colab_setup.sh` | Xem log ngay trên; chạy lại ô 3 (đã cài phần nào thì bỏ qua phần đó) |
| Không thấy nút "Chạy Tầng 1 trên Colab" | Worker chưa có token, hoặc lần chạy đã có Tầng 1 |
| Hết quota GPU Colab | Thử lại sau vài giờ |

## Cách 2 — Colab tự chạy từ ZIP trên Drive (không cần máy bạn)

Notebook: [vcf_dev_setup_colab.ipynb](../model/notebooks/vcf_dev_setup_colab.ipynb)
([Open in Colab](https://colab.research.google.com/github/Nguyendev037/VCuboidFit/blob/main/model/notebooks/vcf_dev_setup_colab.ipynb)).

### Chuẩn bị

Đặt các ZIP tại **MyDrive/datatest/**. Chỉ để các phần của **cùng một bộ nuScenes**:
bảng JSON trong `v1.0-*`, point cloud trong `samples/LIDAR_TOP/`.
Chấp nhận ZIP chứa trực tiếp các thư mục trên hoặc có lớp bọc `data/`, thư mục bao ngoài.
Không cần manifest, camera hay nhãn để chọn frame. ZIP khác định dạng nuScenes cần chuyển đổi trước.

### Chạy 4 ô

1. **Kết nối Drive**: cấp quyền Drive. Mặc định `/content/drive/MyDrive/datatest`;
   folder ở chỗ khác thì sửa `DATA_FOLDER` trong ô 1.
2. **Cài CPU**: tự clone repo, cài engine. Thấy **SETUP OK** thì tiếp tục.
3. **Đọc ZIP**: tự giải nén vào ổ tạm Colab, gộp dữ liệu, kiểm tra bảng JSON và LiDAR.
   Thấy **DATA OK** kèm số ZIP/scene/keyframe thì tiếp tục. Giữ nguyên ZIP trên Drive.
4. **Chọn 5%**: chạy Tầng 0 trên toàn bộ keyframe bộ test, lưu vào
   `MyDrive/vcf_results/<lần-chạy>/tier0/`. Thấy **XONG** kèm số frame và đường dẫn.

Runtime CPU mặc định là đủ. Luồng này không dùng Kaggle, Cloudflare, Docker, token,
worker máy cá nhân hay website. Phiên mới chạy lại 4 ô. Mỗi lần đọc ZIP tạo thư mục chạy riêng
để tránh cache cũ. Dữ liệu giải nén mất khi Colab ngắt phiên; kết quả đã lưu trên Drive vẫn còn.

### Kết quả

| File | Nội dung |
|---|---|
| `selected_5pct.csv` | Frame được chọn bởi hybrid, đúng ngân sách |
| `result.json` | Tham số, thông tin lựa chọn, cảnh báo và phân tích |
| `selected.csv` | Kết quả các phương pháp so sánh, không chỉ danh sách 5% |
| `scores.parquet` | Điểm từng frame |
| `results.zip` | Gói result.json, selected.csv, scores.parquet |

Tầng 0 dùng độ hiếm hình học và đa dạng. Notebook không tune, không chấm P, không tạo metric nhãn.
Ngân sách làm tròn và số frame hợp lệ có thể khiến số chọn khác đúng 5%.

### GPU tùy chọn

Đã có kết quả sau ô 4. Chỉ chạy ô cuối nếu muốn train PointPillars: đổi runtime sang T4 GPU,
chạy lại ô 1–4 nếu runtime khởi động lại, đặt `RUN_GPU = True` ở ô cuối. Mặc định GPU tắt nên **Run all** vẫn chỉ chạy CPU. Ô GPU kiểm tra scene seed S theo cấu hình nuScenes,
cài/build môi trường, train 20 epoch rồi suy luận, lưu kết quả ở `tier1/`.
Không có scene seed S thì dừng và giữ kết quả CPU. GPU tùy runtime; chưa kiểm trên Colab/GPU thật.

### Lỗi thường gặp

| Lỗi | Cách xử lý |
|---|---|
| Không thấy datatest | Kiểm tra MyDrive hoặc sửa DATA_FOLDER |
| Không có .zip | Đặt ZIP trực tiếp trong folder, không trong folder con |
| ZIP hỏng / đường dẫn không hợp lệ | Thay ZIP lỗi, chạy lại ô 3 |
| File trùng nhưng nội dung khác | Tách dataset khác nhau sang folder riêng |
| Thiếu JSON / LiDAR | Bổ sung ZIP metadata và point cloud của cùng bộ nuScenes |
| Không đủ 2 frame hợp lệ | Kiểm .bin và ngưỡng tối thiểu 2.000 điểm trong cấu hình LiDAR |
| Hết ổ tạm Colab | Dùng bộ test nhỏ hơn, bắt đầu phiên mới |
| Cài đặt lỗi | Xem lỗi ô 2; lệnh lỗi sẽ dừng ngay |
