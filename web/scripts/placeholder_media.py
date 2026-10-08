"""Sinh ảnh/LiDAR MẪU cho mock-media (thư mục gitignore). Chạy từ web/: python scripts/placeholder_media.py
(cần Pillow + numpy; ví dụ dùng venv của worker).
"""
import json, re, sys
from pathlib import Path
import numpy as np
from PIL import Image, ImageDraw
web = Path(".")
urls = sorted({u for p in (web/"mocks").glob("*.json") for u in re.findall(r'"(/mock-media/[^"]+)"', p.read_text(encoding="utf-8"))})
npts = {}
for p in (web/"mocks").glob("frame-detail-*.json"):
    d = json.loads(p.read_text(encoding="utf-8"))
    if d.get("lidar"): npts[d["lidar"]["url"]] = d["lidar"]["numPoints"]
COL = {"FRONT": (71, 85, 105), "FRONT_LEFT": (51, 65, 85), "FRONT_RIGHT": (30, 41, 59), "BACK": (63, 63, 70), "BACK_LEFT": (55, 65, 81), "BACK_RIGHT": (39, 39, 42)}
rng = np.random.default_rng(7)
def img(path, w, h, label, fmt, **kw):
    cam = re.search(r"CAM_([A-Z_]+)", label)
    base = COL.get(cam.group(1) if cam else "FRONT", (71, 85, 105))
    a = np.zeros((h, w, 3), np.uint8)
    t = np.linspace(0, 1, h)[:, None, None]
    a[:] = (np.array(base) * (0.6 + 0.5 * (1 - t))).clip(0, 255).astype(np.uint8)
    im = Image.fromarray(a); d = ImageDraw.Draw(im)
    y = int(h * 0.62); d.rectangle([0, y, w, h], fill=tuple(int(c * 0.55) for c in base))  # mặt đường
    for k in range(3):  # vài khối "vật thể" mờ
        x = int(w * (0.2 + 0.25 * k)); bw, bh = int(w * 0.10), int(h * 0.22)
        d.rectangle([x, y - bh, x + bw, y], fill=tuple(min(255, int(c * 1.5)) for c in base))
    d.text((int(w * 0.03), int(h * 0.04)), "ẢNH MẪU · " + label, fill=(226, 232, 240))
    path.parent.mkdir(parents=True, exist_ok=True); im.save(path, fmt, **kw)
n = 0
for u in urls:
    out = web / "public" / u.lstrip("/")
    label = out.stem
    if "/thumbs/" in u: img(out, 320, 180, label, "WEBP", quality=70)
    elif "/images/" in u: img(out, 1600, 900, f"{out.parent.name} {label}", "JPEG", quality=60)
    elif "/lidar/" in u:
        k = npts.get(u, 30000); r = rng.uniform(2, 60, k); th = rng.uniform(0, 2 * np.pi, k)
        pts = np.stack([r * np.cos(th), r * np.sin(th), rng.normal(0.2, 0.6, k) + (r < 12) * 0.5, rng.uniform(0, 1, k)], 1).astype(np.float16)
        out.parent.mkdir(parents=True, exist_ok=True); out.write_bytes(pts.tobytes())
    n += 1
print("files", n)
