"""Test của pipeline camera cũ (c4/extract, c4/mining, c4/pipeline, c4/eval): giữ chạy được nhưng
đánh dấu `legacy` để loại khỏi luồng LiDAR bằng `pytest -m "not legacy"`."""
import pytest


def pytest_collection_modifyitems(items):
    here = __file__.rsplit("conftest.py", 1)[0]
    for item in items:
        if str(item.fspath).startswith(here):
            item.add_marker(pytest.mark.legacy)
