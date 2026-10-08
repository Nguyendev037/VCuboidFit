from pathlib import Path

C4 = Path(__file__).resolve().parent.parent / "c4"


def test_no_leakage():
    """Code mining và extract không bao giờ đọc nhãn (thư mục gt/ hoặc module rare_gt)."""
    files = [p for d in ("mining", "extract") for p in (C4 / d).rglob("*.py")]
    assert files, "không tìm thấy mã nguồn mining"
    for p in files:
        src = p.read_text(encoding="utf-8")
        assert "gt/" not in src, p
        assert "rare_gt" not in src, p
