# Benchmark giám khảo độc lập (judge-bench)

Câu hỏi duy nhất: **với cùng một pool ảnh và cùng ngân sách B, lô ảnh VCuboidFIT chọn có làm một model nhận diện AEB *độc lập* bỏ sót hoặc không chắc trên đối tượng có thật nhiều hơn lô của bên thứ 3 không? Và huấn luyện thêm trên lô đó có giúp model ấy tốt hơn không?**

Đây là bằng chứng về "đầu ra" của data mining: giá trị của lô ảnh được đo bằng model *của người khác*, không phải bằng thước của chính mình. Thiết kế đầy đủ (SPEC, prereg, handoff, số đo) nằm ở hồ sơ quản trị `planning/21_2026-10-17_external-judge-bench/` trong workspace BuildLab. Trang này là bản tóm tắt cho developer.

## 1. Thiết kế trong một hình

```text
PandaSet / Argoverse 2 ──adapter──► data-root dạng nuScenes (ảnh 1600×900)
        │ split tất định theo chuỗi: CAL 20 % · POOL 55 % · EVAL 25 %
        ▼
 POOL ──► mọi bên chọn B = 5 %  (OURS, M1, M2 · X0 random×100 · X1 k-center DINOv2 · X2 uncertainty YOLO11m · X3 đếm đông · N1 mờ · N2 tối)
        │ selections.json + sha256  ⇐ commit TRƯỚC khi giám khảo chạy POOL
        ▼
 CAL ──► giám khảo JA (Faster R-CNN v2) + JB (RT-DETR): hiệu chỉnh τ, kiểm hợp lệ V1–V3
 POOL ─► chấm toàn bộ một lần ⇒ đối tượng GT AEB nào bị "struggle"
        ▼
 SY@B, Δ = SY(OURS) − max bên thứ 3, CI bootstrap cụm theo chuỗi, Holm ⇒ report + dashboard
 EVAL ─► Pha 4: fine-tune JA trên từng lô, đo AP50 VRU ⇒ giá trị huấn luyện
```

## 2. Vì sao làm như vậy (tóm tắt tài liệu tham khảo)
| Rủi ro | Cách chặn | Nguồn |
|---|---|---|
| Thước tự chế, sân nhà | Giám khảo là model công khai không ai trong dự án train | DataComp (Gadre 2023) |
| "Phân vân" bị ăn gian bằng ảnh mờ/tối/rỗng | Chỉ chấm trên đối tượng GT thật; heuristic mờ/tối phải thua | CODA (Li 2022) |
| Giám khảo thiên vị họ model gần nó | 2 giám khảo khác kiến trúc, không trùng họ với selector; thắng phải đúng với cả hai | self-preference bias |
| Baseline yếu ⇒ thắng giả | random ×100 + k-center + uncertainty + đếm đông, cùng điều kiện | DeepCore 2022, Mittal 2019, Lüth 2023 |
| Tune trên test | Engine giữ nguyên config nuScenes (zero-shot); prereg băm trước; POOL/EVAL mở một lần | — |
| Phân vân ≠ có ích | Pha 4 train-on-selection | AL 3D nuScenes (Liang 2022) |

## 3. Metric chính
- **Đối tượng AEB:** VRU (người đi bộ, xe đạp, xe máy) ≤ 40 m, và xe trong hành lang `0 < x ≤ 40 m`, `|y| ≤ 2 m`. Mỗi đối tượng có ≥ 1 điểm LiDAR, hộp 2D cao ≥ 20 px, mỗi đối tượng lấy một camera.
- **Struggle:** giám khảo không có detection cùng nhóm với IoU ≥ `iou_thr` và score ≥ τ. τ và `iou_thr` được hiệu chỉnh trên CAL sao cho recall trên đối tượng dễ ≥ 0,90.
- **SY@B** = số instance khác nhau bị struggle trong lô / B.
- **Luật thắng (prereg `judge-bench-v1`, sha `4b8ef249…`):** trên Argoverse 2, cận dưới CI95 của Δ > 0 với mọi giám khảo hợp lệ (≥ 2), và OURS thắng random, N1, N2 sau Holm. Không đạt ⇒ "chưa chứng minh ở cỡ mẫu này". PandaSet chỉ là sơ bộ.

## 4. Code và lệnh
| Thành phần | Đường dẫn |
|---|---|
| Lõi: split, cổng, registry, đối tượng AEB, metric | `model/worker/c4/bench/{split,gate,registry,aeb,metrics}.py` |
| Bọc engine / bên thứ 3 / giám khảo / Pha 4 | `c4/bench/{ours,thirdparty,judge,train_sel}.py` |
| Dashboard, helper Colab | `c4/bench/{dashboard,colab}.py` |
| Adapter dữ liệu ngoài | `c4/data/adapters/{pandaset,av2,common}.py`, CLI `python -m c4.cli.adapt` |
| CLI benchmark | `python -m c4.cli.bench_judge split\|prereg\|select\|judge\|report\|train-eval --job-dir J` |
| Notebook Colab A100 (12 ô) | `model/notebooks/vcf_judge_bench_colab.ipynb` |
| Notebook thẩm định độc lập (CPU, không import `c4`) | `model/notebooks/vcf_judge_bench_review.ipynb` + `judge_bench_review_core.py` |
| Test | `model/worker/tests/bench/`, `tests/test_adapt_*.py`, `tests/test_splits_override.py` (126 test, 2026-10-17) |

Thứ tự bắt buộc (CLI từ chối nếu sai, mã thoát 3): `adapt → lidar_index → split → prereg → select (băm) → judge cal → judge pool (một lần) → report → train-eval`.

Mã thoát: 0 ok · 2 thiếu đầu vào · 3 vi phạm thứ tự/hash/đã mở · 4 giám khảo không hợp lệ · 5 hết VRAM.

## 5. Quy trình chạy thật (đã đo 2026-10-17)

### 5.1. Lấy dữ liệu
| Bộ | Cách lấy | Kết quả đo |
|---|---|---|
| nuScenes pilot (P1) | `python -I model/scripts/subset_nusc.py --src E:/nuscenes_trainval --version v1.0-trainval --scenes scene-1059..scene-1073 --out F:/vcf_ext/nusc_pilot/root` | 15 scene VAL, 602 kf, ảnh 6 camera + LiDAR keyframe + 5 267 sweep LiDAR, 4,87 GB, 49 s |
| Argoverse 2 Sensor VAL (P3) | `python -I model/scripts/fetch_av2_val.py --out F:/vcf_ext/av2/src --workers 32` (S3 công khai, tải tiếp được) | 150 log, 57 783 file, 35,65 GB (đầy đủ 166 GB; chỉ lấy LiDAR + 7 camera gần keyframe 2 Hz + nhãn + calib), 68 phút ở ~8,6 MB/s |
| PandaSet (P2) | trang chính thức cần form; bản Kaggle chưa kiểm | chưa có |

### 5.2. Chuẩn bị job ở máy (OPERATIONS §3 bước 1–6)
```bash
W=model/worker; PY=$W/.venv/Scripts/python.exe; R=F:/vcf_ext/nusc_pilot/root; J=F:/vcf_ext/nusc_pilot/job
$PY -m c4.cli.adapt --dataset av2 --src F:/vcf_ext/av2/src --out F:/vcf_ext/av2/root   # chỉ AV2/PandaSet
$PY -m c4.cli.lidar_index --data-root $R --job-dir $J
$PY -m c4.cli.bench_judge split --job-dir $J --seed 20261017 --dataset nuscenes-pilot
# thêm TẠM `override_file: $J/bench/engine_split_override.parquet` dưới `splits:` trong
# model/worker/configs/lidar.yaml, chạy lại lidar_index, rồi TRẢ file về nguyên trạng (không commit)
$PY -m c4.cli.lidar_index --data-root $R --job-dir $J
$PY -m c4.cli.bench_judge prereg --job-dir $J --file <planning/21_…/specs/SPEC-P04-PREREG-STATS.md>
$PY -m c4.cli.lidar_t0 --data-root $R --job-dir $J
python -I model/scripts/pack_judge_job.py --dataset nuscenes-pilot --job $J --root $R \
  --final-config <planning/11_…/evidence/M8/final_config.json> --repo-sha <sha> --out F:/vcf_pack/judge_bench/nuscenes-pilot
git archive --format=zip -o F:/vcf_pack/judge_bench/code_<sha>.zip <sha>
```
Pilot đo được: CAL (V) 120 kf · POOL (T) 321 kf · EVAL (P) 161 kf; split `8bbee0bf…`; prereg khớp `4b8ef249…`; `lidar_t0` 602/602; gói 3 part, 5,07 GB, sha `f86d658f…`, 14 337 file.

Bố cục gói (giải nén vào `JOB_DIR` trên Colab): nội dung job (`bench/ gt/ index/ lidar/ media/`) + `data_root/` + `final_config.json`. ZIP lưu thẳng (STORED), cắt theo byte thành `pack_part_NNN.bin` ≤ 1,9 GB; `manifest.json` ghi `parts`, sha từng part, sha cả gói, `prereg_sha256`, `split_sha256`, `repo_sha`.

### 5.3. Đưa lên Drive (người làm, tài khoản Colab authuser=2)
```text
MyDrive/vcf_judge/
├── code_<sha>.zip
└── <DATASET>/            (nuscenes-pilot | pandaset | av2)
    ├── manifest.json
    └── pack_part_*.bin
```
Connector Google Drive của agent đăng nhập tài khoản khác nên agent không tự upload được. Phương án tự động: `rclone` + đăng nhập một lần (chưa cài).

### 5.4. Chạy trên Colab
1. Nối Colab MCP theo [colab-mcp.md](colab-mcp.md) §3; chép notebook repo (bản đã sửa) lên `benchmark_2`.
2. Ô 1: `DATASET`, `REPO_SHA=<sha>` (phải có `code_<sha>.zip` trên Drive), giữ `RUN_POOL=False`.
3. Chạy ô 0–6 (ô 4b chuẩn bị đầu vào: trọng số, extract_clip, context cv/fit/run, rare lidar_only → crops, DINO, YOLO; giống chuỗi `prepare` của lần chạy T pitch-v2, cluster_only) ⇒ select (băm `selections_sha256`) + giám khảo CAL + `power.json`. **Commit `selections_sha256` + `judge_calib.json` vào BuildLab TRƯỚC** khi bật `RUN_POOL=True` và chạy ô 7–11.
4. Kéo `results_bundle.zip` về, chạy notebook thẩm định trên CPU.

### 5.5. Lỗi đã gặp
| Hiện tượng | Nguyên nhân | Đã xử lý |
|---|---|---|
| Ô 5 chắc chắn dừng `MISSING_INPUT` | notebook không truyền `--data-root/--final-config/--dataset` cho select/judge/report | sửa `94be150`: ô 1 thêm `DATA_ROOT`, `FINAL_CONFIG` |
| Ô 5 (sau `94be150`) dừng `MISSING_INPUT: cache/context_frame.parquet, cache/rare_crops.npy …` (đo 2026-10-17 trên A100) | gói chỉ có `lidar/ index/ gt/ media/`; OURS (multisensor) cần cache bối cảnh + crop OpenCLIP, X1/N1/N2 cần DINO, X2/X3 cần YOLO, mà notebook không có bước sinh | thêm ô 4b vào notebook; lần đầu ô 4b còn lỗi exit 4 thiếu trọng số OpenCLIP ⇒ ô 4b gọi `model/scripts/fetch_weights.py` trước |
| Ô 6: `select --split cal --exploratory` ⇒ `ORDER_VIOLATION` exit 3 (đo 2026-10-17) | lệnh chưa được cài: `select` bỏ qua `--split`, không code nào ghi `power.json` | cài nhánh CAL: chọn đủ 9 bên trên CAL (OURS/M2 `pool_split=V`, in-sample, nhãn exploratory) ⇒ `bench/cal/selections_cal.json` + `power.json` (MDE = 2,8·SE(D_JA)·√(scene CAL/scene POOL)); POOL đã mở ⇒ từ chối; `selections.json` không bị chạm. Test `tests/bench/test_bench_power.py` |
| `selections.json.repo_sha` rỗng | CLI đọc git, mà `code_<sha>.zip` không có `.git` | ô 2 đặt `VCF_REPO_SHA`; CLI đọc biến này trước |
| AV2 150 log: `adapt` exit 3 `PROJ_FAIL` sau 198 s | log `15ec0778…` chỉ 73,9 % hộp xe thẳng trục (ngưỡng §6.6 ≥ 80 %). Đo cả 150 log (`model/scripts/diag_av2_axis.py`, 5,5 phút): 6 log < 80 %, nhưng hướng hộp khớp hướng di chuyển của chính xe (trung vị 1,34°, log tệ nhất 4,3°) và ở bước này điểm + hộp đều là hệ ego gốc AV2 ⇒ PCA lệch do chỉ thấy một mặt xe, adapter không sai | `f92cb68`: §6.6 tính trên cả bộ đúng chữ SPEC (gộp 92,5 % / 67 995 hộp), ghi từng log; thêm §6.8 hướng hộp vs hướng di chuyển < 10°/log. Ngưỡng 80 % giữ nguyên, không bỏ log |
| AV2 log `04994d08` lấy `ring_rear_right` làm `CAM_BACK` | quy tắc chọn camera theo yaw đo từ calib từng log | đúng SPEC-P01 §4, không phải lỗi |
| AV2 ô 5 `select` chạy ~4 h | `novelty_knn` (`c4/mining/novelty.py`) O(N²) numpy CPU trên 951 663 crop; `select --split cal --exploratory` chạy lại một lần nữa | chấp nhận, KHÔNG sửa engine giữa benchmark (config/sha đóng băng) |
| AV2 ô 6 exit 4 `JUDGE_INVALID ['JA','JB']` (2026-10-18) | V1: recall vật dễ 0,845 / 0,866 < 0,90 dù τ ở sàn 0,05, IoU 0,3; V2 2,79 / 2,43, κ 0,72 đạt. ~95 % vật dễ bị sót là người đi bộ, khung gần nhất cao 32–46 % hộp GT, cặp khớp lệch tâm ≈ 0 ⇒ không phải lỗi chiếu; nghi che khuất (định nghĩa "dễ" không xét) | đúng luật SPEC-P03 §8: benchmark dừng, POOL KHÔNG mở, không đổi τ/IoU/định nghĩa. Muốn chạy tiếp ⇒ hồ sơ mới, đăng ký lại trước POOL |

## 6. Trạng thái (2026-10-18 06:40)
- ✅ Thiết kế + prereg, ✅ code + test; notebook ô 4b `9b2bd4c`, power `394f70a`, adapter AV2 `f92cb68`, LF `661876f`.
- G2 pilot nuScenes: chạy hết tới bundle (nhãn chạy khô, không kết luận); ⬜ thẩm định CPU.
- G6 AV2 150 log: adapt + chuẩn bị + select (`04dbbd1c…`, B 132 / POOL 2 630) xong; ⛔ dừng ở cổng giám khảo `JUDGE_INVALID` (calib `9fe4dd6e…`). POOL chưa mở ⇒ chưa có số D/SY trên AV2.
- ⬜ PandaSet · ⬜ Pha 4 · ⬜ thẩm định đối kháng.
- Mọi con số phải đi kèm sha prereg/selections và output của notebook thẩm định.

Slide trình bày (10 trang): [slides/judge-bench.pptx](slides/judge-bench.pptx).

Liên quan: [colab-mcp.md](colab-mcp.md) (điều khiển notebook bằng agent) · [colab-dev-setup.md](colab-dev-setup.md).
