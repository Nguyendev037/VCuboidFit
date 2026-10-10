import os
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.patches import FancyBboxPatch, FancyArrowPatch

fig, ax = plt.subplots(figsize=(14.6, 10.8))
ax.set_xlim(-0.6, 14.6); ax.set_ylim(0, 10.8); ax.axis("off")
EDGE = "#2F5597"
OUT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "workflow_v2.png")

def box(x, y, w, h, title, lines, fill):
    ax.add_patch(FancyBboxPatch((x, y), w, h, boxstyle="round,pad=0.12",
                 fc=fill, ec=EDGE, lw=1.6))
    ax.text(x + w/2, y + h - 0.38, title, ha="center", va="top",
            fontsize=10.5, fontweight="bold")
    ax.text(x + w/2, y + h/2 - 0.32, lines, ha="center", va="center", fontsize=8.4)

def arrow(x1, y1, x2, y2, label="", dashed=False, color=EDGE, rad=0.0, lx=None, ly=None):
    ax.add_patch(FancyArrowPatch((x1, y1), (x2, y2), arrowstyle="-|>",
                 mutation_scale=16, lw=1.5, color=color,
                 linestyle="--" if dashed else "-",
                 connectionstyle=f"arc3,rad={rad}"))
    if label:
        ax.text(lx if lx is not None else (x1+x2)/2 + 0.1,
                ly if ly is not None else (y1+y2)/2 + 0.12, label, fontsize=8.5,
                color=color if color != EDGE else "#C00000", fontweight="bold")

def dbox(x, y, w, h, title, lines, fill):
    """Khối TUỲ CHỌN — viền nét đứt."""
    ax.add_patch(FancyBboxPatch((x, y), w, h, boxstyle="round,pad=0.12",
                 fc=fill, ec=PURPLE, lw=1.6, linestyle="--"))
    ax.text(x + w/2, y + h - 0.38, title, ha="center", va="top",
            fontsize=10.5, fontweight="bold", color=PURPLE)
    ax.text(x + w/2, y + h/2 - 0.32, lines, ha="center", va="center", fontsize=8.4)

M, P, E = "#DCEAF7", "#FDEBD0", "#E2F0D9"
PURPLE, Q = "#6A3D9A", "#EFE6F7"
box(0.3, 9.1, 5.6, 1.3, "Model LÕI: checkpoint PointPillars công khai", "đóng băng · chỉ inference · train trên nuScenes train\n→ V/T chỉ lấy scene model chưa thấy (val / mini_val)", M)
dbox(6.6, 9.1, 6.0, 1.3, "Bước 0 (tuỳ chọn): train model Seed", "train_seed.py · Seed = frame đã có nhãn\nseed_manifest.json → frame Seed loại khỏi V/T", Q)
box(0.3, 7.2, 3.4, 1.4, "M0 Chuẩn hoá", "keyframes only · V/T THEO SCENE\ntrong 150 scene val (không leak)", M)
box(4.4, 7.2, 4.1, 1.4, "M0.5a Sanity check model", "100–300 frame CÓ nhãn (random + phân tầng)\nrecall theo slice · schema · IoU box vs GT", P)
box(9.2, 7.2, 3.4, 1.4, "M0.5b Pilot batch", "500–1000 frame: gán tay top-B′ +\nrandom-B′ → so yield · go/no-go", P)
box(0.3, 5.2, 3.4, 1.4, "M1 Sinh ứng viên", "(a) clustering class-agnostic\n(b) PointPillars + TTA (chỉ inference)", M)
box(4.4, 5.2, 4.1, 1.4, "M2 Điểm vật thể", "s_obj = rank_agg(shape, unc*,\nslice, vru) + boost cứng", M)
box(9.2, 5.2, 3.4, 1.4, "M3 Điểm frame", "s_frame = rank_agg(obj, crowd,\nweather†) + boost · OOD = cờ", M)
box(0.3, 3.2, 3.4, 1.4, "M4 Dedup + đa dạng", "top-k mỗi nhóm · quota slice\n(rare_class/crowd/night/rain/…)", M)
box(4.4, 3.2, 4.1, 1.4, "M5 Chọn theo ngân sách", "top-B → frames_ranked.csv (lý do)\n+ objects_T.csv (box khoanh sẵn)", M)
G = "#FFF4D6"
ax.add_patch(FancyBboxPatch((0.3, 0.95), 3.4, 1.5, boxstyle="round,pad=0.12", fc=G, ec="#B7791F", lw=1.8))
ax.text(2.0, 2.07, "Cổng NGOẠI LAI (4 phép thử)", ha="center", va="top", fontsize=10.5, fontweight="bold", color="#5C3D00")
ax.text(2.0, 1.38, "hợp lệ · thời gian · hình học · k-NN\nHợp lệ → chọn · Nghi ngờ → review_T.csv\nNgoại lai → loại (không train)", ha="center", va="center", fontsize=8.2)
box(4.4, 0.95, 4.1, 1.5, "M6 Đánh giá (GT giấu)", "rule filter → P/R@B theo slice · AP · yield\nrandom×10 · ablation · bootstrap theo scene\nlỗi giả trên V: tỉ lệ lọt cổng ngoại lai", E)
box(9.2, 3.2, 3.4, 1.4, "Gán nhãn (người)", "lô selected=1 (+ explore=1 nếu\nphương án B) · ledger loại khỏi\nvòng sau", P)

arrow(3.1, 9.1, 3.1, 8.75)
arrow(9.6, 9.1, 7.6, 8.75, "hoặc", color=PURPLE, lx=9.75, ly=8.82)
arrow(3.7, 7.9, 4.4, 7.9)
arrow(8.5, 7.9, 9.2, 7.9, "PASS")
arrow(10.9, 7.2, 2.0, 6.6, "GO", dashed=True, color="#C00000")
arrow(3.7, 5.9, 4.4, 5.9)
arrow(8.5, 5.9, 9.2, 5.9)
arrow(10.9, 5.2, 2.0, 4.6, dashed=True)
arrow(3.7, 3.9, 4.4, 3.9)
arrow(0.3, 5.5, 0.3, 2.2, "sau M1", color="#B7791F", rad=0.35, lx=-0.58, ly=4.3)
arrow(2.0, 2.45, 2.0, 3.2, "chỉ Hợp lệ", color="#B7791F", lx=2.1, ly=2.75)
arrow(6.45, 3.2, 6.45, 2.45)
arrow(9.2, 3.9, 8.5, 3.9, "lô mới")
arrow(10.9, 3.2, 7.6, 2.0, "yield", dashed=True, color="#C00000")
arrow(12.75, 3.9, 12.75, 9.6, "retrain\n(công tắc,\nAP chỉ báo\nkhi bật)", dashed=True, color=PURPLE, rad=0.12, lx=13.65, ly=6.0)

ax.text(0.3, 0.52, "(*) s_unc trọng số thấp — rareness ≠ uncertainty    (†) đêm/mưa: metadata + camera + proxy mưa LiDAR; KHÔNG suy 'đêm' từ point cloud",
        fontsize=8.6, style="italic")
ax.text(0.3, 0.18, "Ràng buộc: keyframes only · fit thống kê chỉ trên V · GT chỉ M6 nhìn · rank-aggregation · seed cố định · out_dir theo run_id · frame PILOT/đã-gán loại khỏi T",
        fontsize=8.6, style="italic")
plt.tight_layout()
plt.savefig(OUT, dpi=170, bbox_inches="tight")
print("saved", OUT)
