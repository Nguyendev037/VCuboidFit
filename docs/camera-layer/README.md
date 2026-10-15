# Tầng camera và cơ chế chấm điểm S

Tài liệu kỹ thuật cho engine `rare_v24`, dữ liệu nuScenes (LiDAR_TOP + 6 camera), không dùng VLM/LLM. Cập nhật 16/10/2026.

Nguồn chân lý là code: [`model/worker/c4/rare/`](../../model/worker/c4/rare/) (chấm điểm, chọn lô, đánh giá) và [`model/worker/c4/context/`](../../model/worker/c4/context/) (tầng camera). Mọi công thức dưới đây đã đối chiếu với code.

Đi kèm trong thư mục này:

| File | Nội dung |
|---|---|
| [`report.pdf`](report.pdf) | Báo cáo kỹ thuật 10 trang (bản in của `report.html`) |
| [`report.html`](report.html) | Nguồn HTML của báo cáo, mở bằng trình duyệt hoặc in lại ra PDF |
| [`slides.html`](slides.html) | Bộ 14 slide thuyết trình (1920 × 1080), kèm ghi chú người nói dưới mỗi slide |

## Đọc nhanh: điểm S là gì

1. **Chấm từng vật** LiDAR đề xuất: hình dạng lạ, rơi vào ô khoảng cách/số điểm hiếm, có phải VRU, model có lưỡng lự không. Ra `s_obj` trong [0, 1].
2. **Chấm frame**: lấy vật điểm cao nhất, cộng mức đông VRU và bối cảnh xấu (đêm, mưa, sương). Ra điểm thô `raw`.
3. **Xếp hạng**: đổi `raw` sang hạng phần trăm trong các frame hợp lệ của chính job đó. Đó là S (`s_frame`). S = 0,90 nghĩa là "cao hơn 90 % frame hợp lệ", không phải "90 % khả năng hiếm".
4. **Chọn lô** B frame (thường 5 % pool): không lấy thẳng top-S mà dùng MMR để vừa ưu tiên S cao vừa tránh frame trùng, phạt frame lặp cùng track, chia đều theo scene.

Không bước nào đọc nhãn. Nhãn chỉ được đọc ở bước đánh giá cuối (`eval.py`) để đo lô đã chọn bắt được bao nhiêu vật hiếm thật.

---

## 1. Vị trí của tầng camera

VCuboidFIT chọn keyframe LiDAR đáng gán nhãn cho bài toán phát hiện người đi bộ, xe đạp, xe máy (VRU) phục vụ phanh khẩn cấp (AEB). Hệ thống chọn một lô theo ngân sách; người duyệt xem lý do chọn, point cloud, hộp 3D và 6 camera rồi xuất ZIP.

Camera không phải pipeline chính và không tự gán nhãn. Nó chỉ chạy khi chọn engine `rare_v24` với profile `multisensor`, và góp hai tín hiệu:

- (a) **bối cảnh frame**: đêm, chói, ống kính bẩn/mờ, mưa/sương;
- (b) **khái niệm ngữ nghĩa** của vật VRU mà LiDAR đã đề xuất (xe lăn, trẻ em, người nằm…).

Profile `lidar_only` và engine `c4_legacy` không dùng camera để chấm.

## 2. Hai công cụ đọc ảnh: OpenCV và OpenCLIP

| | OpenCV | OpenCLIP |
|---|---|---|
| Câu hỏi trả lời | Ảnh sáng, chói, mờ đến đâu? (vật lý) | Ảnh trông giống câu mô tả nào? (ngữ nghĩa) |
| Cách làm | Phép tính xác định trên pixel, không học máy | Mô hình ảnh–ngôn ngữ học sẵn, so ảnh với câu mô tả |
| Phần cứng | CPU, đa luồng | GPU một lần để tính embedding, cache, sau đó CPU |
| Đầu ra | 13 đặc trưng → 4 cờ chất lượng | 4 trục bối cảnh + 12 khái niệm VRU |

Hai bên bổ sung nhau. Ở bước ghép (C3), hai bên "bỏ phiếu": đồng ý thì gắn thẻ, mâu thuẫn thì đưa người duyệt.

### 2.1 OpenCV là gì

**OpenCV** (Open Source Computer Vision Library) là thư viện xử lý ảnh mã nguồn mở phổ biến nhất: đọc ảnh, đổi không gian màu, lọc, tính histogram, tìm vùng liên thông. Mọi kết quả là phép toán xác định trên pixel.

Trong VCuboidFIT (tầng C1):

- đọc ảnh ở ½ độ phân giải, co về 448 × 252;
- tính 13 đặc trưng chất lượng mỗi ảnh, chạy CPU đa luồng;
- ảnh hỏng → `img_ok = False`, mọi cờ = 0, frame vào hàng review với mã `IMG_UNREADABLE`;
- tầng này **chỉ sinh đặc trưng, không chứa ngưỡng**; ngưỡng fit ở C3 trên tập V.

Điểm mạnh: giải thích được từng con số. Giới hạn: không hiểu nội dung ảnh, ví dụ không phân biệt được đèn đường với mặt trời.

### 2.2 OpenCLIP là gì

**OpenCLIP** là bản mã nguồn mở của CLIP (Contrastive Language–Image Pre-training). Mô hình học trên hàng trăm triệu cặp ảnh–chú thích, biến ảnh và câu chữ thành vector 512 chiều trong **cùng một không gian**: ảnh và câu cùng nghĩa thì vector gần nhau.

- Dự án dùng **ViT-B/16 (openai)**, không huấn luyện lại (zero-shot).
- OpenCLIP **không sinh chữ**, nên không phải VLM.
- Embedding ảnh tính một lần trên GPU, cache trong `clip_img.npy`; các bước sau chạy CPU.

Zero-shot hoạt động thế nào:

1. Mỗi lớp có 3 câu mô tả; vector lớp = trung bình 3 câu rồi chuẩn hoá L2.
2. Đo cosine giữa ảnh và từng lớp.
3. Softmax riêng từng trục:

```text
P(c | ảnh, trục) = softmax_{c ∈ trục}( s · cos(z_ảnh, t_c) ),   s = exp(logit_scale) ≈ 100
```

Ví dụ câu mô tả trục `illum`: "a road photo taken in bright daylight", "a twilight street scene from a car camera", "a dark night street scene lit by street lamps".

## 3. Luồng xử lý tầng camera (C0 → C3)

| Bước | Việc | Phần cứng |
|---|---|---|
| C0 · Mặt trời | Độ cao mặt trời từ timestamp + vị trí log (NOAA rút gọn, sai số < 0,3°) | CPU |
| C1 · OpenCV | 13 đặc trưng chất lượng mỗi ảnh | CPU đa luồng |
| C2 · OpenCLIP | Xác suất trên 4 trục bối cảnh từ embedding đã cache | CPU (embedding GPU một lần) |
| C3 · Fit + ghép | Ngưỡng phân vị trên V; luật ghép ra thẻ, biên, cờ review | CPU |
| M3a · Crop vật | Chiếu vật LiDAR lên camera, OpenCLIP ra điểm khái niệm | GPU |
| rare_v24 | Điểm vật, điểm frame, thẻ RHCIO, chọn lô (mục 5) | CPU |

### 3.1 Bảng 13 đặc trưng OpenCV

Cột "Cờ sử dụng" đã đối chiếu với luật trong [`c4/context/fuse.py`](../../model/worker/c4/context/fuse.py).

| # | Tên trong code | Nhóm | Ý nghĩa thực tế | Cờ sử dụng |
|---|---|---|---|---|
| 1 | `luma_mean` | Độ sáng | Độ sáng xám trung bình toàn ảnh | — (chỉ ghi nhận) |
| 2 | `v_mean` | Độ sáng | Độ sáng trung bình kênh V (V = max(B, G, R)) | NIGHT_CV |
| 3 | `v_p5` | Độ sáng | Độ sáng của 5 % pixel tối nhất | VEIL_CV (qua `veil`) |
| 4 | `v_p95` | Độ sáng | Độ sáng của 5 % pixel sáng nhất | VEIL_CV (qua `veil`) |
| 5 | `sat_frac` | Chói | Tỉ lệ diện tích cháy sáng (V ≥ 250) | GLARE_CV |
| 6 | `blob_max_frac` | Chói | Diện tích mảng chói liền lớn nhất | GLARE_CV |
| 7 | `blob_count` | Chói | Số mảng chói riêng lẻ (≥ 20 px) | — (chỉ ghi nhận) |
| 8 | `tile_range` | Chói | Chênh sáng lớn nhất giữa 16 ô lưới 4 × 4 | GLARE_CV |
| 9 | `veil` | Màn mờ | `v_p5 / v_p95`: sương mù, màng nước, loá phủ | VEIL_CV |
| 10 | `noise_sigma` | Độ nét | Mức nhiễu hạt cảm biến (Immerkær 1996) | BLUR_CV (gián tiếp) |
| 11 | `lap_var_raw` | Độ nét | Phương sai Laplacian thô (độ sắc cạnh) | — (chỉ ghi nhận) |
| 12 | `lap_var_dn` | Độ nét | Phương sai Laplacian sau khử nhiễu | BLUR_CV (gián tiếp) |
| 13 | `sharp_ratio` | Độ nét | Độ nét thật = `lap_var_dn / σ_noise` | BLUR_CV |

Ghi chú khi đối chiếu với bảng nháp ban đầu (soạn ở phiên Gemini), có 3 chỗ đã sửa theo code:

- `v_p95` **không** bật NIGHT_CV; nó đi vào `veil = v_p5 / v_p95`, tức thuộc VEIL_CV.
- `blob_count` **không** dùng trong luật GLARE_CV; luật dùng `sat_frac`, `blob_max_frac`, `tile_range`.
- `noise_sigma` và `lap_var_dn` chỉ tác động gián tiếp, qua `sharp_ratio`.

Vì sao cần `sharp_ratio`: ảnh đêm nhiều nhiễu có phương sai Laplacian cao dù thực tế mờ, nên phải chia cho nhiễu mới ra độ nét thật.

### 3.2 Từ đặc trưng đến 4 cờ

Mọi ngưỡng là phân vị học trên tập V.

| Cờ | Luật |
|---|---|
| NIGHT_CV | `v_mean` < P95 của `v_mean` trên các frame V có mặt trời < −6° |
| GLARE_CV | `sat_frac` ≥ P97,5 **và** (`blob_max_frac` ≥ P97,5 **hoặc** `tile_range` ≥ P97,5) |
| BLUR_CV | `sharp_ratio` < P2,5 (nét kém nhất 2,5 % của V) |
| VEIL_CV | `veil` ≥ P97,5 (phủ mờ nhất 2,5 % của V) |

Vì sao dùng phân vị, không dùng ngưỡng cố định: mỗi bộ camera có độ sáng, nhiễu khác nhau. Phân vị trên V nghĩa là "bất thường so với chính dữ liệu này", tự thích ứng khi đổi dataset. P97,5 / P2,5 nghĩa là chỉ 2,5 % ảnh cực đoan nhất của V bật cờ. Ngưỡng lưu trong `context_thresholds_v1.json` kèm SHA, máy sinh, cấm sửa tay.

### 3.3 Bốn trục bối cảnh OpenCLIP (C2)

| Trục | Lớp |
|---|---|
| `illum` | day · lowlight · night |
| `glare` | none · headlight · sun |
| `lens` | clean · droplets · blurred |
| `weather` | dry · rain · fog |

### 3.4 Fit ngưỡng trên V và luật ghép (C3)

Biên mỗi trục = P(top-1) − P(top-2). Ngưỡng biên = P20 của biên trên V (hạ về P10 nếu tỉ lệ review trên V > 15 %). Hàm fit chỉ nhận split V; token ngoài V báo lỗi `LEAK_T`. Mỗi trục ra một trạng thái: **OK** (gán thẻ), **SOFT** (bỏ thẻ, không review), **DISAGREE** (bỏ thẻ, đưa vào review).

- `illum`: độ cao mặt trời quyết định (< −6° night, < 6° lowlight, còn lại day), vì CLIP không tách được night/lowlight trên ảnh tối. CLIP chắc chắn ngược mặt trời (vd trong hầm) ⇒ DISAGREE.
- `glare`: chỉ gán khi cờ CV đồng thuận hoặc CLIP vượt ngưỡng chắc chắn; CLIP "none" nhưng GLARE_CV bật ⇒ DISAGREE.
- `lens`: droplets/blurred chỉ gán khi BLUR_CV hoặc VEIL_CV xác nhận.
- `weather`: ban đêm không gán (CLIP zero-shot cho P(rain) ≈ 0,8 ở mọi cảnh đêm); rain/fog cần biên ≥ mức chắc chắn.

Chưa có file ngưỡng đóng băng ⇒ cảnh báo `CONTEXT_NOT_FROZEN`, mọi thẻ = null. DISAGREE không bao giờ cho thẻ.

## 4. Tập V và tập T

Dữ liệu chia theo scene (cả scene đi cùng nhau, seed cố định) thành các tập tách rời. Benchmark chính có 170 scene nuScenes:

| Tập | Quy mô | Dùng để |
|---|---|---|
| V | 100 scene · 3.973 keyframe | Học tần suất "bình thường", fit mọi ngưỡng (surprisal, camera, khái niệm), chỉnh tham số |
| T | 35 scene · 1.389 keyframe | Chấm điểm cuối cùng, mở đúng một lần; không chỉnh gì theo kết quả T |
| S, P | 7 + 28 scene | Seed và pilot, để riêng |

Vì sao phải tách: vừa học tần suất vừa chấm trên cùng một tập thì điểm cao giả, giống học thuộc đề rồi thi đúng đề đó. Code chặn việc này: hàm fit chỉ nhận split V, frame ngoài V báo lỗi `LEAK_T`.

## 5. Thuật toán điểm S, từng bước

Lấy từ `c4/rare/gate.py`, `object_score.py`, `frame_score.py`, `select.py` và [`configs/rare_def_v24.yaml`](../../model/worker/configs/rare_def_v24.yaml). Trọng số mặc định nằm trong `c4/rare/pipeline.py` và được ghi vào `config_used.json` của mỗi lần chạy.

### Bước 0 · Cổng frame (không chấm điểm)

| Kết quả | Khi nào | Hệ quả |
|---|---|---|
| outlier | Bộ lọc LiDAR loại frame | Không bao giờ được chọn |
| suspect | Không có ứng viên; mọi vật dưới `min_pts`; hoặc embedding z0 lệch > 6σ | Không bao giờ được chọn |
| valid | Còn lại (lệch 3σ–6σ chỉ gắn cờ OOD, không cộng điểm) | Được chấm hạng và chọn |

### Bước 1 · Tham chiếu "bình thường", fit trên V bằng dự đoán

Từ các vật VRU dự đoán (pedestrian, bicycle, motorcycle, vru_unknown) trong frame thuộc V, hệ thống học:

- tần suất từng lớp, p(lớp);
- cạnh bin khoảng cách và số điểm LiDAR = tứ phân vị theo từng lớp, tạo lưới ô (cell) `lớp | d? | p?`;
- tần suất cell = tỉ lệ frame V chứa cell đó, p(cell);
- kích thước trung vị và độ lệch chuẩn (dài, rộng, cao) mỗi lớp.

Độ hiếm đo bằng **surprisal**: `u = −log p`. Cell chưa từng thấy ở V có u = +∞.

Ví dụ: ô "người đi bộ · rất xa · rất ít điểm" xuất hiện ở 2 % frame V ⇒ u = −log 0,02 ≈ 3,9 (hiếm); ô "người đi bộ · gần · nhiều điểm" xuất hiện ở 40 % ⇒ u ≈ 0,9 (thường).

### Bước 2 · Điểm từng vật `s_obj`

```text
s_obj = 0,15·shape + 0,35·slice + 0,30·vru + 0,20·unc        (cắt về [0, 1])
```

| Thành phần | Cách tính | Bắt được gì |
|---|---|---|
| shape (0,15) | `1 − exp(−½·z²)`, z = độ lệch lớn nhất của (dài, rộng, cao) so với trung vị lớp, theo σ | Hình dạng lạ: xe lăn, xe đẩy, người ngồi |
| slice (0,35) | Hạng phần trăm surprisal của cell, trong nhóm VRU của frame hợp lệ; cell chưa thấy = 1 | VRU ở tổ hợp ít gặp: rất xa, rất ít điểm |
| vru (0,30) | 1 nếu pedestrian/bicycle/motorcycle; 0,5 nếu vru_unknown; 0 nếu khác | Đúng đối tượng của bài toán AEB |
| unc (0,20) | ½·hạng(entropy) + ½·hạng(độ bất nhất TTA) của PointPillars, cấp frame | Model đang lưỡng lự; = 0 khi chưa có Tầng 1 |

Bốn thành phần đều trong [0, 1] và trọng số cộng bằng 1, nên `s_obj` trong [0, 1]. Khi chưa có PointPillars, unc = 0 nên `s_obj` tối đa 0,80. Mỗi vật kèm `reasons` = thành phần đóng góp lớn nhất (vd `slice p95`), hiện ở Deep Review.

Profile `multisensor` trộn thêm camera:

```text
s_obj_ms = 0,8·s_obj + 0,2·max( r_sem, 1 nếu crop khớp khái niệm hiếm, ngược lại 0 )
```

`r_sem` = hạng phần trăm độ mới (kNN) của embedding crop vật. 12 khái niệm trong `concepts_v1.yaml`: nhóm R (wheelchair, stroller, child, scooter_rider, cyclist_passenger, delivery_rider, animal_on_road, person_lying, police_directing, construction_worker) và nhóm I (pedestrian_crossing_front, cyclist_merging). Ngưỡng khái niệm = P99,5 trên crop của split tham chiếu.

### Vì sao 0,35 · 0,30 · 0,20 · 0,15

Trọng số xếp theo mức sát với mục tiêu "VRU hiếm":

| Trọng số | Thành phần | Lý do |
|---|---|---|
| 0,35 | slice | Đo đúng định nghĩa "hiếm" mà benchmark chấm (lớp × khoảng cách × số điểm), nên nặng nhất |
| 0,30 | vru | Bài toán chỉ quan tâm người đi bộ, xe đạp, xe máy; vật không phải VRU mất 0,30 nên khó lên top |
| 0,20 | unc | Model lưỡng lự là nơi dữ liệu mới có ích, nhưng chỉ có khi chạy PointPillars nên không để quá nặng |
| 0,15 | shape | Kích thước lấy từ cụm điểm dễ nhiễu (cụm vỡ, cụm ghép), dễ báo "lạ" giả nên nhẹ nhất |

Đây là **trọng số thiết kế**: chọn bằng lập luận về bài toán, khoá trong prereg trước khi chấm T, chưa tinh chỉnh bằng dữ liệu. Câu hỏi mở Q2 trong SPEC-P05 (có ablation trên V hay không) chưa có quyết định. Cách kiểm chứng ở mục 8.

### Bước 3 · Điểm frame và S

```text
raw = 0,70·max(s_obj trong frame) + 0,15·min(số VRU / 5, 1) + 0,15·0,3·[mưa/sương hoặc đêm]
S   = s_frame = hạng phần trăm của raw trên các frame valid     (frame khác: S = 0)
```

| Con số | Lý do |
|---|---|
| 0,70 · lấy max | Mục tiêu là bắt vật hiếm, nên vật nổi nhất quyết định chính. Một người đi bộ hiếm giữa cảnh đông xe đủ kéo cả frame lên; nhiều vật bình thường không cộng dồn thành "hiếm" |
| 0,15 · đông VRU, chặn ở 5 | Nhiều VRU là nhiều cơ hội học; chặn ở 5 để cảnh 30 người không thắng chỉ nhờ đông |
| 0,15 × 0,3 = tối đa 0,045 | Bối cảnh xấu chỉ đủ phân thắng giữa hai frame gần điểm nhau, không đẩy frame tầm thường lên top; thẻ camera chưa đủ chắc (mưa F1 0,48) |
| S là hạng | S = 0,90 nghĩa là cao hơn 90 % frame hợp lệ trong job; không so tuyệt đối giữa hai pool |

Thời tiết lấy từ CAM_FRONT, đêm là mặt trời < −6°. Hai frame cùng raw nhận hạng trung bình. Thẻ RHCIO không cộng vào S.

### Bước 4 · Chọn lô B frame

| Cơ chế | Giá trị | Lý do |
|---|---|---|
| Ngân sách | B = ⌈5 % × số frame hợp lệ⌉ (T: B = 70) | Ngân sách gán nhãn chốt từ trước |
| MMR | λ = 0,7: chọn frame có `0,7·S − 0,3·max độ giống` với các frame đã chọn (cosine trên embedding LiDAR z0) | 70 % theo điểm, 30 % theo đa dạng |
| Phạt track | × 0,5 | Một vật qua nhiều frame: chỉ frame có `s_obj` cao nhất của track giữ điểm |
| Quota scene "even" | ⌈B / số scene⌉ mỗi scene ở pha đầu | Lô phủ đều các scene |
| Explore | cờ | Frame được chọn dù không nằm trong top-B theo S thuần được đánh dấu cho người duyệt |

Mục đích: 70 frame chọn ra là 70 tình huống khác nhau, không phải 70 góc nhìn của cùng một người đi bộ.

### Các ngưỡng định nghĩa "hiếm" (`rare_def_v24.yaml`)

| Con số | Dùng ở đâu | Vì sao giá trị này |
|---|---|---|
| α = 0,10 | Ngưỡng thẻ R1, R2 | Phân vị 90 % độ bất ngờ trên V: chỉ 10 % hiếm nhất vượt qua |
| Tứ phân vị | Chia ô khoảng cách, số điểm | Mỗi lớp chia 4 khoảng có số vật bằng nhau, tự khớp phân bố từng lớp |
| −6° | Mặt trời → đêm | Mốc hoàng hôn dân dụng: dưới −6° trời đã tối |
| 30 m · 10 điểm | Thẻ H (khó) | Vật xa hoặc thưa điểm là nơi detector LiDAR hay bỏ sót |
| 20 m × ±4 m | Thẻ I (hành lang) | Vùng ngay trước xe: làn của mình và một phần làn bên |
| 0,5 m/s | VRU "đang di chuyển" | Thấp hơn tốc độ đi bộ chậm, lọc vật đứng yên và nhiễu bám vết |
| `min_pts` = 1 | Cổng frame | Vật phải có ít nhất 1 điểm LiDAR |
| P99,5 | Ngưỡng khái niệm camera | Chỉ 0,5 % crop giống khái niệm nhất mới được gắn, giảm báo giả |
| 0,8 / 0,2 | Trộn LiDAR với camera | LiDAR vẫn quyết định chính; camera chỉ bổ sung |

Định nghĩa đóng băng: muốn đổi phải tạo `rare_def_v25.yaml` mới, không sửa file cũ. Các mốc 30 m, 20 m, 4 m, 0,5 m/s là lựa chọn thiết kế theo bài toán AEB, không học từ dữ liệu.

### Thẻ RHCIO: giải thích, không cộng vào S

| Thẻ | Điều kiện (suy từ dự đoán, không từ nhãn) |
|---|---|
| R1 | Surprisal lớp của một VRU > phân vị 90 % trên V; hoặc crop khớp khái niệm nhóm R |
| R2 | Surprisal cell (lớp × khoảng cách × số điểm) > phân vị 90 % trên V |
| R3 | VRU di chuyển ≥ 0,5 m/s trong bối cảnh xấu |
| H | Vật xa > 30 m hoặc < 10 điểm LiDAR (chỉ báo cáo) |
| C | Bối cảnh xấu: mưa/sương hoặc đêm |
| I | VRU di chuyển trong hành lang trước xe (0 < x ≤ 20 m, \|y\| ≤ 4 m); hoặc khái niệm nhóm I |

Thẻ không gộp OR thành một cờ `is_rare`: gộp lại thì gần như frame nào cũng "hiếm" (87,6 % frame nuScenes-mini có VRU xa/ít điểm).

### Ví dụ tính tay (lidar_only, chưa có PointPillars nên unc = 0)

Frame ban ngày, trời khô, 3 VRU. Vật nổi nhất: người đi bộ ở cell hiếm (slice = 0,95), kích thước bình thường (shape = 0,10).

```text
s_obj = 0,15·0,10 + 0,35·0,95 + 0,30·1 + 0,20·0 = 0,648
raw   = 0,70·0,648 + 0,15·min(3/5, 1) + 0      = 0,453 + 0,090 = 0,543
```

Nếu 1.200 trong 1.389 frame hợp lệ có raw thấp hơn 0,543 thì S ≈ 0,86 (con số 1.200 là giả định minh hoạ). Đọc là: frame này cao hơn khoảng 86 % frame hợp lệ, lý do hiển thị là `slice p95`. Nếu có PointPillars và model lưỡng lự (unc 0,6), `s_obj` tăng thêm 0,12.

## 6. Vì sao S được thiết kế như vậy

| Đặc điểm | Cách làm và lý do |
|---|---|
| Đo "hiếm" bằng surprisal | `−log(tần suất)` so với tham chiếu học trên V, không đặt ngưỡng cứng kiểu "xa hơn 30 m là hiếm"; tự thích ứng với từng bộ dữ liệu |
| Không dùng nhãn khi chọn | Tham chiếu học từ dự đoán; pool chưa gán nhãn vẫn chạy được, nhãn không rò vào bước chọn (`test_no_leakage_lidar`) |
| Chấm vật trước, frame sau | Frame lấy điểm vật nổi nhất (max); không cộng dồn vật bình thường |
| Trọng số ưu tiên VRU | slice 0,35 và vru 0,30 cao nhất; shape 0,15 vì dễ nhiễu |
| Không cộng dồn tín hiệu | Bối cảnh tối đa 0,045, số VRU bão hoà ở 5, OOD chỉ gắn cờ |
| S là hạng phần trăm | Diễn giải rõ: "cao hơn x % frame hợp lệ trong job" |
| Chọn lô có đa dạng | MMR + phạt track + chia đều scene |
| Giải thích được | Mỗi frame có `reasons`, thẻ RHCIO và bằng chứng để người duyệt đối chiếu 3D và camera |
| Chấm kết quả theo vật | IY theo instance và NY trên thang Random–Oracle, bootstrap theo scene; đếm theo frame dễ cho số đẹp giả |

## 7. Đánh giá

### 7.1 Đánh giá điểm S

Module duy nhất được đọc nhãn: `c4/rare/eval.py`. Quy trình: chốt định nghĩa và ngưỡng trên V, đăng ký trước (prereg, có SHA256), rồi mở T đúng một lần.

Mục tiêu: instance GT thuộc trục R2. Với `capture = rare_form`, instance chỉ tính "bắt được" khi frame chọn chứa nó đúng ở dạng hiếm.

```text
IY@B = số instance mục tiêu khác nhau có ≥ 1 frame trong lô / B
NY@B = (IY − E[IY_random]) / (IY_oracle − E[IY_random])
```

- **IY** (instance yield): mỗi frame gán nhãn thu được bao nhiêu vật hiếm khác nhau. 10 frame cùng một người đi bộ chỉ tính 1.
- **NY**: 0 = ngang Random (trung bình 100 lần), 1 = ngang Oracle (tham lam trên GT). NY âm = kém Random.
- **Reach**: bao nhiêu instance mục tiêu có ít nhất một ứng viên LiDAR cách tâm ≤ 1 m. Không có ứng viên thì không phương pháp xếp hạng nào bắt được.
- **CI95**: bootstrap theo scene 1.000 lần. CI của chênh lệch chứa 0 ⇒ không tuyên bố hơn.

### 7.2 Đánh giá tầng camera

Hai mức tách biệt: (A) thẻ bối cảnh có đúng không; (B) thêm camera vào S có giúp chọn frame tốt hơn không.

**Mức A · thẻ bối cảnh.** Job `night_v24` trên nuScenes trainval: 255 scene, 10.173 keyframe, 61.038 ảnh. V = 100 scene để fit; chỉ đo ngoài V: 37.086 ảnh, 6.181 frame, 155 scene (45 đêm, 10 mưa). Đáp án: `scene.description` chứa "night"/"rain" (nhãn cấp scene, thô), chỉ đọc trong script đo.

| Trục (CAM_FRONT) | Frame | Thật + | Gắn + | P | R | Macro-F1 | Cổng |
|---|---|---|---|---|---|---|---|
| Đêm | 6.181 | 1.809 | 1.648 | 1,000 | 0,911 | 0,968 | ≥ 0,85 ✅ |
| Mưa | 6.181 | 402 | 66 | 0,000 | 0,000 | 0,480 | ≥ 0,70 ❌ |

- Đêm tốt vì luật mặt trời gần như không sai (P = 1,00); recall 0,911 do chạng vạng bị xếp lowlight.
- Mưa trượt đúng như thiết kế dự báo: ban đêm cố ý không gắn thời tiết nên mưa đêm luôn bị bỏ; 66 lần gắn "mưa" đều rơi vào ban ngày không mưa.
- Gánh nặng review: 7,7 % ảnh ngoài V (9,7 % trên V, dưới trần 15 %); theo frame là 34 %.
- Đây là phép đo minh hoạ (ngưỡng fit trên V của chính job), chưa phải nghiệm thu trên T độc lập.

**Mức B · ablation M3 − M2.** Cùng pool T, cùng B = 70, cùng tham chiếu V, chỉ khác có camera hay không.

| Cấu hình | IY | CI95 | NY | Thời gian A100 |
|---|---|---|---|---|
| M2 lidar_only | 0,100 | [0,000; 0,257] | 0,052 | ~140 s |
| M3 multisensor | 0,057 | [0,000; 0,171] | −0,030 | ~1.035 s |

Pool T toàn ban ngày, không có đêm/mưa, nên chưa đo được đúng chỗ tầng bối cảnh được thiết kế để giúp; 28/42 mục tiêu không có ứng viên LiDAR, camera (chỉ chấm lại vật LiDAR đề xuất) không cứu được.

### 7.3 Kết quả benchmark T

Benchmark đăng ký trước (pitch-v2), Colab A100, 13–14/10/2026: 1.389 frame, 35 scene, B = 70, 42 instance mục tiêu. Nguồn: [`web/public/demo/bench_pitch.json`](../../web/public/demo/bench_pitch.json) (run `20261013-192329-49de1480`).

| Phương pháp | IY | CI95 | NY | Reach 1 m |
|---|---|---|---|---|
| M0 Chọn ngẫu nhiên (TB 100 lần) | 0,073 | [0,020; 0,156] | 0,000 | – |
| M1 Điểm hình học Tầng 0 (đối chứng) | 0,114 | [0,000; 0,291] | 0,079 | – |
| M2 Điểm S · chỉ LiDAR | 0,100 | [0,000; 0,257] | 0,052 | 14/42 |
| M3 Điểm S · LiDAR + camera | 0,057 | [0,000; 0,171] | −0,030 | 14/42 |

- M2 − M1 = −0,014, CI95 [−0,164; 0,084]: CI chứa 0, chưa đủ cỡ mẫu để phân định.
- Nút thắt ở bước bắt ứng viên: Reach 14/42 (33 %); trọng số tốt đến đâu cũng không chọn được 28 instance không có ứng viên.

### 7.4 Tầng 1: PointPillars

Train trên nuScenes trainval (Colab A100), đo riêng trên 602 frame VAL (RTX 4060 Laptop, 10 sweep). Đánh giá tham khảo, chưa chạy lại benchmark T.

| Checkpoint | mAP | NDS | Ghi chú |
|---|---|---|---|
| mini-e80 | 0,017 | 0,065 | Mốc trước khi train lớn |
| trainval e6/20 | 0,209 | 0,282 | ~285 ms/frame, 1,1 GB VRAM |
| trainval e12/20 | 0,220 | 0,343 | ~330 ms/frame, 1,1 GB VRAM |

AP theo lớp ở e12: ô tô 0,790 · xe tải 0,702 · xe máy 0,547 · người đi bộ 0,132 · xe đạp 0,012 · rào chắn 0,013 · cọc 0,000. Lớp nhỏ còn yếu vì mới tới epoch 12/20, tắt gt_sampling để tránh rò nhãn, chỉ dùng 29 % trainval.

## 8. Kiểm chứng các con số (việc tiếp theo)

Mọi tinh chỉnh chỉ làm trên V; T mở đúng một lần. Thước đo là IY và NY kèm CI95 bootstrap theo scene.

| Phép thử | Câu hỏi |
|---|---|
| Chia đều | 0,35/0,30/0,20/0,15 có tốt hơn 4 × 0,25 không? |
| Bỏ từng phần | Tắt lần lượt shape, slice, vru, unc: phần nào bỏ mà IY không giảm thì không cần |
| Quét lân cận | Dịch trọng số quanh bộ hiện tại: kết quả ổn định thì con số đáng tin, chỉ tốt ở một điểm thì là may |
| Chấm trên T mới | Chọn cấu hình trên V, khoá, chấm một lần trên tập T mới có đêm và mưa |

Đi kèm: train PointPillars đủ 20 epoch để có thành phần unc, dùng PointPillars làm nguồn ứng viên để nâng Reach; tìm tín hiệu khác cho mưa đêm (giọt nước trên ống kính, phản chiếu mặt đường); đo riêng độ chính xác điểm khái niệm.

## 9. Chạy lại bằng CLI

```bash
python -m c4.cli.extract_clip --data-root D --job-dir J --device cuda   # embedding ảnh (GPU)
python -m c4.cli.context cv  --data-root D --job-dir J                  # C1 OpenCV (CPU)
python -m c4.cli.context fit --job-dir J --split V                      # C3 fit ngưỡng, chỉ V
python -m c4.cli.context run --data-root D --job-dir J                  # C2 + ghép -> context_frame
python -m c4.cli.rare crops  --data-root D --job-dir J --device cuda    # M3a crops
python -m c4.cli.rare run    --data-root D --job-dir J --profile multisensor
```

Mã thoát `rare`: 0 hoàn tất · 2 thiếu đầu vào / contract / crops lỗi thời · 3 cấu hình sai · 1 lỗi khác. Cần `split_manifest.csv` trước khi fit; không gộp V/T.

## 10. Bất biến và vùng cấm

- Không VLM/LLM ở bất kỳ bước nào; ca khó đưa cho người duyệt.
- Bước chấm và chọn không đọc nhãn của pool; thẻ camera là dự đoán, không phải nhãn.
- Ngưỡng và tham chiếu chỉ fit trên V, lưu kèm SHA; `rare_def_v24.yaml` đóng băng (đổi định nghĩa = file v25 mới).
- Không tune lại trọng số bằng kết quả T; không mở lại T để chấm.
- Một model GPU mỗi process; bảng dữ liệu qua `c4.contracts` (Parquet, không DB).
