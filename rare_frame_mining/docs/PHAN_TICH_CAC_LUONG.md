# PHÂN TÍCH CHI TIẾT CÁC LUỒNG — pipeline rare-frame-mining v2.3

Tài liệu trả lời cho MỖI module 5 câu: **làm gì — vì sao phải có (nếu bỏ thì sao) —
input/output — giúp ích gì — metric trả ra nghĩa là gì**. Viết cho người mới vào dự án
và cho người chấm kết quả (không cần đọc code vẫn hiểu).

## 0. Luồng tổng quát

**v2.2 (10/10/2026) — cách dùng model ("Cả hai"):** LÕI = checkpoint PointPillars công khai
đóng băng, chỉ inference (mục 5). TUỲ CHỌN = Bước 0 train model Seed + vòng retrain (mục 13b),
bật/tắt bằng công tắc; AP downstream chỉ báo khi bật. Sơ đồ `docs/workflow_v2.png` vẽ khối
tuỳ chọn bằng viền tím nét đứt.

```
Frame LiDAR (keyframes) ── M0 data/weather ── M1 candidates ──┬─ M2 điểm vật thể ─┐
                                                              └─ M3 điểm frame ◄──┘
                                        ┌───────────────────────────────────┘
                     M4 rank/dedup/quota ── M5 top-B + CSV ── ĐỘI GÁN NHÃN ── M6 đánh giá
                     (M0.5 sanity/pilot đứng trước, ra go/no-go)
```

Nguyên tắc xuyên suốt: **nhãn GT chỉ module M6 và M0.5 được nhìn**; mọi thứ ở giữa
chạy label-free. Bất kỳ sửa đổi nào phá nguyên tắc này đều invalidates toàn bộ đánh giá.

---

## 1. `data.py` — Nạp dữ liệu & 3 nguồn (M0, phần 1)

| Câu hỏi | Trả lời |
|---|---|
| Làm gì | Định nghĩa khung `Frame` (bản ghi mỏng — điểm load lazy) và `GTBox`; dựng 3 nguồn dữ liệu cùng interface: `BinDirSource` (`.npy/.bin` + `meta.json` + `gt.json` của công ty), `NuscenesSource` (adapter devkit, chỉ keyframes), dùng chung cho mọi bước sau |
| Vì sao phải có | Không có lớp trừu tượng nguồn thì mỗi module phải tự biết đọc mỗi định dạng; đổi data (công ty ↔ nuScenes) phải sửa toàn pipeline. Lazy-load là bắt buộc: 40k keyframes × ~10k điểm nếu load hết sẽ chết RAM (sandbox 2 GB, máy thật cũng không đủ) |
| Nếu bỏ | Pipeline chỉ chạy được 1 định dạng; OOM khi nạp pool lớn; không có chỗ cắm `gt.json` → không có "đáp án giấu" cho M6 |
| Input | Thư mục `.npy/.bin` (N×3 hoặc N×4, [x y z intensity]), meta (scene/t/ego/desc), gt.json (box + class + num_lidar_pts); hoặc dataroot nuScenes |
| Output | Danh sách `Frame{fid, scene, t, ego_xy, desc, loader(), gt_fn(), camera_paths}` — `gt_fn` là **hộp đen chỉ M6 gọi** |
| Giúp ích | Vừa là kênh dữ liệu cho scorer (không nhãn), vừa là kênh GT giấu cho đánh giá — hai kênh tách nhau bằng interface |

**Chống leak theo nguồn gốc model (v2.2):** `NuscenesSource(split="auto")` chỉ nạp scene
model CHƯA thấy: 150 scene val (trainval) hoặc 2 scene mini_val (mini), theo split chính thức
của devkit (`create_splits_scenes`). Hàm `select_scenes` chặn `split="all"`/`"train"` khi
`model_provenance="nuscenes_train"` (checkpoint công khai) — bản v2.1 nhận tham số `split`
nhưng không dùng, nên nạp cả scene train (leak `s_unc`/`s_ood`). Model Seed/ngoài
(`provenance="seed"|"external"`) được dùng scene khác, frame Seed loại qua `--seed-manifest`.

**Chú ý schema:** `num_lidar_pts` chỉ có sẵn trong nuScenes; nguồn BinDir phải tự đếm
điểm trong box (như `synthetic.py` làm mẫu) nếu muốn slice "<10 điểm" có GT đúng.

## 2. `synthetic.py` — Dữ liệu tổng hợp

- **Làm gì**: sinh làng đường giả có đủ các slice hiếm thật (bicycle/motorcycle, vật xa,
  vật sparse, crowd, mưa có backscatter, đêm chỉ là metadata) + GT box kèm đếm điểm.
- **Vì sao**: cho phép chạy end-to-end và test mọi module **không cần nuScenes/GPU**;
  test tự động phải có GT để khẳng định hành vi.
- **Nếu bỏ**: không demo được, không có test end-to-end — mọi bug phải tìm trên data thật
  (đắt và mù).
- **Metric/kết quả trả ra**: không — đây là fixture. Lưu ý đã ghi trong README: base rate
  của demo (~79% frame hiếm) là **cố ý không thực tế** → con số demo chỉ chứng minh code
  chạy đúng, KHÔNG phải hiệu năng.

## 3. `weather.py` — Slice thời tiết / đêm

| | |
|---|---|
| Làm gì | 3 kênh tín hiệu: ① `parse_desc` — regex trên `scene.description` (metadata chính thức); ② `lidar_rain_proxy` — tỉ lệ điểm "trên không" intensity thấp (backscatter giọt mưa) chuẩn hoá thành điểm liên tục [0..1]; ③ `camera_brightness` — proxy đêm từ ảnh (nếu có camera); `rain_score_combine` ghép metadata + proxy |
| Vì sao phải có | Đề bài yêu cầu slice "mưa, đêm". Phản biện domain đã chứng minh: **LiDAR chủ động, không suy giảm ban đêm** → "đêm" tuyệt đối KHÔNG suy từ hình dạng point cloud; **mưa là biến cường độ** (mm/h) không phải nhị phân → proxy liên tục |
| Nếu bỏ | (a) Suy "đêm" từ cloud → gán nhãn ban đêm vô nghĩa, người gán thấy ranking kỳ lạ, mất niềm tin vào hệ thống; (b) mưa nhị phân → bỏ phân biệt mưa nhỏ/mưa to mà suy giảm LiDAR khác nhau từng bậc (Robo3D) |
| Input | `desc` (chuỗi), point cloud (N×4), đường dẫn ảnh camera (tuỳ chọn) |
| Output | `night ∈ {0,1}`, `rain_score ∈ [0,1]` |
| Giúp ích | Hai cờ của 4 tiêu chí "hiếm" trong đề; `rain_score` liên tục cho phép quota slice rain tách mưa to |
| Metric | `night=1` → frame thuộc slice đêm (eval nhánh LiDAR của hệ fusion AEB + OOD gap); `rain_score` ≥0.75 = metadata xác nhận mưa, 0.2–0.5 = proxy nghi ngờ (khuyếch đại thấp vì proxy dễ nhiễu), >0.5 → tính là mưa trong hard-boost |

## 4. `features.py` — Hình học cụm điểm

- **Làm gì**: `crop_roi` (cắt ROI 1–50 m), `remove_ground` (lưới xy, ground mỗi ô = min-z),
  `cluster_points` (DBSCAN, fallback voxel-CC), `cluster_features` (n, L/W/H **theo hướng
  trục riêng gần z = H** — sửa bug người đứng cao 1.7 m bị ghi H≈0.5), `vru_prior`,
  `person_like`.
- **Vì sao**: đây là đường nguồn **(a) độc lập với model** — thứ duy nhất bắt được vật mà
  PointPillars **bỏ sót** (chính là nhóm vật hiếm cần nhất). `vru_prior` giữ scorer không
  nhặt rác/cột/cone chỉ vì "hiếm hình".
- **Nếu bỏ**: chỉ còn nguồn (b) → mọi vật model miss biến mất khỏi ranking trước cả khi
  ai kịp gán nhãn; không có ground removal → DBSCAN gộp cả mặt đất thành 1 cụm khổng lồ.
- **Input/Output**: point cloud → danh sách cluster + đặc trưng `[n, L, W, H, eig1-3,
  density, height, centroid, yaw, mean_intensity]`.
- **Metric (đặc trưng)**: `n_points` & `density` — vật xa/thưa có cả hai thấp (nguyên nhân
  slice "ít điểm"); `height` + `W` — phân biệt người (cao 0.6–2 m, hẹp) với hộp/bịch;
  eigenvalues — dạng thẳng/bẹt/khối; `min_pts_shape=10` — dưới ngưỡng này hình học không
  ổn định nên `vru_prior` hạ xuống 0.3 thay vì loại (cluster ít điểm vẫn phải giữ lại —
  nó chính là hiếm).

## 5. `detectors.py` — PointPillars (chỉ inference) + TTA

| | |
|---|---|
| Làm gì | 3 backend cùng interface: `heuristic` (giả lập từ cluster — demo/test), `mmdet3d`, `openpcdet` (model thật, chỉ inference — đề bài cấm train lại); `augment_points` + `untransform_box` cho TTA (xoay/flip/jitter rồi biến đổi ngược box về hệ gốc) |
| Vì sao phải có | Model là nguồn (b): cung cấp **lớp dự đoán** (cluster không có), `det_score`, và nguyên liệu `s_unc`. TTA là cách rẻ nhất đo uncertainty khi chỉ được dùng 1 model đóng băng (không ensemble được) |
| Nếu bỏ | Mất lớp dự đoán → không định nghĩa được "lớp hiếm bicycle/motorcycle" ở cấp ứng viên; mất `s_unc` → không còn tín hiệu "model không chắc chắn" nào ngoài shape |
| Input/Output | point cloud (hoặc bản augmented) → list `Detection{center, size, yaw, score, class_name, probs}`; TTA trả về variance đã untransform |
| Metric | `det_score` — độ tự tin model (đầu vào baseline confidence-only ở M6); `tta_std_xy / tta_std_size` — box nhảy bao nhiêu giữa các pass (nhảy nhiều = model không chắc về vị trí/kích thước); `tta_entropy` — phân bố lớp đều (không biết là gì); `missed=True` — model không ghép được pass nào về cluster này → uncertain nhất (capping khi mọi candidate đều missed) |

**Cạm bẫy (ghi trong skill):** mmdet3d trả cột kích thước có thể là (w,l,h) tuỳ phiên bản —
M0.5a `box_schema` check tồn tại để bắt lỗi này trước khi chạy toàn bộ.

## 6. `m1_candidates.py` — Sinh ứng viên vật thể (M1)

- **Làm gì**: chạy song song 2 nguồn, **match theo BEV-IoU** để không đếm đôi: cluster mà
  không có detection nào khớp → `missed=True` (model bỏ sót — giữ nguyên, đây là vàng);
  detection không khớp cluster nào → thành ứng viên riêng (`source='det'`). Sau đó chạy
  các TTA pass và ghép về cluster canonical trong bán kính `match_radius`.
- **Vì sao**: điểm xuất phát của mọi scoring; design "2 nguồn + match" là biện pháp đối
  với lỗi CRITICAL "model bỏ sót chính vật hiếm" và lỗi đếm đôi bị phản biện chỉ ra.
- **Nếu bỏ match IoU**: một vật xuất hiện 2 lần (cluster + box) → crowd_count và obj_agg
  phình, ranking nghiêng về frame đông vật trùng lặp.
- **Input/Output**: Frame (điểm) → list candidate dict (mỗi ứng viên mang đủ đặc trưng,
  lớp dự đoán, TTA variance, 3 cờ far/few/confusion) + `aux` (thống kê frame: n_total,
  n_fg, frac_air, mean_int, rain_proxy) + `mean_det_score`.
- **Giúp ích**: quyết định "vật nào tồn tại trong frame này" — mọi điểm số phía sau đều
  tính trên danh sách này.
- **Metric quan sát**: số candidate/frame, tỉ lệ `missed_by_model` (cao bất thường ở một
  vùng → domain shift hoặc model yếu đúng loại vật đó — M0.5a đo chính xác hơn).

## 6b. `outlier_gate.py` — Cổng NGOẠI LAI (v2.3, Phương án chốt 10/10 bước 2)

| Câu hỏi | Trả lời |
|---|---|
| Làm gì | 4 phép thử không cần nhãn: (1) hợp lệ dữ liệu (đủ điểm, NaN, cường độ, điểm dưới mặt đường, Δt, ego), (2) nhất quán thời gian (keyframe liền kề còn điểm LiDAR quanh vị trí vật, hệ toàn cục), (3) hình học/ngữ nghĩa (không lơ lửng, kích thước VRU khả dĩ), (4) k-NN tới V khác scene ≤ p99.9 của V. Chia **Hợp lệ / Nghi ngờ / Ngoại lai** |
| Vì sao phải có | Hiếm và ngoại lai đều "lạ"; nếu chỉ dùng một điểm OOD thì frame lỗi cảm biến được xếp lên đầu như frame hiếm, đốt ngân sách gán nhãn và làm bẩn tập train |
| Nếu bỏ | Frame thưa điểm/NaN/điểm "ma" lọt vào lô gán nhãn; không còn bằng chứng tách hiếm khỏi lỗi |
| Input/Output | frame + ứng viên M1 (+ s_vru_raw M2) → `gate`, `gate_fail`, `gate_tier`; `review_T.csv` |
| Ràng buộc | fit tham chiếu (trung vị, k-NN) không dùng nhãn, k-NN chỉ trên V; frame tier > 0 xếp sau và không bao giờ `selected=1` |
| Metric | `corruption_test.<kiểu>.leak_rate` = tỉ lệ frame cố ý làm hỏng lọt vào Hợp lệ (thấp là tốt); `rare_true_as_outlier/suspect` = tỉ lệ frame hiếm thật (GT) bị loại nhầm (thấp là tốt); `domain_shift_warning` = cả loạt T cô lập so với V |

**OOD từ v2.3 chỉ là cờ** (`ood_flag` khi `ood_raw` > p95 của V; `frame.w_ood = 0`). Muốn so sánh
với bản cũ thì đặt `w_ood > 0` như một ablation và khai báo trong báo cáo.

## 7. `m2_object_score.py` — Điểm vật thể (M2)

| Thành phần | Làm gì | Nếu bỏ | Metric → ý nghĩa |
|---|---|---|---|
| `s_shape` | IsolationForest (fit **chỉ trên V**, fallback kNN/z-dist) đo độ hiếm của vector [L,W,H,eigs,density,log n,height] | Scorer chỉ còn các cờ luật → rơi lại tautology (phản biện CRITICAL #1), không phát hiện "hiếm mới" ngoài luật | `s_shape_raw` lớn = vùng hình dạng thưa trong data — ứng viên hiếm thật |
| `s_unc` | TTA variance + entropy; missed → cap trên | Mất tín hiệu model-không-chắc; nhưng KHÔNG được nặng — rareness ≠ uncertainty (REM ECCV'22) | `s_unc_raw` — trọng số mặc định chỉ 0.15 |
| `s_slice` | mean 3 cờ: >30 m, <10 điểm, cặp nhầm quen | Mất 2/4 tiêu chí "hiếm" của đề | `far/few/confusion` — cờ cứng, minh bạch, trích được trong "lý do" |
| `s_vru` | prior hình dạng VRU (0.6–2 m, ≤1.2 m; nới cho trẻ em) | Scorer nhặt rác/cột/cone hiếm-hoi không liên quan AEB | `s_vru_raw ∈ {0, 0.3, 0.5, 1}` |
| **`s_obj`** | **rank_agg (Borda có trọng số)** + hard_boost mỗi cờ | Cộng đại số thô → thành phần scale lớn lấn át (phản biện MAJOR) | `s_obj ∈ (0,1]` — percentile-trong-split, chỉ so được trong cùng 1 lần chạy |

**Vì sao rank-aggregation**: các thành phần ở thang đo khác nhau (kNN-distance mét, entropy
0–1, IoU 0–1). Rank từng thành phần trong split rồi Borda → không cần chuẩn hoá, bền nhiễu,
ít hyperparam (chống overfit V nhỏ — phản biện MAJOR #4).

## 8. `m3_frame_score.py` — Điểm frame (M3)

- **Làm gì**: 4 thành phần → `s_frame`; đồng thời tính `rule_only` (ablation) và
  `slice_primary` (quota). OOD dùng Mahalanobis 8 chiều thống kê frame, **fit trên V**
  (subset "comfort" = nửa frame model tự tin nhất — xấp xỉ "phân phối model đã học").
- **Nếu bỏ từng cái**: không có `obj_agg` → frame có 1 vật hiếm quý bị chìm trong frame
  nhiều vật thường; không có `s_ood` → không phát hiện "khác phân phối model đã học" ngoài
  các luật (đề yêu cầu); không có `rule_only` → M6 không chứng minh được shape/unc/ood có
  đóng góp (tautology); không có `slice_primary` → quota đa dạng hoá vô hình.
- **Metric**:
  - `crowd_count` — số cluster/detection giống người; ≥5 = "đông" (đề).
  - `night`, `rain_score` — từ weather (mục 3).
  - `ood_raw` — khoảng cách Mahalanobis; **lớn = frame khác hẳn phân phối V-comfort**.
    Chỉ so được trong cùng run (fit trên V của run đó).
  - `obj_agg = 0.5·max + 0.5·mean-top-k(s_obj)` — max bắt "1 vật hiếm cũng đủ", top-k
    chống 1 outlier decide hết.
  - `rule_only` — số tín hiệu luật thô (0–4): ablation cho M6.
  - `slice_primary` — slice đầu tiên khớp theo thứ tự ưu tiên rare_class→crowd→night→
    rain→far_few→typical; dùng cho quota M4 và đọc report theo slice.

## 9. `m4_aggregate.py` — Rank, dedup, đa dạng hoá (M4)

- **Làm gì**: sort theo `s_frame` → gộp nhóm dedup (cùng scene VÀ gần nhau theo **Δt < 2 s
  HOẶC ego dịch < 2 m**) → **giữ top-2 mỗi nhóm** → chọn top-B có **quota slice**
  (rare_class 0.30, crowd 0.20, night 0.15, rain 0.15, far_few 0.20, typical 0.10).
- **Vì sao từng quyết định**: nuScenes ghi liên tục 2 Hz — không dedup thì 4 keyframe cùng
  1 cảnh đốt 4 suất ngân sách (phản biện kỹ thuật); nhưng dedup giữ-chỉ-1 làm mất coverage
  cảnh kéo dài → top-k (phản biện phương pháp); Δt cứng bẻ gãy với data 20 Hz của công ty
  → thêm displacement; quota chống "ranking rơi hết vào mưa đêm" và chống dataset nghiêng
  (phản biện domain).
- **Nếu bỏ quota**: bảng xếp hạng thiên lệch không kiểm soát; model sau này yếu case thường
  (phản biện SP #8) — chỉ cần tăng `typical` quota nếu đội model phàn nàn.
- **Input/Output**: frame_dicts → `ranked_all` (đủ, có `rank_nodedup`) + `ranked_kept`
  (sau dedup, có `rank`).
- **Metric**: `kept` — frame sống sót dedup; `dedup_effect` (tính ở M6) = R@B của
  pipeline-vs-nodedup — **âm bao nhiêu là chi phí coverage của dedup bấy nhiêu**; nếu
  được sử dụng, ngưỡng chấp nhận mất ≥3–5 điểm recall phải được người mua nhãn ký.

## 10. `m5_select.py` — Đầu ra bàn giao (M5)

Hai CSV + 2 JSON. Ý nghĩa từng cột (đọc khi duyệt kết quả):

`frames_ranked_T.csv`: `rank` (thứ tự gán nhãn — số nhỏ gán trước) · `rank_nodedup` (thứ tự
trước dedup — đối chiếu chi phí dedup) · `s_frame` (điểm tổng) · `rule_only` (tín hiệu luật
thô) · `mean_det_score` (model tự tin trung bình — thấp = model lúng túng) · `obj_agg`,
`crowd_count`, `night`, `rain_score`, `ood` (thành phần) · `slice_primary` · `kept` ·
`reasons` (**văn bản lý do — người gán nhãn đọc được, không cần hiểu scorer**).

`objects_T.csv` (vật khoanh sẵn trong từng frame): `fid, cid` · `source` (cluster / det /
cluster+det — "cluster" thuần = model bỏ sót) · `class_name`, `det_score` · `dist_m`,
`n_points`, `L/W/H` (nguyên nhân slice xa/ít-điểm) · `cx,cy,cz,yaw` (box khoanh) ·
`s_shape_raw, s_unc_raw, s_slice_raw, s_vru_raw, s_obj` (trace từng thành phần) ·
`far/few/confusion` (cờ cứng) · `missed_by_model` · `reasons`.

`summary.json` (đếm + top-10 preview) · `config_used.json` (toàn bộ tham số đã chạy —
bắt buộc lưu để tái lập; phản biện F8 về reproducibility).

## 11. `m05_pilot.py` — M0.5 Pilot (sanity + chọn mẫu)

| | |
|---|---|
| Làm gì | (M0.5a) chọn tập nhỏ **2 mẫu**: `random` (ước base rate — vô chệch) + `stratified` (tín hiệu rẻ "có cụm 2-bánh" — để bắt được lớp hiếm, **chấp nhận chệch**); chạy detector trên đó, greedy-match detection↔GT theo IoU cùng lớp; xuất per-class recall/precision + slice VRU + **checklist 4 quyết định**. (M0.5b ở `run_pilot.py batch`) |
| Vì sao | Đốt 240k inference rồi mới phát hiện "cột box sai thứ tự / recall lớp hiếm = 0" là lỗi đắt nhất dự án; điểm chọn lại của M0.5 là ra **quyết định go/no-go**, không phải cải thiện model |
| Nếu bỏ | Mọi bug schema/domain-shift chỉ lộ khi đã gán nhãn vài nghìn frame hoặc sau M6 toàn pool |
| Input/Output | frames (có GT), detector, config → `pilot_sanity.json` |
| Giúp ích | Nút go/no-go trước khi scale; đồng thời là cơ sở chọn nguồn (b) dùng/bỏ, cần camera hay không |

**Metric của M0.5a — ý nghĩa & ngưỡng:**

| Metric | Ý nghĩa | Đọc thế nào |
|---|---|---|
| `per_class.recall` + `recall_wilson95` | recall mỗi lớp + khoảng tin 95% | n nhỏ → CI rất rộng (bình thường); hành động theo **tâm** CI, không theo giá trị chấm |
| `box_schema` (IoU TP trung bình) | box model và GT có mô tả cùng vật cùng cách không | PASS ≥0.55; WARN → kiểm tra thứ tự cột (w,l,h) mmdet3d **trước khi làm gì khác** |
| `intensity_channel` | kênh intensity có khắp nơi không | thiếu → tắt `rain_proxy`, slice mưa chỉ còn metadata |
| `vru_recall_ngoai_30m` | model nhớ VRU ở vùng xa không | <0.3 → xem lại ngưỡng "xa" của đề cho sensor này |
| `rare_class_recall` | recall bicycle+motorcycle | <0.25 → nguồn (b) ít giá trị với lớp hiếm; tăng `--n-strat` nếu CI quá rộng |

**Nguyên tắc hai mẫu:** base rate chỉ được ước từ mẫu RANDOM; mẫu phân tầng chỉ dùng đo
recall. Trộn hai mục đích = số liệu sai hệ thống.

## 12. `m6_evaluate.py` — Đánh giá trên GT giấu (M6)

**Làm gì**: áp bộ lọc luật lên GT của T (lớp ∈ {bicycle, motorcycle} ∨ VRU >30 m ∨ VRU <10 điểm;
frame hiếm = có vật hiếm ∨ đông ≥5 ∨ đêm ∨ mưa), rồi đo bảng xếp hạng của pipeline so với
4 baseline. **Vì sao**: đây là "đáp án giấu" của đề — giá trị hệ thống nằm ở chỗ nó so với
random cùng chi phí. **Nếu bỏ**: không ai biết bảng xếp hạng có đáng tiền hơn random không.

**Phạm vi luật xa/ít điểm (v2.2, `obj.far_few_scope`)**: mặc định `"vru"` — chỉ xét
pedestrian/bicycle/motorcycle, vì đề là bài toán VRU cho AEB. Đo trên 404 keyframe nuScenes
mini: tính mọi lớp → 404/404 frame "hiếm" (base rate 100%, đánh giá vô nghĩa); chỉ VRU →
354/404; chỉ lớp bicycle/motorcycle → 265/404. Kể cả bản VRU, base rate trên mini vẫn rất cao
→ số báo cáo phải lấy trên 150 scene val của trainval và đọc kèm `base_rate`. Lưu ý thêm
(REM, ECCV'22): xa/ít điểm là **khó** (hard), không phải **hiếm** (rare) — giữ trong đáp án
vì đề yêu cầu, nhưng báo cáo nên tách slice `far_few` khỏi `rare_class`.

`report["model"]`: mode / provenance / retrain — để người đọc biết số liệu đến từ checkpoint
công khai hay model Seed, và AP downstream có được báo hay không.

**Từng metric & cách đọc:**

| Metric | Ý nghĩa | Đọc / hành động |
|---|---|---|
| `base_rate` | tỉ lệ frame hiếm trong T | mọi lift phải đọc **tương đối** với base rate; base cao → random mạnh → lift nhỏ là bình thường |
| `P@B` | trong B frame được chọn, bao nhiêu % thật sự hiếm | chi phí lãng phí nhãn; P thấp hơn random → scorer có vấn đề thật |
| `R@B` | bao nhiêu % frame hiếm được bắt trong B | hiệu quả khai thác; đọc cùng recall ceiling |
| `AP` (full ranking) | chất lượng TOÀN BỘ thứ tự, không phụ thuộc chọn B | so scorer với nhau khi chưa chốt B |
| `lift_over_random` | R@B − random R@B | **chỉ số quan trọng nhất cho người mua nhãn**; lift ≤ 0 ở mọi B → scorer vô dụng |
| `random_mean/std` | random ×10 seeds | std cho biết biên độ nhiễu của so sánh — lift phải > std mới tin |
| `rule_only_ablation` | ranking chỉ từ 4 cờ luật | rule-only ≈ pipeline → shape/unc/ood không đóng góp (tautology cảnh báo); pipeline > rule-only rõ rệt → scorer có giá trị thêm |
| `confidence_only` | chỉ dùng det_score | kiểm tra composite tốt hơn 1 tín hiệu đơn thuần |
| `pipeline_nodedup` + `dedup_effect` | trước/sau dedup | giá của dedup (âm recall) — quyết định keep_topk |
| `yield_vru_per_frame` | số GT-VRU box mỗi frame gán nhãn | ngôn ngữ tiền: nhãn đáng tiền bao nhiêu; so pipeline vs random |
| `slices[s].n_pos / R@B / random_R@B` | recall theo từng slice hiếm | thấy scorer yếu slice nào (vd chỉ được mưa, dở crowd) |
| `slices[s].wilson` | CI 95% cho precision trong slice nhỏ | slice n nhỏ → CI rộng; đừng kết luận từ 1 số chấm |
| `object_level.precision/recall` | box khoanh có trúng GT hiếm (IoU ≥ 0.5) | chất lượng đầu ra cấp VẬT — cái đội gán thấy |
| `bootstrap_recall_by_scene` | resample theo scene → CI recall | frame cùng scene tương quan — bootstrap đúng cấp scene mới không giả CI hẹp |
| `n_pilot_excluded` | số frame PILOT bị loại | bằng chứng cơ chế chống leak đang chạy |

## 13. `pipeline.py` — Orchestrator (M0→M5)

- **Làm gì**: nạp frames → (subset/exclude) → M1 cho mọi frame → chia **V/T theo scene**
  (+ `PILOT` cho frame exclude) → M2 fit-chỉ-trên-V → aggregate → M3 fit-OOD-chỉ-trên-V →
  aggregate → M4 rank/dedup/quota từng split → M5 ghi file → lưu `artifacts.pkl` cho M6.
- **Vì sao thứ tự**: `s_obj` phải có trước `frame_raw_features` (bug đã gặp và vá);
  shape/OOD fit trước khi chấm T (nếu fit trên T = leak thống kê); split theo scene vì
  frame liền kề cùng cảnh (leak, phản biện).
- **Nếu bỏ**: pipeline không tái lập được; leak ở mọi tầng.
- **Tuỳ chọn `--tune rule_v`**: grid-search 4 trọng số frame trên **GT của V** — biến thể
  khai báo (label-free mặc định giữ nguyên); chỉ dùng khi đã có nhãn thử nghiệm.
- **Tham số `exclude_fids`**: label-ledger v0 — frame đã gán nhãn/pilot bị tách khỏi V/T.

## 13b. `scripts/train_seed.py` — Bước 0 + vòng retrain (TUỲ CHỌN)

| Câu hỏi | Trả lời |
|---|---|
| Làm gì | `manifest`: chọn tập Seed (frame đã có nhãn) → `seed_manifest.json`; `infos`: lọc infos .pkl của OpenPCDet xuống đúng Seed và in lệnh train; `add`: gộp lô vừa gán nhãn (selected=1, explore=1) vào Seed → round mới |
| Vì sao có | Workflow 9/10 cho phép công ty tự train model trên dữ liệu đã có nhãn và cải thiện qua từng vòng. Đây là công tắc, không phải lõi: lõi vẫn chạy với checkpoint công khai |
| Nếu bỏ | Lõi không đổi; chỉ mất khả năng báo AP sau vòng retrain |
| Input/Output | nuScenes/BinDir + danh sách fid có nhãn → `seed_manifest.json` (+ infos .pkl đã lọc) |
| Ràng buộc | Frame Seed luôn bị loại khỏi V/T (`--seed-manifest` → split PILOT); sau mỗi lần train lại phải chạy lại M0.5a sanity và sinh lại toàn bộ bảng xếp hạng; script KHÔNG tự train (cần GPU + OpenPCDet) |
| Metric | AP/NDS chuẩn nuScenes của model Seed trên val sau mỗi round — **chỉ báo khi `--retrain` bật**. Phương án B: `--explore-frac` thêm cột `explore=1` cho frame ngẫu nhiên ngoài lô chọn, giữ phân phối chung khi train lại |

## 14. `utils.py` — Hàm nền

| Hàm | Làm gì | Nếu thiếu | Ý nghĩa khi xuất hiện trong report |
|---|---|---|---|
| `bev_iou` (Sutherland–Hodgman, polygon xoay thật) | IoU box BEV chính xác kể cả box xoay | match cluster-det và M6 sai khi box yaw ≠ 0 | mọi "IoU ≥ 0.5" trong report dựa vào đây |
| `rank_pct` + `weighted_rank_agg` | percentile rank + Borda có trọng số | cộng đại số thô → thành phần lấn át | `s_obj/s_frame` luôn trong (0,1] và so được trong split |
| `Mahalanobis` (shrinkage) | khoảng cách tới phân phối V | OOD chết khi covariance singular (8 chiều, n nhỏ) | `ood_raw` lớn = khác phân phối V |
| `wilson_ci` | CI 95% cho tỉ lệ n nhỏ | 1 số chấm trên 10 mẫu → kết luận sai | mọi recall/precision kèm n nhỏ trong report |
| `average_precision` | AP của ranking nhị phân | chỉ còn P/R@B phụ thuộc chọn B | `AP` trong report |
| `save_json/save_csv` + seed | tái lập | không tái lập được run | `config_used.json` |

---

## 15. Bảng tóm tắt "bỏ module X thì vỡ gì"

| Bỏ | Hậu quả ngay lập tức |
|---|---|
| weather.py | slice đêm/mưa sai cơ chế (đêm suy từ cloud) → 2/4 tiêu chí hiếm vô nghĩa |
| features.py (clustering) | mất mọi vật model bỏ sót — nhóm quý nhất của bài toán |
| detectors.py + TTA | mất lớp dự đoán, `s_unc`, baseline confidence-only |
| match IoU trong M1 | đếm đôi → crowd/obj_agg phình, ranking nghiêng |
| rank-agg (utils) | thành phần scale lớn lấn át; scorer không so được giữa runs |
| dedup | 1 cảnh ăn 4 suất ngân sách (2 Hz) |
| quota | ranking lệch 1 slice, dataset nghiêng |
| M0.5 | bug schema/recall phát hiện sau khi đốt cả pool |
| rule_only + yield (M6) | không chứng minh được scorer có giá trị thêm (tautology) |
| `outlier_gate` | frame lỗi (thưa điểm, NaN, điểm "ma") được chọn như frame hiếm; OOD cộng điểm đẩy chúng lên đầu |
| `select_scenes` (split auto) | scene train lọt vào V/T khi dùng checkpoint công khai → s_unc/s_ood lệch, M6 không còn sạch |
| `far_few_scope="vru"` | luật xa/ít điểm tính cả xe/rào chắn → gần như mọi frame "hiếm", Random thắng mặc định |
| PILOT split | nhãn pilot lọt vào T → toàn bộ M6 không còn là "đánh giá trên GT giấu" |
