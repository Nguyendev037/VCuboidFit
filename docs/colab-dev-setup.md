# Chạy VCuboidFIT trên Google Colab

Có 2 cách. **Cách 1** là cách chính: máy bạn chạy web, Colab chỉ làm phần nặng (Tầng 1, cần GPU).
Ngoài ra có notebook benchmark nghiên cứu và notebook huấn luyện PointPillars trainval lớn (>50 GB, A100) ở cuối tài liệu. T đã hoàn tất trên A100; đó là luồng riêng, không chứng minh cầu nối Tầng 1 từ xa đã đạt gate Colab thật. Không mở lại tập T để thử hướng dẫn này. [Số đo và gate còn lại](project-status.md).

Điều khiển notebook bằng agent qua MCP (hay nối nhầm notebook/tài khoản): xem [colab-mcp.md](colab-mcp.md).

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

## Huấn luyện PointPillars trainval lớn (>50 GB LiDAR, A100)

Notebook: [TrainModel.ipynb](../model/notebooks/TrainModel.ipynb) (File → Upload notebook trong Colab).
Tên hiển thị khi nhập là **TrainModel.ipynb**; đây là notebook huấn luyện chính thức của hồ sơ 16, dùng **Run all**.
Runtime yêu cầu **GPU A100 + High-RAM**, đĩa `/content` còn trống tối thiểu dung lượng source pack + 35 GB dự phòng.
Không đụng tập T cũ: toàn bộ 205 scene complete official TRAIN (8.182 keyframes, 10 sweeps, >50 GB LiDAR) được dùng để huấn luyện từ đầu; tập kiểm tra nội bộ là 15 scene complete official VAL ngoài pool cũ (602 keyframes). Các scene V/P cũ trong pool được xếp vào TRAIN, không gọi là holdout và không chuyển giao kết luận chẩn đoán.

- Huấn luyện PointPillars từ đầu (khởi tạo ngẫu nhiên, không checkpoint có sẵn, không `--init-ckpt`), 10 sweeps, 20 epochs, batch 8 (tự động hạ 4 rồi 2 nếu gặp lỗi CUDA OOM thực sự), 8 workers, `gt_sampling: False`.
- Script đóng gói và kiểm tra toàn vẹn metadata: `model/scripts/trainval_full.py` (CLI `pack`, `index`, `verify`).

Chuẩn bị gói dữ liệu và mã nguồn:
```powershell
python model/scripts/trainval_full.py pack --data-root E:/nuscenes_trainval `
  --pool-index model/workspace/jobs/pool_v24/lidar/index.parquet --out F:/vcf_pack/trainval_pp_v2
```
Chép toàn bộ thư mục `F:/vcf_pack/trainval_pp_v2/` (bao gồm các part `trainval_part_*.zip`, `code_trainmodel.zip` và `manifest.json`) vào `MyDrive/datatest/trainval_pp_v2/`.

Vận hành và khôi phục khi ngắt quãng (Resume):
- Thư mục làm việc cục bộ trong Colab: `/content/vcf_trainmodel` (mã nguồn giải nén tại `repo/`, dữ liệu tại `data/`, thí nghiệm tại `exp/`).
- Checkpoint được đồng bộ nguyên tử lên Drive mỗi 300 giây (`.part` rồi đổi tên, kèm `.sha256`), tự động giữ tối đa 2 bản checkpoint mới nhất trên Drive tại `MyDrive/vcf_results/<RUN_ID>/train/pcdet_output/`.
- Nếu ngắt runtime giữa chừng: kết nối lại A100 và chạy lại **Run all** với cùng `RUN_ID` (mặc định `trainmodel-full-20261014`); notebook tự động khôi phục checkpoint hợp lệ từ Drive và OpenPCDet tiếp tục huấn luyện từ epoch gần nhất.
- Kết quả hoàn tất lưu tại `MyDrive/vcf_results/<RUN_ID>/`: `manifest.json`, `parameters.json`, `seed/{seed_latest.pth,pp_seed.yaml,train_config.yaml,seed_tokens.txt,index.parquet}`, checkpoint mirror, logs và `SHA256SUMS.txt`.
- Lưu ý đánh giá: NuScenes devkit evaluation sau train trên tập heldout 15 scene có thể báo lỗi do devkit mặc định đòi đủ 150 scene VAL; checkpoint epoch 20 vẫn được nghiệm thu hoàn tất với `post_train_eval=failed` ghi nhận trung thực (SPEC-P01 §3). Không công bố mAP/NDS toàn bộ tập val chính thức từ tập con này.


Bẫy môi trường Colab đã gặp và đã vá trong notebook (lượt 2026-10-14):
- `dist-packages` của Colab có file `.gitignore` ⇒ `pccm` tưởng cumm là bản editable và tự JIT-build (lỗi thiếu `tensorview/pybind_utils.h`). Ô 4 đặt `CUMM_DISABLE_JIT=1`, `SPCONV_DISABLE_JIT=1` trước mọi import.
- Bước cài OpenPCDet kéo `numba`/`scikit-image` mới ⇒ numpy lên 2.x, nuscenes-devkit/spconv vỡ. Ô 4 ghim `numpy<2 numba==0.61.2 llvmlite==0.44.0`. Nếu kernel đã nạp numpy cũ (`numpy.dtype size changed` khi `import pandas`): khởi động lại kernel rồi chạy lại từ ô 1.
- Ô 5 đọc mỗi part trên Drive đúng **một lượt** (chép về `/content/_part_tmp` và băm SHA cùng lúc), giải nén từ đĩa local; part có marker `markers/part_<tên>` thì bỏ qua khi chạy lại.
- Khi dữ liệu đã giải nén (`markers/data_unpacked`), ô 1 chỉ đòi 35 GB trống thay vì source + 35 GB.

Thời gian đo trên A100-80GB (batch 8, 10 sweeps, CBGS): `create_info` ~10 phút; 4.327 iteration/epoch × ~0,71 s ≈ **51 phút/epoch**; VRAM ~27–36 GB. 20 epoch ≈ 17 giờ + chuẩn bị ~1 giờ.

Dừng sớm có chủ đích (ô **8b**): bấm ⏹ ô 8, đặt `STOP_EARLY=True` ở ô 8b rồi chạy 8b → 9 → 10. Ô 8b dừng tiến trình train, lấy checkpoint epoch mới nhất làm `seed_latest.pth` (qua `train_seed --init-ckpt`), ghi `epochs_trained` vào `run_identity.json`. Ô 10 gọi `runtime.unassign()` để ngừng tốn compute unit sau khi ô 9 đã xuất bản.

Kết quả lượt đầu (`RUN_ID=trainmodel-full-20261014`): dừng sớm ở **epoch 6/20** để kịp hạn; trọng số trong repo tại [`model/weights/pointpillars-trainval-e6/`](../model/weights/pointpillars-trainval-e6/) — chi tiết ở [model-workflow §9](model-workflow.md#9-trọng-số-pointpillars-trainval-epoch-6-trainmodel-2026-10-15).
