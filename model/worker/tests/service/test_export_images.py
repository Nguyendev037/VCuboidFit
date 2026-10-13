"""SPEC-P07: actual API ZIP, selected order, original cameras, metadata and limits."""
import copy
import csv
import io
import json
import zipfile

from fastapi.testclient import TestClient

from c4.cli import lidar_index, lidar_t0
from c4.lidar import load_lidar_config
from service import engines, export_images
from service.main import create_app
from service.settings import Settings
from tests.fixtures.make_nuscenes import make_nuscenes


def test_export_selected_images_and_errors(tmp_path, monkeypatch):
    settings = Settings(workspace=tmp_path / "ws")
    root = make_nuscenes(settings.datasets / "d", n_scenes=2, frames_per_scene=6,
                         rare_frames={(s, i): [("human.pedestrian.adult", (8+i, 2*s, 0), 150)]
                                      for s in range(2) for i in range(6)})
    job = settings.jobs / "j1"
    cfg = copy.deepcopy(load_lidar_config())
    cfg["filter"]["min_points"] = 50
    monkeypatch.setattr(lidar_t0, "load_lidar_config", lambda: cfg)
    assert lidar_index.main(["--data-root", str(root), "--job-dir", str(job)]) == 0
    assert lidar_t0.main(["--data-root", str(root), "--job-dir", str(job)]) == 0
    (job / "job.json").write_text(json.dumps(dict(jobId="j1", datasetId="d", pipeline="lidar",
                                                state="done")), encoding="utf-8")
    real_run = engines.run_rare_v24
    monkeypatch.setattr(engines, "run_rare_v24", lambda *a, **kw: real_run(
        *a, **kw, scoring={"min_ref_vru": 0}))
    # Fixture may put metadata in a version subfolder; production root is datasets/id/data.
    monkeypatch.setattr(export_images, "_dataset_root", lambda *a: root)
    with TestClient(create_app(settings, runner=lambda *a, **k: {})) as client:
        result = client.post("/jobs/j1/select", json={"engineVersion": "rare_v24", "budget": 0.1})
        assert result.status_code == 200, result.text
        body = result.json()
        sid = body["selectionId"]
        url = f"/jobs/j1/selections/{sid}/export-images.zip"
        response = client.get(url, params={"cams": "front", "lidar": False})
        assert response.status_code == 200, response.text
        assert response.headers["content-type"] == "application/zip"
        assert f"vcf_j1_{sid}_rare.zip" in response.headers["content-disposition"]
        with zipfile.ZipFile(io.BytesIO(response.content)) as archive:
            rows = list(csv.DictReader(io.StringIO(archive.read("index.csv").decode("utf-8-sig"))))
            folders = {n.split("/")[0] for n in archive.namelist() if "/" in n}
            assert len(rows) == len(folders) == body["budgetB"]
            assert [r["sample_token"] for r in rows] == [f["sampleToken"] for f in body["preview"]]
            for row in rows:
                meta = json.loads(archive.read(row["folder"] + "/meta.json"))
                assert meta["predTags"] and meta["objects"] and meta["gate"] == "valid"
                assert meta["context"] is None
                assert archive.read(row["folder"] + "/CAM_FRONT.jpg")
            assert not any("CAM_BACK" in n or "lidar_bev" in n for n in archive.namelist())
            assert "CC BY-NC-SA 4.0" in archive.read("README.txt").decode()
        assert client.get("/jobs/j1/selections/absent/export-images.zip").json()["error"]["code"] == "SELECTION_NOT_FOUND"
        monkeypatch.setattr(export_images, "MAX_FRAMES", 0)
        assert client.get(url).json()["error"]["code"] == "EXPORT_TOO_LARGE"
        data = export_images.get_data(type("Request", (), {"app": client.app})(), "j1", sid)
        monkeypatch.setattr(data, "budget_b", lambda b: 0)
        assert client.get(url).json()["error"]["code"] == "EMPTY_SELECTION"
