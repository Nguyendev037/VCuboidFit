# Chạy VCuboidFIT với Google Colab — hướng dẫn từng bước

Tài liệu này dành cho người mới clone repo. Đọc mục 1 để chọn đúng cách chạy, rồi làm theo
từng bước của cách đó. Mỗi bước có **kết quả đúng** để tự kiểm trước khi sang bước sau.

## 1. Chọn cách chạy

| Cách | Khi nào dùng | Máy cần có |
|---|---|---|
| **A. Chỉ Colab** | Thử môi trường, chạy Tầng 0 + Tầng 1 trên nuScenes-mini, không cần web | Tài khoản Google, tài khoản nuScenes (để tải dữ liệu) |
| **B. Máy bạn + Colab (chế độ agent)** | Dùng website trên máy bạn (máy không có GPU), nhờ GPU của Colab chạy Tầng 1 rồi tự gửi kết quả về | Máy Windows chạy được worker + web ([run-local.md](run-local.md)), `cloudflared`, tài khoản Google |

Hai cách dùng chung notebook [`model/notebooks/colab_dev_setup.ipynb`](../model/notebooks/colab_dev_setup.ipynb):
[Open in Colab](https://colab.research.google.com/github/Nguyendev037/VCuboidFit/blob/main/model/notebooks/colab_dev_setup.ipynb).
Cách A chạy ô 1–7; cách B chạy ô 1–3 rồi nhảy thẳng tới ô 8.

**Phiên bản:** máy bạn và Colab phải cùng phiên bản repo (≥ 0.6.1). Trước khi làm, `git pull` ở máy bạn;
trên Colab ô 2 tự `git pull`.

## 2. Chuẩn bị chung trên Colab (ô 1–3)

1. Mở link "Open in Colab" ở trên. Vào **Runtime → Change runtime type → T4 GPU → Save**.
2. **Ô 1** — bấm chạy, cho phép truy cập Google Drive.
   Kết quả đúng: `Mounted at /content/drive`. Thư mục `MyDrive/vcf` được tạo (giữ cache qua các phiên).
3. **Ô 2** — clone repo về `/content/VCuboidFit` (lần sau tự `git pull`).
4. **Ô 3** — cài môi trường (pip + build OpenPCDet). Lần đầu 10–15 phút, các lần sau ~1 phút nhờ cache trên Drive.
   Kết quả đúng: dòng cuối là **`SETUP OK`**. Không thấy dòng này thì đọc lỗi phía trên và xem mục 6.

## 3. Cách A — chỉ Colab (ô 4–7)

1. **Ô 4** — smoke test. Kết quả đúng: `... passed` và không có `failed`.
2. **Ô 5** — dữ liệu. Tải **nuScenes-mini** (`v1.0-mini.tgz`) từ <https://www.nuscenes.org/download>
   (cần đăng ký tài khoản), giải nén lên Drive tại `MyDrive/vcf/nuscenes/` sao cho có
   `MyDrive/vcf/nuscenes/v1.0-mini/` và `MyDrive/vcf/nuscenes/samples/`. Chạy ô 5.
   Kết quả đúng: `tồn tại: True`.
3. **Ô 6** — Tầng 0 (CPU, vài phút). Kết quả nằm ở `MyDrive/vcf/exp/V/report_selection.md`.
4. **Ô 7** — Tầng 1 (GPU, 20–60 phút trên T4). Nếu ô 5 báo `tồn tại: False`, ô 7 in
   "Bỏ qua Ô 7…" — đó là đúng, không phải lỗi: chưa có dữ liệu thì chưa chạy được Tầng 1.

## 4. Cách B — máy bạn + Colab (chế độ agent)

Có **hai máy**, làm theo đúng thứ tự:

```text
Máy bạn (Windows): worker :8001 + web :3000 + cloudflared ──(https://<tên-ngẫu-nhiên>.trycloudflare.com)──► Colab (GPU, ô 8)
```

### 4.1. Máy bạn — cài cloudflared (một lần)

```powershell
winget install --id Cloudflare.cloudflared
cloudflared --version        # kết quả đúng: in ra "cloudflared version ..."
```
Không có `winget`: tải `cloudflared-windows-amd64.exe` ở
<https://github.com/cloudflare/cloudflared/releases>, đổi tên thành `cloudflared.exe`, đặt vào thư mục có trong `PATH`.

### 4.2. Máy bạn — tạo token và chạy worker CÓ token

Mở **PowerShell số 1** ở thư mục gốc repo:

```powershell
python -c "import secrets;print(secrets.token_urlsafe(32))"
# -> in ra một chuỗi dài, ví dụ  q3V...xYz  (đây là TOKEN; lưu lại, chút nữa dán vào Colab)
$env:VCF_REMOTE_TOKEN = "<dán TOKEN vừa in>"
$env:VCF_PORT = "8001"
$env:WORKSPACE = "$PWD\model\workspace"
cd model\worker
.venv\Scripts\python -m uvicorn service.main:create_app --factory --port 8001
```
- Token phải đặt **trước** khi khởi động worker, và **cùng cửa sổ** PowerShell đó. Worker đang chạy sẵn
  mà không có token thì tắt (Ctrl+C) rồi chạy lại đúng các lệnh trên.
- Chưa có `.venv`: làm mục 1 của [run-local.md](run-local.md) trước.

Kiểm (PowerShell khác, KHÔNG kèm token để không nhận mất việc): `curl.exe http://127.0.0.1:8001/remote/t1/next`
→ đúng là ra `unauthorized` (worker đã bật cầu nối, đang đòi token). Ra `remote_disabled` nghĩa là worker chưa nhận token, làm lại bước trên.

### 4.3. Máy bạn — chạy web

**PowerShell số 2**: `cd web ; npm run dev` → mở <http://localhost:3000>, nạp dữ liệu và chạy phân tích
như bình thường ([run-local.md](run-local.md) mục 2–3).

### 4.4. Máy bạn — mở tunnel và LẤY URL THẬT

**PowerShell số 3**:
```powershell
cloudflared tunnel --url http://127.0.0.1:8001
```
Đợi vài giây, trong output có một khung như sau:
```text
+--------------------------------------------------------------------------------------------+
|  Your quick Tunnel has been created! Visit it at (it may take some time to be reachable):  |
|  https://bright-river-lamp-quiet.trycloudflare.com                                         |
+--------------------------------------------------------------------------------------------+
```
- Dòng `https://….trycloudflare.com` **trong khung đó** chính là URL cần dán vào Colab. Tên là ngẫu nhiên và
  **đổi mỗi lần** chạy lại cloudflared.
- **KHÔNG** dán `https://xxxx.trycloudflare.com` — đó chỉ là ví dụ trong tài liệu, không tồn tại.
- Giữ cửa sổ này mở suốt lúc Colab làm việc; đóng nó là Colab mất kết nối.

Kiểm (trình duyệt hoặc PowerShell): mở `https://<URL vừa lấy>/health` → thấy `{"ok":true,...}`.
Mới tạo tunnel có thể mất 10–30 giây mới truy cập được.

### 4.5. Máy bạn — tạo việc trên web

Trên web, mở job đã phân tích → **Tham số nâng cao** → bấm **"Chạy Tầng 1 trên Colab"**.
Nút chỉ hiện khi worker có token (bước 4.2) và job chưa có Tầng 1. Bấm xong, job chờ Colab nhận việc.

### 4.6. Colab — ô 8 (chế độ agent)

Đã chạy ô 1–3 (mục 2). Chạy **ô 8**:
1. Ô hỏi `URL tunnel của worker` → dán URL thật ở bước 4.4 (dạng `https://<tên>.trycloudflare.com`, không có `/` cuối).
2. Ô hỏi `VCF_REMOTE_TOKEN` → dán TOKEN ở bước 4.2 (gõ/dán sẽ **không hiện ký tự**, đó là bình thường) → Enter.
3. Ô 8 tự kiểm `/health`. URL sai/tunnel chưa sẵn sàng thì nó báo ngay và dừng — sửa rồi chạy lại ô 8.

Log đúng khi chạy (giờ:phút:giây ở đầu dòng):
```text
khong co viec                                  # chưa có việc: chờ, cứ 60 s hỏi lại (bước 4.5 chưa bấm)
nhan viec t1_xxxxxxxxxxxx (job ..., epochs=..)  # đã nhận việc
cache miss: da tai data/ cho dataset ...        # lần đầu tải dữ liệu từ máy bạn qua tunnel (có thể lâu)
chay: ... train_seed ... / infer_t1 ...         # đang train + suy luận trên GPU
da gui ket qua t1_xxxxxxxxxxxx                  # xong: kết quả đã về máy bạn
```
Khi thấy `da gui ket qua`, quay lại web: panel tham số tự mở khoá **Tầng 1**. Ô 8 tiếp tục chờ việc mới;
muốn dừng bấm nút ■ (Interrupt) của ô.

### 4.7. Tắt cầu nối

Đóng cửa sổ cloudflared (Ctrl+C), tắt worker và chạy lại không có `VCF_REMOTE_TOKEN`. Khi đó mọi `/remote/*` trả 404.
URL quick tunnel là công khai, **token là lớp bảo vệ duy nhất** — không chia sẻ token, chỉ bật cầu nối khi cần.

## 5. Tham số cho người vận hành

| Biến (đặt ở máy chạy worker) | Mặc định | Ý nghĩa |
|---|---|---|
| `VCF_REMOTE_TOKEN` | rỗng = tắt | Bật cầu nối Colab; Colab phải gửi đúng token |
| `VCF_REMOTE_LEASE_SEC` | `5400` | Thời gian Colab được giữ một việc; quá hạn mà không gửi heartbeat thì việc về hàng đợi |
| `VCF_REMOTE_MAX_RESULT_MB` | `200` | Dung lượng tối đa của kết quả Colab gửi về |
| `VCF_PORT` | `8001` | Cổng worker; tunnel phải trỏ đúng cổng này |

Chạy agent ngoài notebook: `python model/scripts/colab_agent.py --server <URL> --work /content/vcf [--once] [--dry-run]`
(token lấy từ biến `VCF_REMOTE_TOKEN`). `--dry-run` không cần GPU, ghi kết quả giả để thử đường truyền.
Chi tiết giao thức (leaseId, `X-Lease-Id`, mã lỗi 409/411/413): [run-local.md](run-local.md) mục 5c.

## 6. Lỗi hay gặp

| Triệu chứng | Nguyên nhân | Cách sửa |
|---|---|---|
| Ô 8 báo không kết nối được / `khong ket noi duoc worker` | URL sai (dán ví dụ `xxxx`), có `/` hoặc khoảng trắng thừa, cloudflared đã tắt hoặc vừa chạy lại (URL đổi) | Lấy lại URL trong khung của cloudflared (bước 4.4), mở `<URL>/health` thử trước |
| `token bi tu choi (401)` | Token Colab khác token worker | Dán lại đúng token; token đổi thì phải khởi động lại worker với token mới |
| `worker chua bat VCF_REMOTE_TOKEN` | Worker chạy mà không có token | Làm lại bước 4.2 (đặt token rồi mới chạy worker, cùng cửa sổ) |
| Ô 8 chỉ in `khong co viec` mãi | Chưa bấm "Chạy Tầng 1 trên Colab" trên web | Làm bước 4.5 |
| Không thấy nút "Chạy Tầng 1 trên Colab" | Worker không có token, hoặc job đã có Tầng 1 | Kiểm bước 4.2; job đã có Tầng 1 thì không cần |
| `tier1.sh: cd: .../nuscenes: No such file or directory` | Chạy Tầng 1 trực tiếp (cách A) mà chưa có nuScenes trên Drive | Làm ô 5 của cách A, hoặc dùng cách B (ô 8 tự lấy dữ liệu từ máy bạn) |
| Ô 3 không in `SETUP OK` | Lỗi cài đặt / runtime không có GPU | Kiểm Runtime là T4 GPU; chạy lại ô 3 (dùng cache). Chỉ cần Tầng 0: `bash model/scripts/colab_setup.sh --cpu-only` |
| Hết quota GPU | Colab giới hạn GPU miễn phí | Đổi runtime CPU (chỉ Tầng 0, ô 1–6) hoặc thử lại sau vài giờ |
| Phiên Colab bị ngắt | Hết thời gian / mất mạng | Chạy lại ô 1–3 rồi ô cần dùng; việc đang dở tự về hàng đợi khi hết lease |
| `lease_mismatch` / `not_leased` trong log | Việc đã hết hạn và được giao lại | Không cần làm gì, agent tự bỏ việc cũ và nhận việc mới |
| P100 (Kaggle) | sm_60 nằm ngoài danh sách arch đã build | Dùng T4 |
