"""Bất biến I1 (planning/04): chỉ gt.py đọc nhãn, chỉ eval.py đọc gt_rare_lidar."""
import ast
from pathlib import Path

LIDAR = Path(__file__).resolve().parents[2] / "c4" / "lidar"
LABEL_FREE = ["pcd.py", "descriptor.py", "extract.py", "index.py", "splits.py", "score.py",
              "select.py", "uncertainty.py"]
FORBIDDEN_IMPORTS = {"c4.lidar.gt", "c4.lidar.eval", "c4.data.rare_gt", "c4.data.project"}
FORBIDDEN_STRINGS = ["sample_annotation", "gt_rare", "description", "num_lidar_pts", "\"gt\"",
                     "'gt'", "gt/"]


def _imports(tree):
    for n in ast.walk(tree):
        if isinstance(n, ast.Import):
            yield from (a.name for a in n.names)
        elif isinstance(n, ast.ImportFrom) and n.module:
            yield n.module
            yield from (f"{n.module}.{a.name}" for a in n.names)


def test_label_free_modules_never_touch_labels():
    for name in LABEL_FREE:
        src = (LIDAR / name).read_text(encoding="utf-8")
        tree = ast.parse(src)
        bad = set(_imports(tree)) & FORBIDDEN_IMPORTS
        assert not bad, f"{name} import {bad}"
        code = "\n".join(ln for ln in src.splitlines() if not ln.lstrip().startswith("#"))
        doc = ast.get_docstring(tree) or ""
        code = code.replace(doc, "")
        hits = [s for s in FORBIDDEN_STRINGS if s in code]
        assert not hits, f"{name} chứa {hits}"


def test_gt_rare_lidar_read_only_by_eval_and_experiment():
    readers = sorted(p.name for p in LIDAR.glob("*.py")
                     if '"gt_rare_lidar"' in p.read_text(encoding="utf-8"))
    assert set(readers) <= {"gt.py", "eval.py", "experiment.py", "pipeline.py"}, readers
