# Benchmark giám khảo độc lập (judge-bench)

Câu hỏi duy nhất: **với cùng một kho ảnh và cùng ngân sách B, lô ảnh VCuboidFIT chọn có làm một model nhận diện AEB (Autonomous Emergency Braking – phanh khẩn cấp tự động) *độc lập* bỏ sót vật có thật nhiều hơn lô của bên thứ 3 không? Và huấn luyện thêm trên lô đó có giúp model ấy tốt hơn không?**

Giá trị của lô ảnh được đo bằng model *của người khác*, không bằng thước của chính mình. Thiết kế đầy đủ (SPEC, prereg, handoff, evidence) ở hồ sơ quản trị `planning/21_2026-10-17_external-judge-bench/` trong workspace BuildLab. Trang này là bản tóm tắt cho developer, cập nhật 2026-10-18 sau lần chạy Argoverse 2.

## 1. Thiết kế trong một hình

```text
Argoverse 2 Sensor VAL ──adapter──► data-root dạng nuScenes (6 camera, ảnh 1600×900)
        │ chia tất định theo tên log: CAL 20 % · POOL 55 % · EVAL 25 %
        ▼
 POOL ──► mọi bên chọn B = ⌈5 % × N_POOL⌉ khung
        │ (OURS · X0 random×100 · X1 k-center DINOv2 · X2 uncertainty YOLO11m · X3 đếm đông · N1 mờ · N2 tối)
        │ selections.json + sha256 ⇐ commit TRƯỚC khi giám khảo chấm POOL
        ▼
 CAL ──► giám khảo JA (Faster R-CNN v2) + JB (RT-DETR): hiệu chỉnh τ, iou_thr, kiểm hợp lệ V1–V3
 POOL ─► chấm toàn bộ một lần ⇒ vật GT AEB nào bị "struggle" (bỏ sót)
        ▼
 SY@B, D = SY(OURS) − max(X1, X2, X3), CI bootstrap theo log, Holm ⇒ report
 EVAL ─► Pha 4 (chưa chạy): fine-tune JA trên từng lô, đo AP50 VRU
```

## 2. Dữ liệu chấm: Argoverse 2, không phải nuScenes

- **nuScenes không dùng để chấm.** Đó là dữ liệu nhóm dùng để xây và chỉnh engine (config `final_config.json` sha `e4cdde32…`). Chấm trên đó là "thi lại đúng đề đã ôn". 15 scene nuScenes chỉ dùng để chạy thử quy trình (pilot, mục 6.3), không đưa lên slide.
- **Argoverse 2 Sensor** (Argo AI; Wilson và cộng sự, NeurIPS 2021 Datasets & Benchmarks; CC BY-NC-SA 4.0, chỉ nghiên cứu). Theo bài báo: 1 000 đoạn lái ~15 giây (700 train / 150 val / 150 test), 6 thành phố Mỹ, 7 camera vòng 2048×1550 + 2 camera stereo, 2 LiDAR, hộp 3D cho 26 loại vật. *Các số này lấy theo bài báo, không đo trong repo; `log.json` sau adapter không giữ tên thành phố.*
- **Phần dùng:** toàn bộ 150 log VAL (test không có nhãn công khai): 4 806 keyframe, 28 831 ảnh, 345 259 hộp 3D. Tải chọn lọc 35,65 GB / 57 783 file (đủ bộ 166 GB).
- **Chuẩn hoá ảnh (SPEC-P01 §4):** chọn 6/7 camera theo yaw danh nghĩa nuScenes (thường bỏ `ring_rear_right`), cắt 16:9 quanh tâm quang học, resize 1600×900. Giám khảo và mọi selector đọc **cùng một file ảnh** (sha trong `media_manifest.parquet`). Không dùng Waymo vì license cấm đánh giá hiệu năng xe thật.
- **Kiểm chuyển đổi (G5):** 96,8 % hộp xe gần đạt kiểm phép chiếu; 99,99 % xe dài > rộng; 92,5 % hộp thẳng trục LiDAR (67 995 hộp, ngưỡng ≥ 80 % tính trên cả bộ, D21); trung vị lệch hướng hộp vs hướng xe chạy 1,34°.

### 2.1. Ba phần rời nhau (split `6cb43cf3…`, seed 20261017, sha1 tên log)
| Phần | Ý nghĩa | Khung AV2 | Dùng cho |
|---|---|---|---|
| **CAL** (Calibration – hiệu chỉnh), engine `V` | "bài thi thử" | 960 | hiệu chỉnh τ/iou_thr + kiểm V1–V3 của giám khảo; engine fit thống kê tham chiếu **không nhãn**; `power.json` |
| **POOL** (kho ảnh để chọn và chấm), engine `T` | "bài thi thật" | 2 630 | mọi bên chọn B = 132; giám khảo chấm một lần; mọi số kết quả |
| **EVAL** (Evaluation – đánh giá), engine `P` | để dành | 1 216 | Pha 4; chưa mở |

Một log chỉ thuộc một phần. Chia trước khi nhìn nội dung.

## 3. Hai giám khảo và metric
| | JA (Judge A) | JB (Judge B) |
|---|---|---|
| Model | `torchvision fasterrcnn_resnet50_fpn_v2`, COCO_V1 | `PekingU/rtdetr_r50vd` (Hugging Face) |
| Họ | CNN hai bước (Region-based CNN) | transformer (Real-Time DEtection TRansformer) |
| Ngưỡng box | score ≥ 0,05, ≤ 300 hộp/ảnh | threshold 0,05 |

Cả hai huấn luyện sẵn trên COCO, không ai trong dự án train/fine-tune. Lớp ánh xạ theo **tên**: `person, bicycle, motorcycle → vru`; `car, truck, bus → vehicle`.

- **Vật AEB:** VRU (Vulnerable Road User – người đi bộ, xe đạp, xe máy) ≤ 40 m, và xe trong hành lang `0 < x ≤ 40 m`, `|y| ≤ 2 m`; ≥ 1 điểm LiDAR, hộp 2D cao ≥ 20 px, một camera/vật.
- **Struggle (bỏ sót):** không có detection cùng nhóm với IoU (Intersection over Union) ≥ `iou_thr` và score ≥ τ.
- **Hiệu chỉnh trên CAL:** `iou_thr` thử 0,5 → 0,4 → 0,3; τ = ngưỡng lớn nhất giữ recall vật dễ ≥ mục tiêu (prereg 0,90).
- **Kiểm hợp lệ:** V1 tìm được (iou_thr, τ) · V2 tỉ lệ bỏ sót khó/dễ ≥ 2 · V3 Cohen's κ (kappa) JA–JB ≥ 0,20.
- **SY@B** (Struggle Yield) = số vật khác nhau bị bỏ sót trong lô / B (có thể > 1).
- **Luật thắng (prereg `judge-bench-v1`, sha `4b8ef249…`):** cận dưới CI95 của D > 0 với mọi giám khảo hợp lệ, và OURS thắng X0, N1, N2 sau Holm. Không đạt ⇒ "chưa chứng minh ở cỡ mẫu này".

## 4. Vì sao làm như vậy
| Rủi ro | Cách chặn | Nguồn |
|---|---|---|
| Thước tự chế, sân nhà | Giám khảo là model công khai không ai trong dự án train | DataComp (Gadre 2023) |
| "Khó" bị ăn gian bằng ảnh mờ/tối/rỗng | Chỉ đếm vật GT thật; N1/N2 phải thua | CODA (Li 2022) |
| Giám khảo thiên vị họ model gần nó | 2 giám khảo khác kiến trúc, thắng phải đúng với cả hai | self-preference bias |
| Baseline yếu ⇒ thắng giả | random ×100 + k-center + uncertainty + đếm đông, cùng B | DeepCore 2022, Mittal 2019, Lüth 2023 |
| Tune trên test | Engine giữ config nuScenes; prereg băm trước; POOL/EVAL mở một lần | — |
| Bỏ sót ≠ có ích | Pha 4 train-on-selection | AL 3D nuScenes (Liang 2022) |

## 5. Code và lệnh
| Thành phần | Đường dẫn |
|---|---|
| Lõi: split, cổng, registry, vật AEB, metric | `model/worker/c4/bench/{split,gate,registry,aeb,metrics}.py` |
| Bọc engine / bên thứ 3 / giám khảo / Pha 4 | `c4/bench/{ours,thirdparty,judge,train_sel}.py` |
| Dashboard, helper Colab | `c4/bench/{dashboard,colab}.py` |
| Adapter dữ liệu ngoài | `c4/data/adapters/{pandaset,av2,common}.py`, CLI `python -m c4.cli.adapt` |
| CLI benchmark | `python -m c4.cli.bench_judge split\|prereg\|select\|judge\|report\|train-eval --job-dir J` |
| Notebook Colab A100 | `model/notebooks/vcf_judge_bench_colab.ipynb` |
| Notebook thẩm định CPU (không import `c4`) | `model/notebooks/vcf_judge_bench_review.ipynb` + `judge_bench_review_core.py` |
| Test | `model/worker/tests/bench/`, `tests/test_adapt_*.py`, `tests/test_splits_override.py` |

Thứ tự bắt buộc (sai ⇒ exit 3): `adapt → lidar_index → split → prereg → select (băm) → judge cal → judge pool (một lần) → report → train-eval`.

Mã thoát: 0 ok · 2 thiếu đầu vào · 3 vi phạm thứ tự/hash/đã mở · 4 giám khảo không hợp lệ · 5 hết VRAM.

**Lệch prereg có ghi (`e0642f1`):** `bench_judge judge --split cal --target-recall-easy X`. Khác 0,90 ⇒ ghi `bench/prereg_deviation.json` (field, prereg, used, created_at, repo_sha); `report` thấy file này ⇒ nhãn `exploratory` và nối câu "Lệch prereg: … ⇒ exploratory." vào `verdict.text`. Mặc định vẫn 0,90.

## 6. Quy trình đã chạy

### 6.1. Lấy dữ liệu
| Bộ | Lệnh | Kết quả đo |
|---|---|---|
| Argoverse 2 VAL | `python -I model/scripts/fetch_av2_val.py --out F:/vcf_ext/av2/src --workers 32` (S3 công khai, tải tiếp được) | 150 log, 57 783 file, 35,65 GB, 68 phút ~8,6 MB/s; Colab tải lại từ S3: 4,4 phút |
| nuScenes pilot | `python -I model/scripts/subset_nusc.py --src E:/nuscenes_trainval --version v1.0-trainval --scenes scene-1059..scene-1073 --out F:/vcf_ext/nusc_pilot/root` | 15 scene, 602 kf, 4,87 GB |
| PandaSet | trang chính thức cần form | chưa có |

### 6.2. Chuẩn bị job
```bash
W=model/worker; PY=$W/.venv/Scripts/python.exe; R=<data_root>; J=<job_dir>
$PY -m c4.cli.adapt --dataset av2 --src F:/vcf_ext/av2/src --out $R
$PY -m c4.cli.lidar_index --data-root $R --job-dir $J
$PY -m c4.cli.bench_judge split --job-dir $J --seed 20261017 --dataset av2
# thêm TẠM `override_file: $J/bench/engine_split_override.parquet` dưới `splits:` trong
# model/worker/configs/lidar.yaml, chạy lại lidar_index, rồi trả file về nguyên trạng (không commit)
$PY -m c4.cli.lidar_index --data-root $R --job-dir $J
$PY -m c4.cli.bench_judge prereg --job-dir $J --file <planning/21_…/specs/SPEC-P04-PREREG-STATS.md>
$PY -m c4.cli.lidar_t0 --data-root $R --job-dir $J
```
AV2 trên Colab (`/content/av2_prep.sh`, 12 vCPU): adapter 3 906 s · index 443 s · split 150 log · index2 V 960 / T 2 630 / P 1 216 · prereg khớp `4b8ef249…` · t0 4 806/4 806.

### 6.3. Chạy trên Colab (notebook `benchmark_2`)
1. Nối Colab MCP theo [colab-mcp.md](colab-mcp.md) §3. Nếu server mở nhầm notebook khác: sửa ID notebook trong URL tab đó thành ID của `benchmark_2`, **giữ nguyên** đoạn `#mcpProxyToken=…`, bấm Connect.
2. Ô 1: `DATASET=av2`, `REPO_SHA`, giữ `RUN_POOL=False`. Khi Drive không mount được: lấy code qua codeload GitHub theo sha, log ghi local.
3. Ô 4b (chuẩn bị đầu vào), ô 5 `select` ⇒ commit `selections_sha256` vào BuildLab; ô 6 `judge --split cal` ⇒ commit `judge_calib.json`; rồi mới bật `RUN_POOL` và chạy ô 7–8.

Lần chạy AV2 (2026-10-18, code `e0642f1`):
| Bước | Kết quả | Evidence (BuildLab `planning/21_…/evidence/G6/`) |
|---|---|---|
| Lần 1 select | `04dbbd1c…`, B 132, POOL 2 630, ~4 h | `03_colab_select_pool.txt` |
| Lần 1 judge CAL | exit 4 `JUDGE_INVALID`: recall vật dễ 0,845 / 0,866 < 0,90 (τ sàn 0,05, IoU 0,3) | `04_…`, `05_v1_fail_diagnosis.txt` |
| Người quyết D23 | hạ mục tiêu recall vật dễ xuống 0,84, ghi lệch, nhãn exploratory | plan.md D23 |
| Lần 2 select (runtime bị thu hồi, dựng lại từ S3) | `717db94c…`, ~20 phút nhờ vá GPU (6.4) | `06_colab_select_pool_rerun.txt` |
| Lần 2 judge CAL @0,84 | JA τ 0,06 recall 0,8415 · JB τ 0,12 recall 0,8421 · IoU 0,3 · V2 2,77 / 2,54 · κ 0,797; calib `86588b62…` | `07_colab_judge_cal_084.txt` |
| POOL + report | report `533d6a16…`, nhãn exploratory, κ POOL 0,797 | `08_colab_pool_report.txt` |

### 6.4. Vá tăng tốc chỉ trên Colab (engine/repo không đổi)
`/content/vcf_gpu/vcf_gpu_novelty.py` + file `.pth` trong site-packages, bật bằng `VCF_NOVELTY_GPU=1` và `VCF_FAST_CROPS=1`, áp cả cho tiến trình con.
| Bước | CPU (engine) | Vá GPU | Kiểm khớp |
|---|---|---|---|
| `novelty_knn` (O(N²), 951 663 crop) | ~4 h/lần select | select ~20 phút | max \|Δnov\| 2,38e-7 so với CPU (float32, tắt TF32) |
| Cắt crop (ô 4b) | 3 870 s | 1 952 s (song song) | ảnh giống từng pixel bản tuần tự |

### 6.5. Lỗi đã gặp
| Hiện tượng | Nguyên nhân | Đã xử lý |
|---|---|---|
| Ô 5 dừng `MISSING_INPUT` | notebook không truyền `--data-root/--final-config/--dataset` | `94be150` |
| Ô 5 thiếu `cache/context_frame.parquet`, crop, DINO, YOLO | gói chỉ có `lidar/ index/ gt/ media/` | ô 4b (`9b2bd4c`), gọi `fetch_weights.py` trước |
| Ô 6 `select --split cal --exploratory` ⇒ exit 3 | nhánh CAL chưa cài, không ghi `power.json` | `394f70a`, test `test_bench_power.py` |
| `selections.json.repo_sha` rỗng | `code_<sha>.zip` không có `.git` | đặt `VCF_REPO_SHA` |
| AV2 `adapt` exit 3 `PROJ_FAIL` | 6/150 log < 80 % hộp thẳng trục do PCA thấy một mặt xe | `f92cb68`: gate trên cả bộ + kiểm hướng chuyển động |
| sha JSON adapter khác giữa Windows và Colab | ghi CRLF trên Windows | `661876f`: luôn LF |
| AV2 `JUDGE_INVALID` V1 | ~95 % vật dễ bị sót là người đi bộ bị che phần dưới; định nghĩa "dễ" không xét che khuất; chiếu hộp đúng (lệch tâm ≈ 0) | dừng đúng luật (D22); người quyết 0,84 có ghi lệch (D23) |
| Runtime Colab bị thu hồi sau ~3,5 h rảnh | mất toàn bộ `/content` | dựng lại từ S3 cùng lệnh; sha dữ liệu khớp lần 1 |
| Mount Drive "mount failed" | người chưa duyệt hộp thoại | lấy code từ codeload, log local |
| MCP huỷ lệnh sau 1 800 s rảnh | timeout công cụ, ô vẫn chạy | đọc tiến độ bằng `get_cells` |
| Reload trang Colab mất ô vừa thêm | ô chưa lưu | thêm lại ô; file vá trên đĩa còn nguyên |

## 7. Kết quả Argoverse 2 (report `533d6a16…`, nhãn exploratory)

SY@B, B = 132, POOL 2 630:
| Cách chọn | JA | JB |
|---|---|---|
| **OURS** (rare_v24 multisensor) | **0,970** | **1,000** |
| X0 ngẫu nhiên (TB 100 seed) | 0,921 | 0,943 |
| X3 đông người | 0,909 | 0,932 |
| X1 k-center DINOv2 | 0,803 | 0,765 |
| X2 YOLO phân vân | 0,455 | 0,492 |
| N2 ảnh tối | 0,280 | 0,273 |
| N1 ảnh mờ | 0,212 | 0,197 |
| *M2 / M1 (bản cũ của nhóm, không thuộc phép so)* | *0,909 / 0,636* | *1,023 / 0,636* |

- **D (OURS − max X1..X3):** JA +0,061 [−0,210; +0,268] · JB +0,068 [−0,258; +0,336] ⇒ CI chứa 0.
- **Chắc chắn:** OURS > N1 (+0,76 / +0,80), N2 (+0,69 / +0,73), X2 (+0,52 / +0,51), p_Holm ≤ 0,006 với cả hai giám khảo.
- **Chưa chắc:** OURS − X1 +0,17 / +0,23 (p_Holm 0,399 / 0,174); OURS − X0 +0,05 (p_Holm 1,0).
- **Verdict nguyên văn:** "Chưa chứng minh vượt bên thứ 3 ở cỡ mẫu này: Δ = JA: 0.0606 [-0.2096; 0.2683]; JB: 0.0682 [-0.2583; 0.3362] Lệch prereg: judge.target_recall_easy 0.9 → 0.84 sau khi xem CAL ⇒ exploratory."

Pilot nuScenes (chạy thử, không kết luận, report `120e3e26…`): POOL 321, B 17, OURS 0,529 / 0,412 vs X0 0,394 / 0,342; p_Holm nhỏ nhất 0,252; MDE 0,36.

## 8. Trạng thái (2026-10-18)
- ✅ Thiết kế + prereg · ✅ code + test · ✅ pilot nuScenes tới bundle · ✅ AV2 150 log tới report (exploratory).
- ⬜ Thẩm định CPU độc lập · ⬜ PandaSet · ⬜ Pha 4 · ⬜ thẩm định đối kháng.
- Mọi con số phải đi kèm sha prereg/selections/calib/report ở trên.

## 9. Việc để bản V2 (kỳ sau — KHÔNG làm trong hồ sơ 21)
- **`novelty_knn` chạy GPU trong engine** (`c4/mining/novelty.py`, gọi từ `c4/rare/semantic.py`), có cờ bật/tắt, mặc định CPU cho Azure lite; test so khớp CPU↔GPU (max |Δnov|, hạng pct_rank); đo lại select AV2. Cắt crop song song cũng đưa vào engine theo cùng cách.
- **Định nghĩa "vật dễ" có che khuất** (SPEC-P03 §4) và đăng ký lại mục tiêu recall trước khi mở POOL; thêm log để thu hẹp CI.
- **Notebook:** sao lưu `bench/` + `cache/` lên Drive sau mỗi bước dài (runtime bị thu hồi sau ~3,5 h rảnh).

## 10. Slide và kịch bản
- Deck trình bày hội đồng (14 slide, ~11,5 phút): https://claude.ai/artifact/G9wVTB5bF6wXUYfXCRZSwU — cover · method · imageset (ảnh chấm là AV2) · av2intro · splits (CAL/POOL/EVAL) · ours · metrics · judgeintro · judges · rivals · data · guards · av2chart · av2. Bản `.pptx` trong `docs/slides/` là bản cũ 2026-10-17, tải lại từ deck.
- Kịch bản nói và hỏi đáp dự phòng: [judge-bench-script.md](judge-bench-script.md).
- Quy ước slide: mọi chữ viết tắt mở ngoặc ở lần đầu; ngưỡng 0,84 luôn ghi kèm "đăng ký trước 0,90, nhãn thăm dò".

## 11. Chữ viết tắt
| Viết tắt | Nghĩa |
|---|---|
| AEB | Autonomous Emergency Braking – phanh khẩn cấp tự động |
| VRU | Vulnerable Road User – người đi bộ, xe đạp, xe máy |
| CAL / POOL / EVAL | Calibration – hiệu chỉnh / kho ảnh để chọn và chấm / Evaluation – đánh giá |
| JA / JB | Judge A / Judge B – hai giám khảo |
| SY@B | Struggle Yield – số vật bị bỏ sót trên mỗi khung của lô B khung |
| D | SY(OURS) − max(X1, X2, X3) |
| IoU | Intersection over Union – độ trùng hai hộp |
| τ (tau) | ngưỡng độ tin cậy của giám khảo |
| κ (kappa) | Cohen's kappa – độ đồng thuận đã trừ phần trùng ngẫu nhiên |
| CI95 | khoảng tin cậy 95 % (bootstrap theo log, 2 000 lượt) |
| MDE | Minimum Detectable Effect – chênh lệch nhỏ nhất cỡ mẫu phát hiện được |
| MMR | Maximal Marginal Relevance – cân bằng điểm cao và đa dạng |
| OOD | out-of-distribution – ngoài phân phối |
| prereg | đăng ký trước (luật kết luận băm sha256 trước khi mở dữ liệu) |
| log / scene | một đoạn lái liên tục |

Liên quan: [colab-mcp.md](colab-mcp.md) · [colab-dev-setup.md](colab-dev-setup.md) · [glossary.md](glossary.md).
