"""C2: bốn trục bối cảnh bằng OpenCLIP pretrained (không train, không VLM).

Softmax RIÊNG từng trục (B5) với logit_scale của model; ảnh dùng lại cache/clip_img.npy (B4).
"""
from dataclasses import dataclass
from pathlib import Path

import numpy as np
import yaml

from c4.mining.query import TextEncoder

AXES_PATH = Path(__file__).resolve().parent.parent.parent / "configs" / "context_axes_v1.yaml"
REQUIRED_AXES = ("illum", "glare", "lens", "weather")
PROMPTS_PER_CLASS = 3


class ContextConfigError(ValueError):
    """yaml trục bối cảnh sai schema (fail fast lúc nạp)."""


@dataclass(frozen=True)
class Axis:
    name: str
    classes: tuple[str, ...]
    prompts: dict[str, tuple[str, ...]]


def _parse(data) -> list[Axis]:
    if not isinstance(data, dict) or not isinstance(data.get("version"), str):
        raise ContextConfigError("thiếu 'version' (chuỗi)")
    raw = data.get("axes")
    if not isinstance(raw, list) or not raw:
        raise ContextConfigError("thiếu danh sách 'axes'")
    axes, seen = [], set()
    for a in raw:
        if not isinstance(a, dict) or not isinstance(a.get("name"), str):
            raise ContextConfigError("trục thiếu 'name'")
        name = a["name"]
        if name in seen:
            raise ContextConfigError(f"trục trùng tên: {name}")
        seen.add(name)
        classes = a.get("classes")
        if not isinstance(classes, list) or len(classes) < 2 or not all(isinstance(c, str) for c in classes):
            raise ContextConfigError(f"trục {name}: 'classes' phải là list >= 2 chuỗi")
        if len(set(classes)) != len(classes):
            raise ContextConfigError(f"trục {name}: tên lớp trùng")
        prompts = a.get("prompts")
        if not isinstance(prompts, dict) or set(prompts) != set(classes):
            raise ContextConfigError(f"trục {name}: 'prompts' phải có đúng các lớp {classes}")
        for c in classes:
            p = prompts[c]
            if (not isinstance(p, list) or len(p) != PROMPTS_PER_CLASS
                    or not all(isinstance(t, str) and t.strip() for t in p)):
                raise ContextConfigError(
                    f"trục {name}, lớp {c}: cần đúng {PROMPTS_PER_CLASS} prompt chuỗi không rỗng")
        axes.append(Axis(name, tuple(classes), {c: tuple(prompts[c]) for c in classes}))
    missing = [n for n in REQUIRED_AXES if n not in seen]
    if missing:
        raise ContextConfigError(f"thiếu trục: {missing}")
    return axes


def load_axes(path: Path | None = None) -> list[Axis]:
    """Nạp configs/context_axes_v1.yaml (hoặc `path`); sai schema ⇒ ContextConfigError."""
    try:
        data = yaml.safe_load(Path(path or AXES_PATH).read_text(encoding="utf-8"))
    except yaml.YAMLError as e:
        raise ContextConfigError(f"yaml không hợp lệ: {e}") from e
    return _parse(data)


def encode_axes(axes: list[Axis], encoder: TextEncoder) -> dict[str, np.ndarray]:
    """Mỗi trục → (n_class, d): mean của 3 prompt/lớp rồi chuẩn hoá L2."""
    out = {}
    for ax in axes:
        texts = [t for c in ax.classes for t in ax.prompts[c]]
        z = np.asarray(encoder.encode(texts), np.float64)
        if z.shape[0] != len(texts):
            raise ValueError(f"encoder trả {z.shape[0]} vector cho {len(texts)} prompt")
        z = z.reshape(len(ax.classes), PROMPTS_PER_CLASS, -1).mean(axis=1)
        z /= np.maximum(np.linalg.norm(z, axis=1, keepdims=True), 1e-12)
        out[ax.name] = z.astype(np.float32)
    return out


def axis_probs(C_img: np.ndarray, T: dict[str, np.ndarray], logit_scale: float) -> dict[str, np.ndarray]:
    """softmax(logit_scale · C_img @ T_axisᵀ) RIÊNG từng trục → (N, n_class) float32."""
    C = np.asarray(C_img, np.float32)
    out = {}
    for name, Ta in T.items():
        z = float(logit_scale) * (C @ np.asarray(Ta, np.float32).T).astype(np.float64)
        z -= z.max(axis=1, keepdims=True)
        e = np.exp(z)
        out[name] = (e / e.sum(axis=1, keepdims=True)).astype(np.float32)
    return out
