"""Tự kiểm môi trường PointPillars (SPEC-P01 §3). Thoát: 0 ok · 3 không GPU · 5 môi trường lệch."""
from __future__ import annotations

import os
import sys
from importlib import metadata
from pathlib import Path

PINNED = {"numpy": "1.26.4", "spconv-cu118": "2.3.6"}
TORCH_PREFIX = "2.1.2"
EXPECTED_COMMIT = "233f849829b6ac19afb8af8837a0246890908755"
TOL = 1e-4


def _forward(seed: int):
    """Một forward PillarVFE -> PointPillarScatter -> BaseBEVBackbone trên cloud tổng hợp cố định."""
    import numpy as np
    import torch
    from easydict import EasyDict
    from pcdet.models.backbones_2d import BaseBEVBackbone
    from pcdet.models.backbones_2d.map_to_bev import PointPillarScatter
    from pcdet.models.backbones_3d.vfe import PillarVFE

    from c4.lidar.tier1.repro import set_determinism

    set_determinism(seed)
    rng = np.random.RandomState(seed)
    rng_range = np.array([-51.2, -51.2, -5.0, 51.2, 51.2, 3.0], dtype=np.float32)
    voxel = np.array([0.2, 0.2, 8.0], dtype=np.float32)
    grid = np.round((rng_range[3:] - rng_range[:3]) / voxel).astype(int)  # 512 x 512 x 1
    n, p = 2000, 20
    vox_pts = torch.zeros(n, p, 5)
    nvox = torch.randint(1, p + 1, (n,))
    xy = rng.choice(grid[0] * grid[1], n, replace=False)
    coords = torch.tensor(np.stack([np.zeros(n), np.zeros(n), xy // grid[0], xy % grid[0]], 1),
                          dtype=torch.int32)
    for i in range(n):
        k = int(nvox[i])
        c = (coords[i, 3].item() + 0.5) * voxel[0] + rng_range[0], \
            (coords[i, 2].item() + 0.5) * voxel[1] + rng_range[1]
        vox_pts[i, :k, 0] = torch.tensor(c[0] + rng.rand(k) * 0.1 - 0.05)
        vox_pts[i, :k, 1] = torch.tensor(c[1] + rng.rand(k) * 0.1 - 0.05)
        vox_pts[i, :k, 2] = torch.tensor(rng.rand(k) * 2 - 1)
        vox_pts[i, :k, 3:] = torch.tensor(rng.rand(k, 2))
    dev = torch.device("cuda")
    mp = EasyDict(WITH_DISTANCE=False, USE_ABSLOTE_XYZ=True, USE_NORM=True, NUM_FILTERS=[64])
    vfe = PillarVFE(mp, num_point_features=5, voxel_size=voxel, point_cloud_range=rng_range)
    scatter = PointPillarScatter(EasyDict(NUM_BEV_FEATURES=64), grid_size=grid)
    bb = BaseBEVBackbone(EasyDict(
        LAYER_NUMS=[3, 5, 5], LAYER_STRIDES=[2, 2, 2], NUM_FILTERS=[64, 128, 256],
        UPSAMPLE_STRIDES=[0.5, 1, 2], NUM_UPSAMPLE_FILTERS=[128, 128, 128]), 64)
    torch.manual_seed(seed)  # trọng số khởi tạo cố định cho cả hai lần
    for m in (vfe, scatter, bb):
        m.to(dev).eval()
    bd = dict(voxels=vox_pts.to(dev), voxel_num_points=nvox.to(dev), voxel_coords=coords.to(dev),
              batch_size=1)
    with torch.no_grad():
        bd = bb(scatter(vfe(bd)))
    return bd["spatial_features_2d"].float().cpu()


def main() -> int:
    import torch

    if not torch.cuda.is_available():
        print("Docker không thấy GPU. Kiểm: docker run --rm --gpus all <image> nvidia-smi",
              file=sys.stderr)
        return 3
    bad = []
    if not torch.__version__.startswith(TORCH_PREFIX):
        bad.append(f"torch {torch.__version__} != {TORCH_PREFIX}")
    for name, want in PINNED.items():
        try:
            got = metadata.version(name)
        except metadata.PackageNotFoundError:
            got = "missing"
        if got != want:
            bad.append(f"{name} {got} != {want}")
    commit_f = Path(os.environ.get("PCDET_ROOT", "/opt/OpenPCDet")) / "BUILD_COMMIT"
    got = commit_f.read_text().strip() if commit_f.is_file() else "missing"
    if got != EXPECTED_COMMIT:
        bad.append(f"OpenPCDet {got} != {EXPECTED_COMMIT}")
    try:
        import pcdet  # noqa: F401
        import spconv  # noqa: F401
    except Exception as e:  # noqa: BLE001
        bad.append(f"import lỗi: {type(e).__name__}: {e}")
    if bad:
        print("MÔI TRƯỜNG LỆCH:\n  " + "\n  ".join(bad), file=sys.stderr)
        return 5
    a, b = _forward(0), _forward(0)
    mx = float((a - b).abs().max())
    print(f"forward OK shape={tuple(a.shape)} gpu={torch.cuda.get_device_name(0)}")
    if mx > TOL:
        print(f"REPRO FAIL max_abs={mx:.3e} > {TOL}", file=sys.stderr)
        return 5
    print(f"REPRO OK max_abs={mx:.3e}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
