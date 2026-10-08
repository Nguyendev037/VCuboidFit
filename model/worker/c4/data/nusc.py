"""Đọc thẳng các bảng JSON của nuScenes (không dùng nuscenes-devkit, cho phép thiếu nhãn)."""
import json
from dataclasses import dataclass, field
from pathlib import Path

from c4.contracts import ContractError

REQUIRED = ["scene", "sample", "sample_data", "calibrated_sensor", "ego_pose", "sensor"]
OPTIONAL = ["category", "instance", "sample_annotation", "visibility", "attribute", "log"]


def _read(vdir: Path, name: str) -> dict[str, dict]:
    rows = json.loads((vdir / f"{name}.json").read_text(encoding="utf-8"))
    return {r["token"]: r for r in rows}


@dataclass
class NuscTables:
    root: Path
    version_dir: Path
    scene: dict
    sample: dict
    sample_data: dict
    calibrated_sensor: dict
    ego_pose: dict
    sensor: dict
    category: dict = field(default_factory=dict)
    instance: dict = field(default_factory=dict)
    sample_annotation: dict = field(default_factory=dict)
    visibility: dict = field(default_factory=dict)
    attribute: dict = field(default_factory=dict)
    log: dict = field(default_factory=dict)
    has_annotations: bool = False

    @classmethod
    def load(cls, data_root) -> "NuscTables":
        root = Path(data_root)
        vdirs = sorted(p for p in root.glob("v1.0-*") if p.is_dir())
        if not vdirs:
            raise FileNotFoundError(f"{root}: không có thư mục v1.0-*")
        if len(vdirs) > 1:
            raise ContractError(
                f"{root}: nhiều thư mục phiên bản {[p.name for p in vdirs]}, cần đúng một")
        vdir = vdirs[0]
        missing = [n for n in REQUIRED if not (vdir / f"{n}.json").is_file()]
        if missing:
            raise FileNotFoundError(f"{vdir}: thiếu bảng bắt buộc {missing}")
        tables = {n: _read(vdir, n) for n in REQUIRED}
        for n in OPTIONAL:
            if (vdir / f"{n}.json").is_file():
                tables[n] = _read(vdir, n)
        has_ann = (vdir / "sample_annotation.json").is_file() and (vdir / "instance.json").is_file()
        return cls(root=root, version_dir=vdir, has_annotations=has_ann, **tables)

    def scene_samples(self, scene_token: str) -> list[dict]:
        """Các sample của scene theo chuỗi `next` bắt đầu từ first_sample_token."""
        out, tok = [], self.scene[scene_token]["first_sample_token"]
        while tok:
            s = self.sample[tok]
            out.append(s)
            tok = s["next"]
        return out
