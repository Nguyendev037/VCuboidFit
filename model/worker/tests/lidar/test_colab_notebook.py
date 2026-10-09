"""Execute the notebook's actual Drive ZIP and CPU cells without a Colab account."""
import json
import tempfile
import zipfile
from pathlib import Path

import pandas as pd
import pytest

from service.archives import DatasetError
from tests.fixtures import make_nuscenes as fixture

NOTEBOOKS = Path(__file__).resolve().parents[3] / "notebooks"


def cells():
    notebook = json.loads((NOTEBOOKS / "vcf_dev_setup_colab.ipynb").read_text("utf-8"))
    return {c["metadata"]["vcf_step"]: "".join(c["source"])
            for c in notebook["cells"] if c["cell_type"] == "code"}


@pytest.fixture
def env(tmp_path, monkeypatch):
    folder = tmp_path / "datatest"
    folder.mkdir()
    original = tempfile.mkdtemp

    def local_temp(*args, **kwargs):
        if kwargs.get("dir") == "/content":
            kwargs["dir"] = tmp_path
        return original(*args, **kwargs)

    monkeypatch.setattr(tempfile, "mkdtemp", local_temp)
    return dict(Path=Path, tempfile=tempfile, DATA_FOLDER=folder,
                RESULT_FOLDER=tmp_path / "results")


def test_notebook_has_valid_code():
    assert not (NOTEBOOKS / "vcf_tier01_kaggle_colab.ipynb").exists()  # Kaggle đã bỏ, chỉ Colab
    for name, source in cells().items():
        compile(source, f"colab-{name}", "exec")
        assert "kaggle" not in source.lower()
        assert "cloudflare" not in source.lower()
        assert "VCF_REMOTE_TOKEN" not in source


@pytest.mark.parametrize("prefix", ["", "nested/data/"])
def test_zip_parts_to_cpu_results(env, tmp_path, monkeypatch, prefix):
    monkeypatch.setattr(fixture, "N_LIDAR_PTS", 2500)
    root = fixture.make_nuscenes(tmp_path / "fixture", n_scenes=3,
                                frames_per_scene=4, cams=(), with_annotations=False)
    files = sorted(p for p in root.rglob("*") if p.is_file())
    for i in range(2):
        with zipfile.ZipFile(env["DATA_FOLDER"] / f"part{i}.zip", "w") as archive:
            for p in files[i::2]:
                archive.write(p, prefix + p.relative_to(root).as_posix())
    sources = cells()
    exec(sources["data"], env)
    assert len(env["index"]) == 12
    exec(sources["select"], env)
    result = env["result"]
    assert result["tierAvailable"] == [0]
    assert result["metrics"] is None
    target = env["RESULT_FOLDER"] / env["RUN_NAME"] / "tier0"
    selected = pd.read_csv(target / "selected_5pct.csv")
    assert len(selected) == result["budgetB"]
    assert set(selected["sample_token"]) <= set(env["index"]["sample_token"])
    assert (target / "results.zip").is_file()
    assert len(list(env["DATA_FOLDER"].glob("*.zip"))) == 2


def test_no_zip_has_actionable_error(env):
    with pytest.raises(FileNotFoundError, match="Không có file .zip"):
        exec(cells()["data"], env)


def test_gpu_is_disabled_for_run_all(capsys):
    exec(cells()["gpu"], {})
    assert "GPU đang tắt" in capsys.readouterr().out


def test_corrupt_zip_stops(env):
    (env["DATA_FOLDER"] / "bad.zip").write_bytes(b"bad zip")
    with pytest.raises(zipfile.BadZipFile):
        exec(cells()["data"], env)


def test_zip_traversal_is_rejected(env, tmp_path):
    with zipfile.ZipFile(env["DATA_FOLDER"] / "bad.zip", "w") as archive:
        archive.writestr("../escape.txt", "bad")
    with pytest.raises(DatasetError, match="đường dẫn không hợp lệ"):
        exec(cells()["data"], env)
    assert not (tmp_path / "escape.txt").exists()


def test_conflicting_datasets_stop(env):
    for i in range(2):
        with zipfile.ZipFile(env["DATA_FOLDER"] / f"part{i}.zip", "w") as archive:
            archive.writestr("data/v1.0-mini/scene.json", str(i))
    with pytest.raises(DatasetError, match="nội dung khác"):
        exec(cells()["data"], env)


def test_missing_metadata_stops(env):
    with zipfile.ZipFile(env["DATA_FOLDER"] / "part.zip", "w") as archive:
        archive.writestr("samples/LIDAR_TOP/example.bin", b"points")
    with pytest.raises(FileNotFoundError, match="v1.0"):
        exec(cells()["data"], env)
