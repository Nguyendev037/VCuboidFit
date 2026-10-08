"""S0b: nhãn hiếm (GT_RARE) từ scene.description + annotation. Chỉ rare_gt và project đọc nhãn."""
import numpy as np
import pandas as pd
import yaml

from c4.config import CONFIG_DIR
from c4.contracts import GT_RARE, ContractError, validate
from c4.data.nusc import NuscTables

GROUPS = [c for c in GT_RARE if c not in ("sample_token", "is_rare")]


def load_rare_def() -> dict:
    return yaml.safe_load((CONFIG_DIR / "rare_def.yaml").read_text(encoding="utf-8"))


def annotations_by_sample(t: NuscTables) -> dict[str, list[dict]]:
    """sample_token → [annotation + `category` (tên) + `visibility` (token chuỗi)]."""
    if not t.category:
        raise ContractError(f"{t.version_dir}: có annotation nhưng thiếu category.json")
    out: dict[str, list[dict]] = {}
    for a in t.sample_annotation.values():
        inst = t.instance[a["instance_token"]]
        out.setdefault(a["sample_token"], []).append(
            dict(a, category=t.category[inst["category_token"]]["name"],
                 visibility=str(a.get("visibility_token", ""))))
    return out


def _has_keyword(text: str, keywords: list[str]) -> bool:
    text = text.lower()
    return any(k.lower() in text for k in keywords)


def rare_flags(t: NuscTables, frames: pd.DataFrame, rare_def: dict) -> pd.DataFrame:
    """GT_RARE: một dòng mỗi sample_token của `frames` (thứ tự xuất hiện đầu tiên)."""
    samples = frames.drop_duplicates("sample_token")
    anns = annotations_by_sample(t)
    rare_classes = tuple(rare_def["rare_classes"])
    rows = []
    for tok, desc in zip(samples["sample_token"], samples["scene_desc"]):
        boxes = anns.get(tok, [])
        npts = [b["num_lidar_pts"] for b in boxes]
        rows.append(dict(
            sample_token=tok,
            A_night=_has_keyword(desc, rare_def["night_keywords"]),
            A_rain=_has_keyword(desc, rare_def["rain_keywords"]),
            B_rare_class=any(b["category"].startswith(rare_classes) for b in boxes),
            C_crowd=sum(b["category"].startswith("human.pedestrian") for b in boxes)
            >= rare_def["crowd_min_peds"],
            C_low_vis=any(b["visibility"] == str(rare_def["low_vis_level"]) for b in boxes),
            C_far=any(1 <= n <= rare_def["far_max_lidar_pts"] for n in npts)))
    df = pd.DataFrame(rows, columns=["sample_token", *GROUPS])
    freq = group_frequencies(df)
    usable = [g for g in GROUPS if freq[g] <= rare_def["rare_max_freq"]]
    df["is_rare"] = df[usable].any(axis=1) if usable else False
    df["is_rare"] = df["is_rare"].astype(bool)
    return validate(df, "gt_rare")


def group_frequencies(flags: pd.DataFrame) -> dict[str, float]:
    """Tần suất của từng nhóm trong pool (tỉ lệ sample có cờ); pool rỗng ⇒ 0."""
    n = len(flags)
    return {g: float(np.round(flags[g].sum() / n, 6)) if n else 0.0 for g in GROUPS}
