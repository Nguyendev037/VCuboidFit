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

## 5. Trạng thái (2026-10-17)
- ✅ Thiết kế + prereg, ✅ code + 126 test (commit `fa2e8d3`…`6e477bd`).
- ⬜ Chạy khô trên nuScenes 602 kf (Colab) · ⬜ PandaSet · ⬜ Argoverse 2 · ⬜ Pha 4 · ⬜ thẩm định đối kháng.
- Chưa có con số benchmark nào. Mọi con số sau này phải đi kèm sha prereg/selections và output của notebook thẩm định.

Liên quan: [colab-mcp.md](colab-mcp.md) (điều khiển notebook bằng agent) · [colab-dev-setup.md](colab-dev-setup.md).
