# Chạy VCuboidFIT trên Google Colab

Có 2 cách. **Cách 1** là cách chính: máy bạn chạy web, Colab chỉ làm phần nặng (Tầng 1, cần GPU).
Ngoài ra có notebook benchmark nghiên cứu và notebook seed PointPillars trainval (chẩn đoán trên V) ở cuối tài liệu. T đã hoàn tất trên A100; đó là luồng riêng, không chứng minh cầu nối Tầng 1 từ xa đã đạt gate Colab thật. Không mở lại tập T để thử hướng dẫn này. [Số đo và gate còn lại](project-status.md).

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
   - Ô 3 cài môi trường: thời gian tham khảo lần đầu ~10–15 phút, phụ thuộc runtime/mạng; kết thúc bằng `SETUP OK` / `✅ Cài xong`.
   - Ô 4 chạy liên tục, chờ việc.

**Không cần train:** mặc định Colab dùng **trọng số PointPillars có sẵn** (80 epoch, seed nuScenes-mini) thay vì
train lại — một lượt còn tải dữ liệu + suy luận. Các khoảng ~7–20 phút / ~20–35 phút có train là tham khảo vận hành, không phải thời gian benchmark T hoặc SLA. Thứ tự lấy trọng số:
1. Worker gửi kèm việc nếu máy bạn có thí nghiệm riêng (`VCF_T1_EXP`, hoặc tự dò trong `model/workspace/experiments`).
2. Không có thì tải bản mặc định trên GitHub (Git LFS, ~70 MB, kiểm sha256, cache trong phiên).

Muốn train lại trên Colab (vd dữ liệu trainval mới): ở ô 4 thêm `"--train"` vào danh sách lệnh của `colab_agent.py`.
Dữ liệu khác hẳn mini (trainval) nên train lại một lần rồi đặt thí nghiệm đó làm `VCF_T1_EXP` cho các lần sau.

### Bước 3 — Web: giao việc

Mở lần chạy trên web → **Tham số nâng cao** → **"Chạy Tầng 1 trên Colab"**. Log ô 4:

| Log | Nghĩa |
|---|---|
| `khong co viec` | Đang chờ (chưa bấm nút trên web) |
| `nhan viec t1_...` | Đã nhận việc |
| `cache miss: da tai data/` | Đang tải dữ liệu từ máy bạn qua tunnel (lần đầu có thể lâu) |
| `da tai trong so seed tu GitHub` / `tu worker` | Đã có trọng số, bước train sẽ bỏ qua (`dùng trọng số có sẵn ... bỏ qua train`) |
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
Không có scene seed S thì dừng và giữ kết quả CPU. GPU tùy runtime; gate chạy ô GPU này trên Colab thật chưa được xác nhận, khác với benchmark A100 đã hoàn tất.

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

## Benchmark pitching

Notebook: [vcf_bench_pitch_colab.ipynb](../model/notebooks/vcf_bench_pitch_colab.ipynb).
Dùng runtime **A100**, chạy từng ô; mini chỉ minh hoạ in-sample, pool là bảng chính riêng biệt.
Không train PointPillars, không VLM, không dùng sweeps; ứng viên `cluster_only`.

Từ root sản phẩm, đóng gói thật bằng:
```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File model/scripts/pack_pool_colab.ps1
```
Nguồn `E:/nuscenes_trainval` chỉ đọc. Script lấy đúng 6.753 keyframe từ job `pool_v24`,
6 camera mỗi keyframe, toàn bộ `v1.0-trainval/` và `maps/`; chia ZIP độc lập ≤ 2 GB,
kiểm CRC và ghi số file/SHA-256 từng part vào `manifest.json`. Đầu ra mặc định
`F:/vcf_pack/pool_v24/`, không có ZIP tạm trong repo. Script dừng nếu code ZIP đã tồn tại;
để tái đóng gói sau commit H10, dùng `-OutDir F:/vcf_pack/pool_v24/<sha-moi>`.

Chuẩn bị Drive:
1. Chép `manifest.json` và tất cả `vcf_part_*.zip` vào `MyDrive/vcf_pack/pool_v24/`.
2. Chép `code_<sha>.zip` vào `MyDrive/vcf_pack/`. ZIP là `git archive HEAD`, không chứa thay đổi chưa commit.
3. Bộ mini đủ 404 keyframe và 6 camera phải có manifest vcf-pack tại
   `MyDrive/datatest/vcf_manifest.json`. Nếu khác chỗ, sửa `MINI_DATA_ZIP`.
4. Upload notebook trực tiếp vào Colab; sửa `REPO_SHA` bằng `repo_sha` trong manifest,
   sửa `DATA_ZIP`/`CODE_ZIP` nếu dùng thư mục khác. Notebook kiểm cả SHA Git archive và checksum.

Code ZIP phải chứa CLI `c4.cli.bench_pitch` và các đầu vào đóng băng mà CLI yêu cầu; kiểm `--help` trong chính ZIP/môi trường sẽ chạy. Code hiện tại đã có CLI này; gói K1 lịch sử `f4a2abf` chưa có và không dùng để tái lập T. Giữ code SHA của phép thử gốc cùng prereg/final config; không lấy HEAD mới để thay code thử nghiệm cũ.

Notebook ghép cây `data/` của các ZIP sau khi kiểm SHA, kiểm prereg `pitch-v2`,
chạy `lidar_index`, `lidar_t0`, `extract_clip`, `context cv/fit/run`, `rare run lidar_only`,
`rare crops`, `rare run multisensor`, rồi benchmark mini. Pool chạy cùng chuỗi chuẩn bị
nhưng dừng trước `bench_pitch --mode pool`.

`RUN_T = False` mặc định. Chỉ bật tay **một lần** sau khi người duyệt xem mini/cấu hình đóng băng.
Cổng quét `report_pitch.json` mode pool trên Drive và marker `pitch-v2-T-opened.json`;
marker ghi trước lệnh và giữ cả khi lỗi/ngắt phiên. Không xoá marker để thử lại.
Exit 2/3: dừng và gửi log cho người duyệt, không sửa prereg hay tự mở lại T.

Kết quả và log lưu ngay tại `MyDrive/vcf_results/<run_id>/`: `timing.json`, prereg,
log từng CLI, hai thư mục `mini/` và `pool/` riêng, cùng bản sao job.
VRAM là đỉnh bộ nhớ GPU toàn thiết bị qua `nvidia-smi`, lấy mẫu 1 giây;
không phải peak allocator riêng của PyTorch. Lượt T thực tế có tổng thời gian 1.236 s; chỉ báo VRAM nếu evidence chứa số đo thiết bị tương ứng. Nguồn và phạm vi ở [project-status](project-status.md).

## Seed PointPillars trên trainval + chẩn đoán trên V

Notebook: [vcf_night_pp_trainval.ipynb](../model/notebooks/vcf_night_pp_trainval.ipynb) · script
[colab_pp_night.py](../model/scripts/colab_pp_night.py). Runtime **A100 + High-RAM**, **Run all**.
Không đụng T: không có `bench_pitch --mode pool`, `diag --split T` thoát mã 3. Kết quả V là **chẩn đoán**
(tham chiếu fit và chấm cùng trên V), không thay prereg `pitch-v2`.

- Train seed từ đầu trên S của pool (7 scene, 279 keyframe) + 70 scene TRAIN chính thức ngoài pool
  (`scene-1007…1110`, 2.818 keyframe, Singapore đêm). Không bao giờ V, T, P hoặc scene VAL. `sweeps = 1` vì các gói
  không có sweeps (đủ sweeps cần thêm ~58 GB).
- Suy luận trên mọi frame của job pool (không đọc nhãn), rồi `rare_v24` trên V: A `cluster_only` lidar_only,
  B `cluster+pp` lidar_only, C `cluster+pp` multisensor (+A2 tuỳ chọn). Đo IY@B capture B, reach 1 m, bootstrap cụm scene.

Chuẩn bị (sau khi commit, vì code ZIP = `git archive HEAD`; lệnh từ chối cây chưa commit):
```powershell
model\worker\.venv\Scripts\python.exe model\scripts\colab_pp_night.py pack-seed --data-root E:/nuscenes_trainval `
  --pool-index model/workspace/jobs/pool_v24/lidar/index.parquet --out F:/vcf_pack/seed_pp_v1 --code
```
Chép cả thư mục `F:/vcf_pack/seed_pp_v1/` vào `MyDrive/datatest/seed_pp_v1/`. Gói pool cũ (`pool_v24`) được tìm ở
`MyDrive/datatest/pool_v24`, `MyDrive/vcf_pack/pool_v24` hoặc `MyDrive/pool_v24`. Notebook đọc `repo_sha` từ
manifest gói seed — không cần sửa tay.

Ngắt runtime: kết nối lại A100 và **Run all** với cùng `RUN_ID`; bước đã lưu trên Drive được bỏ qua, checkpoint giữa
chừng được đồng bộ mỗi 5 phút. Kết quả ở `MyDrive/vcf_results/<RUN_ID>/` (`diag/diag_table.md`, `seed/seed_latest.pth`
kèm `.sha256`, `SHA256SUMS.txt`). Checkpoint chỉ để trong Drive riêng, không chia sẻ công khai.
Thời gian dự kiến là **ước tính** 2,2–4,2 giờ (train chiếm phần lớn); chi tiết từng ô, điểm cần người quyết và
rollback nằm trong hồ sơ kế hoạch 15 của workspace quản trị (`planning/15_2026-10-14_colab-pp-trainval/`).
