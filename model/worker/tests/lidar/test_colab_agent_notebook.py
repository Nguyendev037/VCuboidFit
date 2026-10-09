"""Notebook Colab agent (Run all): JSON hợp lệ, đặt sẵn GPU, ô kiểm kết nối dừng sớm khi URL sai."""
import ast
import json
from pathlib import Path

import pytest

NB = Path(__file__).resolve().parents[3] / "notebooks" / "vcf_colab_agent.ipynb"


def code_cells():
    nb = json.loads(NB.read_text("utf-8"))
    assert nb["metadata"]["accelerator"] == "GPU"
    return ["".join(c["source"]) for c in nb["cells"] if c["cell_type"] == "code"]


def test_cells_parse_and_order():
    cells = code_cells()
    assert len(cells) == 4
    for src in cells:
        ast.parse(src)
    assert "SERVER_URL" in cells[0] and "TOKEN" in cells[0]
    assert "colab_setup.sh" in cells[2] and "colab_agent.py" in cells[3]


@pytest.mark.parametrize("url", ["", "https://xxxx.trycloudflare.com", "http://abc.trycloudflare.com"])
def test_bad_url_stops_before_install(url):
    with pytest.raises(RuntimeError, match="SERVER_URL"):
        exec(code_cells()[1], {"SERVER_URL": url, "TOKEN": ""})
