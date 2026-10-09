"""Vá OpenPCDet cho numpy ≥ 1.24 và không có av2 (dùng trong Dockerfile + Colab).

python patch_pcdet.py <OpenPCDet_root>   → in số file đã sửa; thoát 1 nếu còn alias sót.
"""
import re
import sys
from pathlib import Path

ALIAS = re.compile(r"\bnp\.(int|float|bool)\b(?![\w])")


def main(root: str) -> int:
    base = Path(root)
    init = base / "pcdet" / "datasets" / "__init__.py"
    lines = init.read_text(encoding="utf-8").splitlines(keepends=True)
    init.write_text("".join(ln for ln in lines if "rgo2" not in ln), encoding="utf-8")
    changed = 0
    for f in [*base.joinpath("pcdet").rglob("*.py"), *base.joinpath("tools").rglob("*.py")]:
        src = f.read_text(encoding="utf-8")
        new = ALIAS.sub(lambda m: m.group(1), src)
        if new != src:
            f.write_text(new, encoding="utf-8")
            changed += 1
    left = [str(f) for f in base.joinpath("pcdet").rglob("*.py")
            if ALIAS.search(f.read_text(encoding="utf-8"))]
    print(f"patched {changed} file(s); remaining aliases: {len(left)}")
    return 1 if left else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1]))
