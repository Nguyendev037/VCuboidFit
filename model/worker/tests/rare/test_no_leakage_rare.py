"""M2 · phía CHỌN của rare_v24 không import/đọc nhãn hay annotation (planning/11 SPEC-P05 §9 + §14.3)."""
import ast
from pathlib import Path

WORKER = Path(__file__).resolve().parents[2]
SELECT_SIDE = [p for p in sorted((WORKER / "c4" / "rare").glob("*.py"))
               if p.name not in ("gt_rhcio.py", "eval.py", "__init__.py")] + [WORKER / "c4" / "cli" / "rare.py"]
BANNED = {"gt_rhcio", "sample_annotation", "annotation", "attribute", "visibility", "gt_rare", "gt_boxes"}
BANNED_MODULES = {"c4.rare.gt_rhcio", "c4.rare.eval"}


def _docstring_nodes(tree: ast.AST) -> set[int]:
    ids = set()
    for node in ast.walk(tree):
        if isinstance(node, (ast.Module, ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)) and node.body:
            first = node.body[0]
            if isinstance(first, ast.Expr) and isinstance(first.value, ast.Constant) \
                    and isinstance(first.value.value, str):
                ids.add(id(first.value))
    return ids


def _violations(name: str, src: str) -> list[str]:
    tree = ast.parse(src)
    docs = _docstring_nodes(tree)
    bad = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Attribute) and (node.attr in BANNED or node.attr == "description"):
            bad.append(f"{name}:{node.lineno} đọc .{node.attr}")
        elif isinstance(node, ast.Name) and node.id in BANNED:
            bad.append(f"{name}:{node.lineno} dùng tên {node.id}")
        elif isinstance(node, ast.Constant) and isinstance(node.value, str) and id(node) not in docs:
            hit = [b for b in BANNED if b in node.value] + (["description"] if node.value == "description" else [])
            if hit:
                bad.append(f"{name}:{node.lineno} chuỗi chứa {hit}")
        elif isinstance(node, ast.Import):
            bad += [f"{name}:{node.lineno} import {a.name}" for a in node.names if a.name in BANNED_MODULES]
        elif isinstance(node, ast.ImportFrom) and node.module:
            for a in node.names:
                full = f"{node.module}.{a.name}"
                allowed = node.module == "c4.rare.eval" and a.name == "budget"  # ngoại lệ DUY NHẤT
                if (node.module in BANNED_MODULES or full in BANNED_MODULES) and not allowed:
                    bad.append(f"{name}:{node.lineno} import {full}")
    return bad


def test_no_leakage_rare():
    """Mọi file phía chọn sạch; bộ quét phải bắt được dòng cấm (đường ĐỎ)."""
    assert len(SELECT_SIDE) >= 7
    found = [v for p in SELECT_SIDE for v in _violations(p.name, p.read_text(encoding="utf-8"))]
    assert not found, found
    assert _violations("x.py", "def f(t):\n    return t.sample_annotation\n")
    assert _violations("x.py", "from c4.rare.gt_rhcio import label_gt\n")
    assert _violations("x.py", "from c4.rare.eval import evaluate\n")
    assert not _violations("x.py", "from c4.rare.eval import budget\n")
    assert not _violations("x.py", 'def f():\n    "ghi chú về annotation"\n    return 1\n')
