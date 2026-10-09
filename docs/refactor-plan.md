# Kế hoạch sửa code và chuẩn hoá tên – VCuboidFIT

Tài liệu này là **kế hoạch**, chưa có dòng code nào được sửa. Nó gồm: (1) quy trình sửa, (2) các lỗi
logic phải sửa trước, (3) các thay đổi cấu trúc, (4) bảng đổi tên file và hàm kèm lý do, (5) cách
kiểm tra sau mỗi bước.

## Tiến độ thực hiện

Đã làm trong working tree (chưa commit); `pytest -m "not perf and not gpu" tests` cho 303 pass, 5 skip.

| Mục | Trạng thái | Ghi chú |
|---|---|---|
| 2.1 Chuẩn hoá MMR | Xong | `select_mmr` bắt buộc `score_norm`; mọi chỗ gọi lấy từ `cfg["mmr_score"]`; thêm test AST `test_every_select_mmr_call_passes_score_norm` |
| 2.2 Pool của web | Xong, **khác kế hoạch** | Tầng 1 loại frame seed S khỏi ứng viên và khỏi ngân sách B (`pool_mask`); Tầng 0 vẫn dùng toàn bộ dữ liệu. Không lọc cứng theo P vì bộ demo vài scene sẽ chỉ còn rất ít scene hoặc không còn scene nào trong P, làm Rarity "khác scene" suy biến |
| 2.3 Nhãn Tầng 1 | Xong, chưa thử trên GPU | `infos_index` không còn khoá nhãn (`strip_labels`, `verify_index_label_free`, có test). Bundle gửi Colab (`service/remote.py`) chỉ giữ `sample_annotation.json` của frame S và T, có test. Lưu ý: file này được đọc cả vào RAM nên với trainval đầy đủ sẽ nặng; chưa chạy thử với OpenPCDet thật |
| 2.4 Tách chọn mẫu và chấm điểm | Xong | `web_selection.py` (label-free, nằm trong danh sách của test chống rò rỉ), `web_scoring.py` (đọc nhãn), `web_run.py` (ghép hai phần) |
| 2.5 Metric trên giao diện | Xong (phương án nhẹ) | Thêm cảnh báo `METRICS_NOTE` vào `warnings` của kết quả khi có metric từ nhãn (`web_scoring.py`); chưa ẩn metric |
| 2.5 Mã camera | Xong (phương án nhẹ) | Xem dòng 3.3. Đính chính: pipeline mặc định khi tạo job đã là `lidar` nếu dữ liệu có LiDAR; `camera` trong `runner.py` chỉ là mặc định cho job cũ chưa ghi `pipeline`, nên không đổi |
| 3.4 Thư mục tài liệu | Xong | `docss/` → `docs/design/` với tên file mới; các tham chiếu `planning/`, `SPEC-P0x` trong comment **chưa** sửa vì không có tài liệu nguồn để trỏ tới |
| 3.3 Mã camera | Xong (phương án nhẹ) | 14 file test camera chuyển sang `tests/legacy_camera/`, tự gắn marker `legacy`; `pytest -m "not legacy"` chạy riêng phần LiDAR (242 pass). Chưa xoá mã `c4/extract`, `c4/mining`, `c4/pipeline`, `c4/eval` |
| 3.2 Agent ra khỏi `scripts/` | Chưa làm | `colab_agent.py` do dev vừa sửa nhiều ở v0.6.2, nên để sau để tránh xung đột |
| 4 Đổi tên | Xong nhóm A và hầu hết nhóm B | Xem danh sách dưới |

Đã đổi tên: `pipeline.py`→`web_selection.py`, `eval.py`→`evaluation.py`, `select.py`→`selectors.py`,
`score.py`→`scoring.py`, `uncertainty.py`→`t1_signals.py`, `mining/mmr.py`→`lidar/mmr.py`;
`run_selection_lidar`→`run_lidar_selection`, `tier_available`→`available_tiers`,
`schema`→`params_schema_for_job`, `l2n`→`l2_normalize`, `_cp`→`_count_pct`, `first_B`→`top_b_tokens`,
`delta_t`→`redundancy_window_s`, `combine`→`combine_scores`, `stack`→`stack_block_vectors`,
`embed`→`embed_descriptors`, `signals`→`compute_t1_signals`, `scores_for`→`score_pool`.

Notebook: ba file (`vcf_tier01_kaggle_colab`, `vcf_colab_agent`, `vcf_dev_setup_colab`) được gộp thành
**một** `model/notebooks/run_on_colab.ipynb`. Lý do: `vcf_dev_setup_colab` đã chứa Tầng 0, Tầng 1 và chế
độ agent, `vcf_colab_agent` chỉ là bản rút gọn của chính ô đó, và notebook thí nghiệm lặp lại phần cài
môi trường; ba tên cũng khó phân biệt. Notebook mới nạp dữ liệu bằng `SOURCE_URL` (Colab tự tải, không
phải upload từ máy), file trong `Drive/vcf_upload` hoặc nút upload; cài môi trường bằng
`scripts/colab_setup.sh` (cache bản build OpenPCDet trên Drive); chế độ agent là phần 9. README và
`docs/` đã cập nhật. Nút "Open in Colab" ở README trỏ vào nhánh `main` nên chỉ mở được sau khi merge.

Chưa đổi (có chủ ý): `pct_rank`, `criterion`, `fmt_table`, `oracle`, `reasons`, `budget`, `Truth`, `Pool`,
`index.py`, `params.py`, tên CLI `lidar_t0`/`lidar_g1`, (nhóm C).
Trường `tier_available` trong `service/models.py` được **giữ nguyên** vì nó sinh ra khoá JSON
`tierAvailable` của hợp đồng với web; lần đổi tên đầu tiên đã làm vỡ khoá này và test bắt được.

Căn cứ đối chiếu: `docs/design/c4-design-detail.pdf` (trước là `docss/T07_Buildphase_Document_final.pdf`, thiết kế chi tiết) và
`docs/design/tier0-tier1-overview.pdf` (trước là `docss/thiet keTang0_Tang1_VCuboidFIT.pdf`, bản thuyết trình Tầng 0/Tầng 1), so với code trong
`model/worker/c4/lidar`, `model/worker/service`, `model/worker/configs`.

---

## 1. Quy trình sửa (làm đúng thứ tự này)

Nguyên tắc: **sửa hành vi trước, đổi tên sau, mỗi loại một commit riêng.** Nếu trộn lẫn thì khi một
test hỏng sẽ không biết do đổi tên hay do đổi logic, và `git blame` mất giá trị.

| Bước | Việc | Cách làm | Điều kiện qua bước |
|---|---|---|---|
| 0 | Chốt mốc | Commit hoặc stash thay đổi dang dở (hiện `train_seed.py` đang sửa dở, chưa commit). Tạo nhánh `refactor/lidar-structure` | `git status` sạch |
| 1 | Chạy test nền | `cd model/worker` rồi `pytest -q -m "not perf and not gpu" tests/lidar tests/service` | Toàn bộ pass (hiện: 80 pass, 1 skip với nhóm `tests/lidar` + `test_mmr/score/uncertainty`) |
| 2 | Sửa lỗi logic (mục 2) | Mỗi lỗi một commit, kèm một test mới tái hiện lỗi | Test mới fail trước khi sửa, pass sau khi sửa |
| 3 | Đổi cấu trúc (mục 3) | Dùng `git mv` để giữ lịch sử file | Test pass, không đổi hành vi |
| 4 | Đổi tên (mục 4) | Đổi theo từng nhóm nhỏ, mỗi nhóm một commit "rename only" | Test pass, `grep` tên cũ không còn kết quả |
| 5 | Cập nhật tài liệu, notebook, Docker | Xem danh sách "nơi tham chiếu ngoài Python" ở mục 5 | Notebook và Docker build vẫn chạy |
| 6 | Chạy lại thí nghiệm Tầng 0 trên V | `python -m c4.cli.lidar_experiment --split V --tune` | Kết quả khác bản cũ chỉ ở chỗ dự kiến (mục 2.1) |

Quy tắc commit: tiêu đề dạng `fix(lidar): ...` cho bước 2, `refactor(lidar): rename ...` cho bước 3-4.
Một commit đổi tên không được chứa thay đổi logic.

---

## 2. Lỗi logic cần sửa trước

### 2.1 Chuẩn hoá điểm cho MMR không nhất quán (ưu tiên cao nhất)

**Thiết kế nói gì:** `configs/lidar.yaml` chốt `mmr_score: minmax` (quyết định Q4). Run chính
`t0_rar_mmr` phải dùng đúng giá trị đó, và mọi phép tune, ablation, bootstrap phải đánh giá cùng
phương pháp với run chính.

**Code đang làm gì:** `select_mmr` có tham số `score_norm`, mặc định `"rank"`. Chỉ một số chỗ truyền
giá trị từ config.

| Vị trí | Truyền `score_norm` từ config? | Hậu quả |
|---|---|---|
| `experiment.py:137` `t0_rar_mmr` | Có | Đúng |
| `experiment.py:177` `tune()` | Không → `rank` | Bộ k/λ/m được chọn tối ưu cho phương pháp khác |
| `experiment.py:216` `ablation_blocks()` | Không → `rank` | Ablation khối A–E chạy trên phương pháp khác |
| `experiment.py:309` bootstrap `run_fn` | Không → `rank` | Khoảng tin cậy gắn nhãn `t0_rar_mmr` thực ra tính trên `rank`; tiêu chí "hơn Random" (mục 5.3) dựa vào khoảng này |
| `experiment.py:145,147,151` `t1_*`, `hybrid_mmr` | Không → `rank` | So sánh `hybrid_mmr` với `t0_rar_mmr` (giả thuyết H3) bị lẫn hai thay đổi |
| `pipeline.py:92` hybrid (web) | Có | Đúng |
| `pipeline.py:102` `t1_nov_mmr`, `t1_unc_mmr` (web) | Không | Lệch với dòng 92 |

**Cách sửa:** bỏ giá trị mặc định của `score_norm` trong `select_mmr` (bắt buộc truyền), hoặc đọc
`cfg["mmr_score"]` bên trong một hàm bọc duy nhất `select_mmr_for_run(...)`. Mọi nơi gọi đều đi qua
hàm này. Như vậy thêm một chỗ gọi mới mà quên truyền sẽ báo lỗi ngay, không âm thầm rơi về `rank`.

**Test cần thêm:** một test kiểm `tune`, `ablation_blocks`, bootstrap và `run_matrix` cùng gọi
`select_mmr` với cùng `score_norm` (mock `select_mmr` rồi so tham số nhận được).

**Hệ quả sau khi sửa:** phải chạy lại tune trên V, vì bộ tham số tốt nhất có thể đổi.

### 2.2 Web chọn trên cả tập S và T

**Thiết kế nói gì:** pool để chọn là P. S là tập seed đã có nhãn, T là tập test. Q1(a): cả hai tầng
chọn đúng B frame **từ P**.

**Code đang làm gì:** `lidar_index` gán S/V/P/T, nhưng `run_selection_lidar` (`pipeline.py:80-91`) đọc
toàn bộ `index.parquet`, tính B trên N của toàn bộ, và cho cả frame S/T làm ứng viên.

**Cách sửa:** lọc theo `split == "P"` (hoặc `"pool"` khi dữ liệu không phải nuScenes chuẩn) ngay sau
khi đọc index. Lưu ý với dữ liệu tuỳ ý, mọi scene là `pool` và Tầng 1 sẽ dừng với lỗi "split S rỗng".
Cần thông báo rõ trên giao diện: Tầng 1 chỉ chạy được trên dữ liệu có nhãn để lấy seed.

### 2.3 Ranh giới nhãn của Tầng 1 chỉ dựa vào quy ước

- `service/remote.py` (`bundle_stream`) gửi toàn bộ thư mục `data` sang Colab, trong đó có annotation
  của mọi frame.
- `train_seed.build_infos` dựng info kèm nhãn cho mọi scene rồi lọc về S; file
  `infos_index_*.pkl` dùng khi suy luận vẫn chứa nhãn của pool.
- Hiện chưa có dòng nào dùng chúng để huấn luyện, và `verify_written` đã kiểm tập train chỉ gồm S.
  Nhưng thiết kế cam kết "chỉ nhãn của S", và test AST không phủ module Tầng 1.

**Cách sửa:** (a) sinh info cho frame ngoài S với `test=True` (không có box); (b) bundle chỉ chứa
annotation của scene thuộc S; (c) thêm test kiểm `infos_index` không có `gt_boxes` cho frame ngoài S.

### 2.4 `pipeline.py` vừa chọn mẫu vừa chấm điểm

`c4/lidar/pipeline.py` import `eval` và đọc `gt_rare_lidar`. Test chống rò rỉ đang cho phép riêng file
này. Chưa rò rỉ vì điểm được tính trước khi đọc nhãn, nhưng không có test nào bảo vệ thứ tự đó.

**Cách sửa:** tách phần chấm (các dòng đọc `gt_path`, `ev.Truth`, `evaluate_runs`, `_web_metrics`,
tag `Rare GT`) sang một module riêng; `pipeline.py` chỉ chọn mẫu và đưa vào danh sách label-free của
`test_no_leakage_lidar.py`.

### 2.5 Việc cần bạn quyết định (không tự làm)

- **Metric hiện trên giao diện cho pool có nhãn:** mỗi lần chỉnh tham số, người dùng thấy Recall ngay.
  Điều này đi ngược quy tắc "chấm P đúng một lần". Chọn một trong hai: ẩn metric cho tới khi đóng
  băng tham số, hoặc giữ nhưng gắn cảnh báo "chỉ để minh hoạ, không dùng làm kết quả".
- **Pipeline camera cũ:** giữ lại hay xoá (mục 3.3).

---

## 3. Thay đổi cấu trúc

### 3.1 Tách chọn mẫu và chấm điểm (theo 2.4)

```text
c4/lidar/
  web_selection.py      # chọn 5% cho web (trước: pipeline.py), KHÔNG đọc nhãn
  web_scoring.py        # chấm bằng nhãn cho web (phần tách ra), thuộc nhóm "vùng chấm điểm"
```

### 3.2 Đưa mã ứng dụng ra khỏi `scripts/`

`model/scripts/colab_agent.py` (hơn 300 dòng, có logic giao thức, retry, heartbeat) là mã ứng dụng,
không phải script tiện ích. Đề xuất: `c4/remote/agent.py` và để `model/scripts/colab_agent.py` chỉ còn
vài dòng gọi `c4.remote.agent.main()`. Lợi ích: test được bằng pytest, và notebook không phải đổi
đường dẫn.

### 3.3 Mã camera cũ

Các phần sau thuộc pipeline camera, không dùng trong cấu hình chính (T07: camera không dùng):

- `c4/extract/{dino,det,clip,quality,base,fake}.py`, `c4/mining/*`, `c4/pipeline.py`, `c4/eval/metrics.py`,
  `c4/data/{rare_gt,project}.py`
- `configs/{base,rare_def,queries}.yaml`, `configs/profiles/`
- các test camera ở thư mục gốc của `tests/` (`test_stage_dino.py`, `test_stage_det.py`,
  `test_stage_clip.py`, `test_query.py`, ...)

Đề xuất theo thứ tự an toàn: (1) đổi mặc định của `runner.py` từ `camera` sang `lidar`; (2) chuyển các
test camera vào `tests/legacy_camera/` và đánh dấu `@pytest.mark.legacy`; (3) khi bạn xác nhận không
dùng nữa, xoá hẳn. Không xoá trong cùng lúc với bước đổi tên.

Lưu ý: `c4/mining/mmr.py` được `c4/lidar/select.py` dùng, nên phải chuyển nó ra trước khi xoá
`c4/mining/` (đề xuất: `c4/lidar/mmr.py`).

### 3.4 Tài liệu

- Gộp `docss/` vào `docs/design/` và đặt lại tên file (mục 4.3). Hiện `docss/` chưa được git theo dõi.
- Nhiều comment trong code trỏ tới `planning/04`, `SPEC-P01`, `SPEC-P02`, `01-CONTRACTS`, nhưng repo
  không có thư mục `planning/`. Hoặc đưa các tài liệu đó vào `docs/design/`, hoặc đổi comment trỏ về
  mục tương ứng trong PDF thiết kế.
- Cập nhật T07 hoặc code cho khớp nhau ở các điểm: mô tả Streamlit và script `01_build_index.py` (code
  thực tế là FastAPI + Next.js + `c4.cli.*`); tên file kết quả `selected_5pct.csv` (web đang ghi
  `selected.csv` gộp mọi baseline); số sweep (thuyết trình ghi 10, notebook dùng 1).

---

## 4. Bảng đổi tên

Tất cả mục dưới đây là **đề xuất**. Ưu tiên: **A** = nên làm vì đang gây nhầm hoặc va chạm, **B** = nên làm
cho dễ đọc, **C** = tuỳ chọn.

### 4.1 Tên file trùng nhau giữa các package

Cùng một tên xuất hiện ở nhiều nơi (`select.py`, `score.py`, `uncertainty.py`, `pipeline.py`,
`index.py`, `params.py`), nên khi đọc stack trace hoặc import khó biết đang ở bản camera hay LiDAR.

| Hiện tại | Đề xuất | Ưu tiên | Lý do |
|---|---|---|---|
| `c4/lidar/pipeline.py` | `c4/lidar/web_selection.py` | A | Trùng `c4/pipeline.py` (camera); tên hiện không nói đây là luồng của web |
| `c4/lidar/select.py` | `c4/lidar/selectors.py` | B | Trùng `c4/mining/select.py` và `c4/cli/select.py`; file chứa nhiều bộ chọn (mmr, topk, random, coreset) |
| `c4/lidar/score.py` | `c4/lidar/scoring.py` | B | Trùng `c4/mining/score.py` |
| `c4/lidar/uncertainty.py` | `c4/lidar/t1_signals.py` | B | Trùng `c4/mining/uncertainty.py`; file còn chứa Novelty loader và `signals`, không chỉ uncertainty |
| `c4/lidar/eval.py` | `c4/lidar/evaluation.py` | A | Trùng tên package `c4/eval/`; `eval` còn là tên hàm dựng sẵn của Python |
| `c4/lidar/index.py` | `c4/lidar/keyframe_index.py` | C | Trùng `c4/data/index.py` |
| `c4/lidar/params.py` | `c4/lidar/selection_params.py` | C | Trùng `c4/params.py` |
| `c4/mining/mmr.py` | `c4/lidar/mmr.py` | A | LiDAR đang import từ package camera (`mining`); cần chuyển trước khi xoá `mining/` |

### 4.2 Tên hàm và class

| Hiện tại | Đề xuất | Ưu tiên | Lý do |
|---|---|---|---|
| `run_selection_lidar` (`pipeline.py`) | `run_lidar_selection` | B | Cùng kiểu động từ + đối tượng với các hàm khác |
| `tier_available` | `available_tiers` | B | Trả về một danh sách, tên cần ở dạng số nhiều |
| `schema` (`pipeline.py`) | `params_schema_for_job` | A | Tên quá chung, dễ nhầm với `params_schema` |
| `l2n` | `l2_normalize` | A | Viết tắt khó đoán |
| `_cp` | `_count_pct` | A | Viết tắt khó đoán |
| `first_B` | `top_b_tokens` | B | Chữ hoa trong tên hàm trái PEP 8; nói rõ hàm trả về token |
| `delta_t` | `redundancy_window_s` | B | Hàm trả về ngưỡng thời gian (giây) của Redundancy, không phải "delta t" nói chung |
| `combine` | `combine_scores` | B | Tên quá chung |
| `pct_rank` | `percentile_rank` | C | Rõ nghĩa hơn |
| `stack` (`descriptor.py`) | `stack_block_vectors` | B | Dễ nhầm với `np.stack` |
| `embed` (`descriptor.py`) | `embed_descriptors` | B | Tên quá chung; hàm làm z-score, chia √d và PCA |
| `signals` (`uncertainty.py`) | `compute_t1_signals` | B | Danh từ làm tên hàm; dễ nhầm với biến `signals` |
| `scores_for` (`experiment.py`) | `score_pool` | B | Rõ đối tượng |
| `criterion` | `tune_criterion` | C | Chỉ rõ dùng cho bước tune |
| `fmt_table` | `format_metrics_table` | C | Không viết tắt |
| `oracle` (`eval.py`) | `oracle_selection` | C | Nói rõ trả về tập chọn |
| `reasons` (`select.py`) | `selection_reasons` | C | Tên quá chung |
| `budget` (`select.py`) | `budget_size` | C | Trùng nghĩa với biến `budget` (tỉ lệ) ở nhiều chỗ |
| `Truth` | `RareTruth` | C | Nói rõ là nhãn "rare", không phải nhãn chung |
| `Pool` (`experiment.py`) | `SplitPool` | C | `Pool` dễ nhầm với "pool P" của thiết kế, trong khi đây là dữ liệu của một split bất kỳ |

### 4.3 Tên file CLI, tài liệu, thư mục

| Hiện tại | Đề xuất | Ưu tiên | Lý do |
|---|---|---|---|
| `c4/cli/lidar_t0.py` | `c4/cli/lidar_tier0.py` | B | Đồng nhất với cách gọi "Tầng 0"; `t0` là viết tắt chỉ dùng nội bộ |
| `c4/cli/lidar_g1.py` | `c4/cli/lidar_gate_g1.py` | C | Nói rõ G1 là cổng quyết định |
| `docss/` | `docs/design/` | A | Tên thư mục gần giống `docs/`, dễ gõ nhầm, và chưa được git theo dõi |
| `docss/thiet keTang0_Tang1_VCuboidFIT.pdf` | `docs/design/tier0-tier1-overview.pdf` | A | Tên có dấu cách, thiếu dấu gạch |
| `docss/T07_Buildphase_Document_final.pdf` | `docs/design/c4-design-detail.pdf` | A | "final" trong tên file không có ý nghĩa khi tài liệu còn được cập nhật |
| `model/scripts/tier1.ps1`, `tier1.sh` | giữ nguyên | – | Notebook gọi trực tiếp; đổi sẽ phải sửa 3 notebook và Docker |

### 4.4 Những thứ **không** nên đổi

- Tên cột trong parquet (`rar`, `nov`, `unc`, `r_rar`, ...) và khoá JSON gửi cho web: đây là hợp đồng với
  `web/`. Đổi sẽ phải sửa `web/lib/api/types.ts` và mock.
- Tên các khối descriptor `A–E` và các nhóm rare `A/B/Bp/C`: trùng tên trong tài liệu thiết kế.
- Tên run trong ma trận thí nghiệm (`t0_rar_mmr`, `hybrid_mmr`, ...): trùng bảng 6.2 của T07.

---

## 5. Nơi tham chiếu ngoài Python phải cập nhật khi đổi tên

Trước khi đổi bất kỳ tên module hoặc CLI nào, tìm bằng `grep -rn "<tên cũ>"` ở các nơi sau:

| Nơi | Ví dụ cần kiểm |
|---|---|
| `model/worker/tests/lidar/test_no_leakage_lidar.py` | Danh sách `LABEL_FREE` ghi theo tên file (`score.py`, `select.py`, `uncertainty.py`, ...). Đổi tên file mà quên sửa danh sách này thì test sẽ lỗi hoặc, tệ hơn, bỏ sót module |
| `model/worker/c4/jobs/runner.py` | Bảng `MODULES` ánh xạ stage → tên CLI (`lidar_t0`, `lidar_index`) |
| `model/notebooks/*.ipynb` | Gọi `c4.cli.lidar_experiment`, `c4.cli.lidar_g1`, `model/scripts/colab_agent.py`, `tier1.sh`, `docker/tier1/patch_pcdet.py` |
| `model/docker/**` và `model/scripts/*.sh,*.ps1` | Đường dẫn module trong `Dockerfile`, `start.sh`, `tier1.sh` |
| `docs/*.md`, `README.md`, `model/README.md` | Tên lệnh, cây thư mục |
| `web/` | Chỉ liên quan nếu đổi khoá JSON; mục 4 đã loại các đổi tên đó |

Lệnh kiểm nhanh sau mỗi nhóm đổi tên:

```powershell
cd model\worker
.venv\Scripts\python -m pytest -q -m "not perf and not gpu" tests\lidar tests\service
git grep -n "<tên cũ>"        # phải không còn kết quả
```

---

## 6. Thứ tự thực hiện đề xuất

1. Mục 2.1 (chuẩn hoá MMR) – ảnh hưởng trực tiếp tới việc kết quả thí nghiệm có đáng tin không.
2. Mục 2.2 và 2.3 (pool của web, ranh giới nhãn Tầng 1).
3. Mục 2.4 + 3.1 (tách chọn mẫu và chấm điểm) kèm đổi tên `pipeline.py` và `eval.py`.
4. Mục 3.3 bước (1) và (2) (đổi mặc định sang `lidar`, chuyển test camera), cùng chuyển `mmr.py`.
5. Đổi tên nhóm A của mục 4, rồi nhóm B.
6. Mục 3.2 (agent ra khỏi `scripts/`) và mục 3.4 (tài liệu).
7. Nhóm C của mục 4 chỉ làm nếu còn thời gian.

Các mục trong 2.5 cần bạn quyết định trước khi làm bước 2 và 4.
