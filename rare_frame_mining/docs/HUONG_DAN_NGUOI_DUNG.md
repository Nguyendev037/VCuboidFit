# HƯỚNG DẪN NGƯỜI DÙNG — chạy pipeline rare-frame-mining từ đầu đến cuối

Tài liệu này đi theo đúng sơ đồ `docs/workflow_v2.png`, từng bước có: lệnh chạy →
kết quả mong đợi → đọc gì → quyết định gì. Bản đồ chi tiết từng module (làm gì/vì sao/
metric nghĩa là gì) xem `docs/PHAN_TICH_CAC_LUONG.md`. Lộ trình các trường hợp chưa làm:
`ROADMAP.md`.

> Mới vào dự án: đọc `docs/README_TONG_QUAN.md` trước (tổng quan, flowchart, user story).
>
> **Cập nhật v2.2 (10/10/2026) — quyết định "Cả hai":** LÕI dùng checkpoint PointPillars
> công khai **đóng băng** (chỉ inference). Bước 0 train model Seed và vòng retrain là
> **công tắc tuỳ chọn** (Bước 8b), AP downstream chỉ báo khi bật. Kèm theo: nuScenes chỉ lấy
> scene model chưa thấy (`--split auto` = 150 scene val / 2 scene mini_val), luật xa/ít điểm
> trong đáp án chỉ tính VRU (`far_few_scope="vru"`).
>
> **v2.3:** thêm **cổng NGOẠI LAI** (Hợp lệ / Nghi ngờ / Ngoại lai) chạy trước khi chọn; OOD chỉ
> còn là cờ, không cộng điểm. Frame Nghi ngờ/Ngoại lai nằm trong `review_T.csv`, không bao giờ
> `selected=1`. Smoke tests nay là **10/10**.

```
Bước 1 cài đặt → Bước 2 demo → Bước 3 chuẩn bị dữ liệu → Bước 4 M0.5a sanity (PASS?)
→ Bước 5 M0.5b pilot (GO?) → Bước 6 chạy full pool → Bước 7 M6 đánh giá
→ Bước 8 bàn giao gán nhãn → Bước 9 vòng lặp
```

---

## Bước 0 — Chuẩn bị môi trường

**Bạn cần:** Python ≥ 3.9 + pip; ~500 MB đĩa cho demo; **không cần GPU** cho tới khi cắm
model thật. Đi kèm project là detector heuristic (giả lập) — đủ để chạy toàn luồng.

```bash
# Cách 1 — một lệnh (khuyên dùng): giải nén + cài + 10/10 tests + demo tự động
bash scripts/bootstrap.sh [đường-dẫn-zip] [thư-mục-làm-việc]

# Cách 2 — thủ công
unzip rare_frame_mining.zip -d .
cd rare_frame_mining
python3 -m pip install -r requirements.txt
python3 tests/test_smoke.py          # phải in: "TẤT CẢ SMOKE TESTS ĐẠT ✓" (7 dòng OK)
python3 scripts/demo_synthetic.py    # ~15–30 giây
```

**Kết quả phải có:** `tests` in 10/10 OK; `demo_output/` chứa 5 file
(`report.json, frames_ranked_T.csv, frames_ranked_V.csv, objects_T.csv, summary.json,
config_used.json`). Nếu thiếu bất kỳ file nào — **dừng**, đọc thông báo lỗi trước khi
đi tiếp (xem Bước 10 — Khắc phục sự cố).

---

## Bước 1 — Xem demo để hiểu đầu ra (10 phút)

Mở `demo_output/report.json` và bảng in cuối demo. Ba điều cần rút ra:

1. **Bảng P@B / R@B có 6 cột:** Pipeline | Random | Rule-only | Conf-only | NoDedup.
   Trong demo, Random mạnh bất thường (P@50 ≈ 0.8) — vì demo tổng hợp có ~79% frame
   hiếm (cố ý). **Đừng lấy con số demo làm bằng chứng** — nó chỉ chứng minh code chạy
   đúng. Trên data thật (base rate vài %), Random sẽ yếu hơn nhiều.
2. **Cột `reasons`** trong `frames_ranked_T.csv` là văn bản người gán nhãn đọc được
   (vd "mưa (1.00); có vật xa >30 m hoặc <10 điểm; OOD (4.02)").
3. **`config_used.json`** là tham số của lần chạy này — cứ mỗi lần chạy hãy giữ nó
   (tái lập kết quả).

## Bước 2 — Chuẩn bị dữ liệu của bạn (chọn 1 nhánh)

### Nhánh A — dữ liệu công ty (thư mục .npy/.bin)

Dựng thư mục như sau:

```
data_cty/
├── frame_0001.npy        # (N, 3|4) float32: x y z [intensity] — frame sensor
├── frame_0002.npy        #   đặt tên Scene_XXXX_fYYYY thì scene tự nhận trước "_"
├── meta.json             # tuỳ chọn nhưng RẤT nên có:
│   {"frame_0001": {"scene": "s01", "t": 0.0, "ego": [0.0, 0.0], "desc": "Night, light rain."}}
└── gt.json               # chỉ bắt buộc khi muốn M6/M0.5a — do đội gán tạo RA SAO
    {"frame_0001": [{"center": [12.3, -3.4, 0.9], "size": [1.7, 0.6, 1.5],
                     "yaw": 0.1, "class": "vehicle.bicycle", "num_lidar_pts": 7}]}
```

Kiểm tra nhanh trước khi chạy (không bắt lỗi ngầm):
- `desc` phải ghi **đêm/mưa bằng chữ** ("Night", "rain") — pipeline KHÔNG suy "đêm" từ
  point cloud; không ghi thì slice đêm/mưa coi như không có.
- `num_lidar_pts`: nếu bạn chưa có, tự đếm điểm trong box (công thức trong
  `extension-recipes.md` recipe 2 / làm mẫu trong `synthetic.py`).
- Scene names phải đúng là scene (frame cùng scene phải cùng tiền tố trước `_`).

### Nhánh B — nuScenes

```bash
pip install nuscenes-devkit pyquaternion
# Tải v1.0-mini (~4 GB) — đủ cho Bước 3–5. v1.0-trainval (~300 GB) cho chạy thật.
# KHÔNG dùng test split: không có GT → M6/M0.5a chạy không được.
python3 - <<'PY'
from rare_mining import NuscenesSource
# split="auto" (mặc định): trainval → 150 scene val; mini → 2 scene mini_val
print(len(NuscenesSource("/duong-dan/nuScenes", "v1.0-mini").frames()), "keyframes")
PY
```

**Vì sao chỉ lấy val (chống leak):** checkpoint PointPillars công khai đã train trên split
train của nuScenes. Nếu để scene train vào V/T thì model "đã thấy" chúng → `s_unc`, `s_ood`
thấp giả tạo. Code chặn cứng: `--split all` hoặc `--split train` với
`--model-provenance nuscenes_train` (mặc định) sẽ báo `ValueError`. Chỉ khi dùng model Seed
tự train (Bước 8b) hoặc model ngoài (`--model-provenance seed|external`) mới được dùng scene khác.

**Lưu ý với v1.0-mini:** mini_val chỉ có 2 scene (scene-0103, scene-0916; 81 keyframe) → V = 1
scene, T = 1 scene. Đủ để chạy thử luồng, KHÔNG đủ để báo số. Đã đo trên 404 keyframe mini:
nếu luật xa/ít điểm tính mọi lớp thì 404/404 frame là "hiếm" (base rate 100%); chỉ tính VRU
còn 354/404; chỉ lớp bicycle/motorcycle là 265/404. Base rate cao như vậy làm Random rất mạnh
→ báo số thật phải chạy trên trainval (150 scene val) và luôn đọc kèm `base_rate`.

## Bước 3 — M0.5a: kiểm định model (nút PASS/FAIL đầu tiên)

```bash
python3 scripts/run_pilot.py sanity \
    --source bindir --dataroot data_cty \        # hoặc --source nuscenes --dataroot ... --version v1.0-trainval (split auto = val)
    --n-random 150 --n-strat 50 --out pilot_sanity.json
```
(Trên mini_val chỉ có 81 frame: hạ xuống `--n-random 40 --n-strat 10`.)

- `--n-random`: mẫu NGẪU NHIÊN (ước base rate — vô chệch). `--n-strat`: mẫu PHÂN TẦNG
  (cố tình tìm frame có cụm "2 bánh" — dùng đo recall lớp hiếm; **bị chệch, không dùng
  để ước base rate** — hai mẫu hai mục đích, đừng trộn).
- **Yêu cầu dữ liệu phải có GT** cho các frame được chọn (gt.json). Với nuScenes: có sẵn.

**Đọc `pilot_sanity.json` (hoặc bảng in) — checklist 4 dòng, xử lý theo verdict:**

| Check | PASS | WARN → làm gì ngay |
|---|---|---|
| `box_schema` (IoU TP trung bình) | ≥ 0.55 | KIỂM TRA THỨ TỰ CỘT (w,l,h) của detector trước khi làm gì khác (recipe 1 bước 4) |
| `intensity_channel` | ≥ 50% frame có kênh 4 | Tắt `rain_proxy` (slice mưa chỉ còn metadata — khai báo trong kết quả) |
| `vru_recall_ngoai_30m` | ≥ 0.3 | Xem lại ngưỡng "xa 30 m" với sensor này hoặc tăng `score_thresh` thấp xuống |
| `rare_class_recall` | ≥ 0.25 | Nguồn (b) ít giá trị với lớp hiếm → tăng `--n-strat` (nếu Wilson CI quá rộng) hoặc chấp nhận clustering là nguồn chính |

**Lưu ý đọc số:** mỗi recall kèm `recall_wilson95` — n nhỏ thì CI rất rộng là BÌNH THƯỜNG
(hành động theo tâm CI, đừng hoảng với 1 số chấm). Nếu cả bảng toàn "n/a" → mẫu chưa có
GT → kiểm tra gt.json / chọn split trainval.

**Quyết định:** cả 4 check PASS (hoặc WARN đã xử lý xong) → sang Bước 4. FAIL box_schema
→ dừng, sửa detector adapter, chạy lại sanity. Đây là điểm rẻ nhất để dừng.

## Bước 4 — M0.5b: lô thử nghiệm (nút GO/NO-GO thứ hai)

```bash
python3 scripts/run_pilot.py batch \
    --source bindir --dataroot data_cty \
    --n-frames 800 --budget 60 --out pilot_output
```

Sinh ra:
- `pilot_output/pilot_fids.json` — danh sách frame pilot (**GIỮ LẠI** — Bước 6 chống leak).
- `pilot_output/pilot_labeling_top.csv` (60 frame pipeline chọn) và
  `pilot_output/pilot_labeling_random.csv` (60 frame random) — giao đội gán nhãn, yêu cầu
  **gán TẤT CẢ vật thể VRU trong từng frame** (lệnh trong cột `task`).
- `pilot_output/frames_ranked_*.csv` — bảng xếp hạng nội bộ pilot.

**Sau khi đội gán xong:** cập nhật nhãn vào `gt.json` (2 lô), rồi:

```bash
python3 scripts/run_eval.py --out pilot_output
# Xem trong report.json: "yield_vru_per_frame": {"pipeline": X, "random_mean": Y}
```

**Quyết định GO/NO-GO:** yield của pipeline ≥ 1.2× random (tức mỗi frame gán nhãn thu
được ≥20% nhiều GT-VRU hơn) → GO sang Bước 5. Yield ngang random → đừng scale: quay lại
Bước 3, xem checklist WARN nào chưa xử lý; cân nhắc đổi detector/checkpoint.

Gợi ý thêm từ M0.5b: đếm objects/frame (median, p90) từ 2 lô → quy ngân sách B frame
thành **số box** (thị trường tính tiền theo box) trước khi cam kết với bên gán nhãn.

## Bước 5 — Chạy FULL POOL (40k keyframes)

```bash
python3 scripts/run_pipeline.py \
    --source bindir --dataroot data_cty \
    --exclude-fids pilot_output/pilot_fids.json \
    --budget 200 --out outputs_run1
# nuScenes: --source nuscenes --dataroot /data/nuScenes --version v1.0-trainval
```

- `--exclude-fids` (file JSON list hoặc dict): frame pilot **và sau này là frame đã gán
  nhãn** (label ledger) — chúng bị ép `split='PILOT'`, M6 tự loại → không leak vào V/T.
- `--budget 200` = ngân sách B (số frame gán nhãn trước) — ĐỀ CỦA CÔNG TY QUYẾT.
- `--max-frames N` nếu muốn chạy thử nhỏ trước (cắt ĐỀU THEO SCENE).
- Thời gian tham chiếu: heuristic detector ~50 frame/phút/CPU như sandbox; PointPillars
  thật ≈ 2.5–7 giờ GPU cho 40k keyframes (cluster + TTA) — lên lịch chạy dài, dùng
  `nohup`/`tmux`; thư mục output theo lần chạy (`outputs_run1`, `outputs_run2`…), đừng
  ghi đè lẫn nhau.

**Kết quả mong đợi:** `outputs_run1/{frames_ranked_T.csv, frames_ranked_V.csv,
objects_T.csv, summary.json, config_used.json, artifacts.pkl}`. Trong
`frames_ranked_T.csv`, cột **`selected=1`** là lô khuyến nghị GIAO GÁN NHÃN (đúng B frame sau quota đa dạng hoá); các dòng còn lại chỉ là thứ tự đầy đủ để tham khảo — đừng gán hết.

## Bước 6 — M6: đánh giá trên GT giấu

```bash
python3 scripts/run_eval.py --out outputs_run1 --report outputs_run1/report.json
```

**Đọc `review_T.csv` trước khi giao lô:** đây là frame Nghi ngờ/Ngoại lai (cột `gate_fail` ghi
phép thử bị trượt). Người duyệt mở point cloud: nếu là dữ liệu thật → thêm fid vào danh sách
xác nhận và chạy lại với `{"gate": {"suspect_policy": "include"}}` hoặc nới ngưỡng tương ứng;
nếu là lỗi → báo đội dữ liệu. `report.json → outlier_gate.corruption_test.*.leak_rate` phải
≈ 0 (lỗi giả không lọt cổng); `rare_true_as_outlier` phải thấp.

Checklist đọc report (theo thứ tự quan trọng):

1. `lift_over_random` — **số quan trọng nhất**: R@B của pipeline trừ random. Phải dương
   và lớn hơn `random_std` mới tin được (nếu lift ≤ 0 ở mọi B → scorer vô dụng, xem lại
   Bước 3).
2. `pipeline` vs `rule_only_ablation` — pipeline phải **vượt rõ** rule-only; nếu ngang →
   s_shape/s_unc/s_ood không đóng góp (cảnh báo tautology).
3. `slices` — scorer yếu slice nào (rare_class / far_few / crowd / night / rain); kèm
   `wilson` — slice n nhỏ đừng kết luận vội.
4. `yield_vru_per_frame` + `object_level` — ngôn ngữ tiền và chất lượng box khoanh.
5. `dedup_effect` — chi phí recall của dedup; nếu mất >3–5 điểm → tăng `keep_topk` trong
   config rồi chạy lại.
6. `n_pilot_excluded` > 0 — bằng chứng cơ chế chống leak đang chạy.
7. `base_rate` — mọi lift phải đọc tương đối với base rate này.

## Bước 7 — Bàn giao cho đội gán nhãn

Giao: các dòng `selected=1` của `frames_ranked_T.csv` (đúng B frame) + `objects_T.csv`. Quy ước:
- Gán theo thứ tự `rank` nhỏ → lớn trong nhóm selected; mỗi frame gán **tất cả VRU** (kể cả vật model bỏ
  sót — cột `missed_by_model=1` chính là gợi ý chỗ cần tìm kỹ).
- `reasons` là gợi ý, KHÔNG phải nhãn — người gán tự xác nhận bằng point cloud.
- Kiểm chất lượng (Wave 1 của ROADMAP): double-label 5–10% lô → IAA IoU ≥0.75, class
  accuracy ≥98%; tranh chấp → senior adjudicate.

## Bước 8 — Vòng lặp (frame mới gán xong → vòng 2)

1. Cập nhật nhãn mới vào `gt.json` (frame cũ gán xong giờ có nhãn thật).
2. Chạy vòng 2 với ledger đầy đủ hơn:
   ```bash
   python3 scripts/run_pipeline.py --exclude-fids ledger.json --out outputs_run2 ...
   # ledger.json = pilot_fids + mọi frame đã gán nhãn (list các fid)
   ```
   → những frame đã gán không bao giờ được chọn lại; nhãn mới nằm trong pool GT cho M6
   (chú ý Wave-2 ROADMAP: giữ quota 10–20% exploration random để scorer không tự đuổi
   theo đuôi đã harvest).
3. Tuỳ chọn `--tune rule_v` — CHỈ khi V đã có nhãn thật (grid search 4 trọng số frame
   trên GT của V; kết quả in log, được ghi vào `config_used.json`).

## Bước 8b — Công tắc tuỳ chọn: Bước 0 train Seed + vòng retrain

Lõi KHÔNG cần mục này. Bật khi công ty muốn dùng nhãn mới để cải thiện model.

```bash
# (1) Chọn tập Seed (frame đã có nhãn) → seed_manifest.json (round 0)
python3 scripts/train_seed.py manifest --source nuscenes --dataroot /data/nuScenes \
    --version v1.0-trainval --seed-split train --n-scenes 100 --out seed_manifest.json
#     data công ty: --source bindir --labeled-fids labeled.json
# (2) nuScenes + OpenPCDet: lọc infos train xuống đúng Seed, in lệnh train (cần GPU)
python3 scripts/train_seed.py infos --dataroot /data/nuScenes --version v1.0-trainval \
    --manifest seed_manifest.json --infos /data/nuScenes/nuscenes_infos_10sweeps_train.pkl
# (3) Train xong → sanity với checkpoint Seed (Bước 3) → chạy pipeline chế độ seed
python3 scripts/run_pipeline.py --source nuscenes --dataroot /data/nuScenes --version v1.0-trainval \
    --model-mode seed --seed-manifest seed_manifest.json --retrain --explore-frac 0.15 \
    --detector openpcdet --checkpoint seed_r0.pth --model-config pointpillar.yaml \
    --budget 200 --out outputs_seed_r0
# (4) Gán nhãn lô selected=1 (+ lô explore=1 = phương án B), gộp vào Seed → round 1
python3 scripts/train_seed.py add --manifest seed_manifest.json --labeled lo_selected.json lo_explore.json
#     → quay lại (2): train lại, sanity lại, chạy vòng mới với manifest mới
```

- `--seed-manifest`: frame Seed bị ép `split=PILOT`, không bao giờ vào V/T.
- `--retrain` + `--explore-frac f`: thêm cột `explore=1` cho round(f·B) frame NGẪU NHIÊN ngoài
  lô chọn (phương án B — giữ phân phối chung khi train lại). Không ảnh hưởng M6.
- `report.json` có khối `model` (mode, provenance, retrain). AP của model sau mỗi vòng
  (đánh giá chuẩn nuScenes trên val) **chỉ báo khi `retrain` bật**; khi tắt chỉ báo M6.
- Đổi checkpoint giữa các vòng → bảng xếp hạng phải sinh lại toàn bộ (ROADMAP F4).
- Script KHÔNG tự train (cần GPU + OpenPCDet); adapter `openpcdet` vẫn phải map output theo
  phiên bản (Bước 9 mục 4) trước khi chạy thật.

## Bước 9 — Cắm PointPillars thật (khi sẵn GPU)

Tóm tắt (chi tiết recipe 1 trong skill/zip):
1. `pip install torch mmdet3d` (khớp CUDA/spconv — dự phòng 2–3 ngày setup).
2. Chạy `run_pipeline.py --detector mmdet3d --checkpoint <.pth> --model-config <py>`.
3. **Bắt buộc verify trước scale:** chạy `run_pilot.py sanity` — check `box_schema` PASS
   mới tiếp tục (bắt lỗi thứ tự cột w/l/h của mmdet3d).
4. `--detector openpcdet`: adapter còn raise lỗi có chủ ý — cần map output theo phiên bản.

## Bước 10 — Khắc phục sự cố

| Triệu chứng | Nguyên nhân | Xử lý |
|---|---|---|
| `ImportError: rare_mining` | chạy script từ thư mục khác | `cd rare_frame_mining` trước |
| Sanity: `box_schema` WARN | thứ tự cột size (w,l,h) mmdet3d | đổi cột trong `MMDet3DPointPillars.detect` |
| Sanity: `rare_class_recall` "n/a" | mẫu không bắt được lớp hiếm / thiếu GT | tăng `--n-strat`, kiểm tra gt.json, dùng trainval không phải test |
| `KeyError: 'num_lidar_pts'`-hành vi lạ ở slice ít điểm | BinDir không có field | tự đếm điểm trong box (recipe 2) |
| Wilson CI cực rộng ở slice | n mẫu quá nhỏ | tăng n hoặc gộp slice khi báo cáo; đừng kết luận từ 1 chấm |
| `ValueError: split='all' gồm scene mà checkpoint công khai đã thấy` | chống leak đang chạy | dùng `--split auto`; chỉ khai `--model-provenance seed/external` khi model thật sự không train trên nuScenes train |
| `--model-mode seed` in CẢNH BÁO thiếu manifest | quên `--seed-manifest` | truyền manifest để frame Seed bị loại khỏi V/T |
| Quá nhiều frame "Nghi ngờ" do phép temporal | xe rẽ gấp / data 20 Hz khác 2 Hz | tăng `gate.temporal_radius_m` hoặc `temporal_min_unsupported` trong config |
| `domain_shift_warning: true` | T khác hẳn V (cảm biến/địa bàn khác) | không phải hiếm: chia lại V/T cùng nguồn hoặc fit tham chiếu mới |
| Chạy giữa chừng bị kill | RAM/đĩa; sandbox 2 GB | `--max-frames`; chỉ keyframes (đã mặc định); tắt TTA trong config |
| Chạy lại ghi đè kết quả cũ | dùng chung `--out` | mỗi lần chạy một thư mục `outputs_run<N>` |
| Demo P@50 ≈ 0.8 ở cả Random | bình thường (synthetic base rate cao) | không phải bug; đo thật trên data thật |
| M6 báo thiếu GT | frame T không có gt | BinDir: bổ sung gt.json; nuScenes: đổi sang mini/trainval |
| `run_pipeline` chậm ở M1 | clustering nhiều điểm | giảm ROI `max_range`, tăng `ground_cell`; giữ keyframes |

## Bảng cheat sheet — tất cả lệnh

| Mục đích | Lệnh |
|---|---|
| Kiểm tra cài đặt | `python3 tests/test_smoke.py` (10/10 OK) |
| Demo không cần data | `python3 scripts/demo_synthetic.py` |
| M0.5a sanity | `python3 scripts/run_pilot.py sanity --source ... --n-random 150 --n-strat 50` |
| M0.5b pilot batch | `python3 scripts/run_pilot.py batch --source ... --n-frames 800 --budget 60 --out pilot_output` |
| Full pool | `python3 scripts/run_pipeline.py --source ... --exclude-fids ... --budget B --out outputs_runN` |
| Đánh giá M6 | `python3 scripts/run_eval.py --out outputs_runN` |
| Tune trên GT của V | thêm `--tune rule_v` vào run_pipeline |
| Bước 0 Seed (tuỳ chọn) | `python3 scripts/train_seed.py manifest / infos / add ...` |
| Chế độ Seed + retrain | `run_pipeline.py --model-mode seed --seed-manifest seed_manifest.json --retrain --explore-frac 0.15 ...` |
| Vẽ lại sơ đồ | `python3 docs/make_diagram.py` (cần matplotlib) |

**Thứ tự không được đảo:** sanity trước pilot, pilot trước full pool, `exclude-fids`
trước khi chạy lại bất kỳ run nào có frame đã gán nhãn. Đó là ba van an toàn của luồng.
