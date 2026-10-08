"""P03a: job LiDAR xuyên service — POST /jobs (mặc định lidar) → runner thật → select/schema/frames.

nuScenes giả chỉ có 300 điểm/frame (< `filter.min_points` 2000 của lidar.yaml), nên fixture ghi lại
`.pcd.bin` dày 4000 điểm: giữ NGUYÊN cấu hình thật, không hạ ngưỡng lidar.yaml.
"""
import json
import os
import time

import numpy as np
import pytest
from fastapi.testclient import TestClient

from service.datasets import _save, validate_dataset
from service.main import create_app
from service.settings import Settings
from tests.fixtures.make_nuscenes import make_nuscenes

N_SCENES, FRAMES_PER_SCENE, N_POINTS = 3, 4, 4000
N = N_SCENES * FRAMES_PER_SCENE
PARAMS = {"minLuma": 0, "minBlurVar": 0}  # BỊ BỎ QUA ở lidar (01-CONTRACTS §3): gửi để chắc vậy


def _dense_lidar(data) -> None:
    """Mỗi .pcd.bin thành 4000 điểm float32 × 5 (x, y, z, intensity, ring) như nuScenes thật."""
    rng = np.random.default_rng(0)
    files = sorted((data / "samples" / "LIDAR_TOP").glob("*.pcd.bin"))
    assert len(files) == N
    for p in files:
        p.write_bytes(rng.uniform(-30, 30, (N_POINTS, 5)).astype(np.float32).tobytes())


@pytest.fixture(scope="module")
def env(tmp_path_factory):
    old = os.environ.get("C4_FAKE_MODELS")
    os.environ["C4_FAKE_MODELS"] = "1"
    settings = Settings(workspace=tmp_path_factory.mktemp("ws"), sevenzip="__khong_co_7z__")
    data = make_nuscenes(settings.datasets / "d1", n_scenes=N_SCENES,
                         frames_per_scene=FRAMES_PER_SCENE)
    _dense_lidar(data)
    _save(settings, validate_dataset(data, "d1"))
    app = create_app(settings)
    with TestClient(app) as c:
        jid = c.post("/jobs", json={"datasetId": "d1"}).json()["jobId"]  # có LiDAR ⇒ mặc định lidar
        t0 = time.monotonic()
        while (st := c.get(f"/jobs/{jid}").json())["state"] not in ("done", "failed"):
            assert time.monotonic() - t0 < 600, "job lidar quá lâu"
            time.sleep(0.5)
        assert st["state"] == "done", st
        sid = c.post(f"/jobs/{jid}/select", json=PARAMS).json()["selectionId"]
        # ngân sách 10 % để danh sách frame có đủ 2 dòng (hybrid lidar chỉ dài bằng B)
        sid10 = c.post(f"/jobs/{jid}/select", json={**PARAMS, "budget": 0.10}).json()["selectionId"]
        yield dict(app=app, settings=settings, jid=jid, sid=sid, sid10=sid10, status=st)
    if old is None:
        os.environ.pop("C4_FAKE_MODELS", None)
    else:
        os.environ["C4_FAKE_MODELS"] = old


@pytest.fixture
def client(env):
    with TestClient(env["app"]) as c:
        yield c


def test_job_runs_lidar_stages_only(env):
    st = env["status"]
    assert st["pipeline"] == "lidar"
    assert [s["name"] for s in st["stages"]] == ["lidar_index", "t0"]
    assert all(s["state"] == "done" for s in st["stages"])
    job = env["settings"].jobs / env["jid"]
    assert (job / "lidar" / "index.parquet").is_file()
    assert (job / "lidar" / "z0.npy").is_file() and (job / "lidar" / "filter.parquet").is_file()
    assert len(list((job / "media" / "bev").glob("*.png"))) == N
    assert (job / "gt" / "gt_rare_lidar.parquet").is_file()  # dataset có annotation
    assert not (job / "cache" / "features_cache.parquet").exists()  # KHÔNG chạy pipeline camera


def test_select_default_returns_lidar_shape(client, env):
    r = client.post(f"/jobs/{env['jid']}/select", json=PARAMS)
    assert r.status_code == 200, r.text
    b = r.json()
    assert b["pipeline"] == "lidar" and b["tierAvailable"] == [0]
    assert b["poolSize"] == N and b["budgetB"] >= 1
    assert {"pipeline", "tier", "k", "lam", "m", "quotaOff", "alpha", "beta", "gamma",
            "budget"} <= set(b["params"])
    assert b["params"]["tier"] == 0  # không có t1/signals.parquet ⇒ chỉ tầng 0
    p0 = b["preview"][0]
    assert p0["bestCam"] == "LIDAR_TOP" and p0["rQry"] == 0 and p0["rRar"] >= 0
    assert p0["bevUrl"] == f"/api/media/{env['jid']}/bev/{p0['sampleToken']}.png"
    # 01-CONTRACTS §4: thumbUrl = ảnh CAM_FRONT (chỉ để xem) nếu dataset có, ngược lại = bevUrl
    assert p0["thumbUrl"] in (p0["bevUrl"],
                              f"/api/media/{env['jid']}/thumbs/{p0['sampleToken']}_CAM_FRONT.webp")
    assert "LIDAR_TOP" not in p0["thumbUrl"]
    assert b["metrics"]["hybrid"]["nBoxes"] >= 0
    assert "sceneRecall" in b["metrics"]["hybrid"] and "nRecall" in b["metrics"]["hybrid"]


def test_select_advanced_params_flow_through(client, env):
    r = client.post(f"/jobs/{env['jid']}/select",
                    json={**PARAMS, "tier": 0, "k": 5, "lam": 0.5, "maxPerScene": 2,
                          "quotaOff": False, "alpha": 1, "beta": 0, "gamma": 0})
    assert r.status_code == 200, r.text
    p = r.json()["params"]
    assert (p["tier"], p["k"], p["lam"], p["m"]) == (0, 5, 0.5, 2)
    assert p["quotaOff"] is False
    assert (p["alpha"], p["beta"], p["gamma"]) == (1.0, 0.0, 0.0)


def test_select_quota_off_removes_scene_cap(client, env):
    b = client.post(f"/jobs/{env['jid']}/select", json={**PARAMS, "quotaOff": True}).json()
    assert b["params"]["m"] is None and b["params"]["quotaOff"] is True


def test_tier0_forces_rarity_weights_and_warns(client, env):
    # k=8 để bộ tham số đã chuẩn hoá là duy nhất: result.json được cache theo tham số ĐÃ giải,
    # nên cảnh báo chỉ có ở lần tính đầu (pipeline lidar tái dùng kết quả cũ).
    b = client.post(f"/jobs/{env['jid']}/select",
                    json={**PARAMS, "beta": 0.3, "gamma": 0.2, "k": 8}).json()
    assert (b["params"]["alpha"], b["params"]["beta"], b["params"]["gamma"]) == (1.0, 0.0, 0.0)
    assert b["params"]["k"] == 8
    assert any("Tầng 0" in w for w in b["warnings"]), b["warnings"]


def test_tier1_without_signals_is_422_tier_unavailable(client, env):
    r = client.post(f"/jobs/{env['jid']}/select", json={**PARAMS, "tier": 1})
    assert r.status_code == 422, r.text
    assert r.json()["error"]["code"] == "tier_unavailable"
    assert "tier_unavailable" in r.json()["error"]["message"]


def test_lidar_other_value_error_is_422_bad_params(client, env):
    r = client.post(f"/jobs/{env['jid']}/select",
                    json={**PARAMS, "alpha": 0, "beta": 0, "gamma": 0})
    assert r.status_code == 422, r.text
    assert r.json()["error"]["code"] == "bad_params"


def test_params_schema_fields_and_tiers(client, env):
    r = client.get(f"/jobs/{env['jid']}/params-schema")
    assert r.status_code == 200, r.text
    b = r.json()
    assert b["tierAvailable"] == [0]
    assert {f["key"] for f in b["fields"]} == {"tier", "k", "lam", "maxPerScene", "quotaOff",
                                               "alpha", "beta", "gamma"}
    k = next(f for f in b["fields"] if f["key"] == "k")
    assert (k["min"], k["max"], k["step"], k["type"]) == (3, 50, 1, "int")
    assert all("label" in f and "default" in f for f in b["fields"])


def test_params_schema_on_camera_job_is_404_not_lidar(tmp_path):
    settings = Settings(workspace=tmp_path / "ws", sevenzip="__khong_co_7z__")
    d = settings.jobs / "cam1"
    d.mkdir(parents=True)
    (d / "job.json").write_text(json.dumps(dict(
        jobId="cam1", datasetId="d", pipeline="camera", createdAt="2026-01-01T00:00:00",
        state="done")), encoding="utf-8")
    (d / "status.json").write_text(json.dumps(dict(
        jobId="cam1", state="done", stage="merge", pipeline="camera", done=1, total=1)),
        encoding="utf-8")
    with TestClient(create_app(settings, runner=lambda *a, **k: {})) as c:
        r = c.get("/jobs/cam1/params-schema")
        assert r.status_code == 404 and r.json()["error"]["code"] == "not_lidar"
        assert c.get("/jobs/khong-co/params-schema").status_code == 404


def test_frames_list_has_rrar_and_bev_url(client, env):
    r = client.get(f"/jobs/{env['jid']}/selections/{env['sid10']}/frames",
                   params={"budget": 0.10})
    assert r.status_code == 200, r.text
    b = r.json()
    assert b["budgetB"] == 2 and b["total"] == len(b["items"]) == 2
    for it in b["items"]:
        assert isinstance(it["rRar"], float) and it["bevUrl"].endswith(
            f"/bev/{it['sampleToken']}.png")
        assert it["thumbUrl"] in (it["bevUrl"], f"/api/media/{env['jid']}/thumbs/"
                                  f"{it['sampleToken']}_CAM_FRONT.webp")
        assert it["bestCam"] == "LIDAR_TOP" and it["rQry"] == 0
        assert it["sceneName"].startswith("scene")


def test_frames_sort_by_score_uses_lidar_column(client, env):
    r = client.get(f"/jobs/{env['jid']}/selections/{env['sid10']}/frames",
                   params={"budget": 0.10, "sort": "score"})
    assert r.status_code == 200, r.text
    s = [i["S"] for i in r.json()["items"]]
    assert s == sorted(s, reverse=True)


def test_frame_detail_lidar_has_viewer_media(client, env):
    tok = client.get(f"/jobs/{env['jid']}/selections/{env['sid10']}/frames",
                     params={"budget": 0.10}).json()["items"][0]["sampleToken"]
    r = client.get(f"/jobs/{env['jid']}/frames/{tok}", params={"sid": env["sid10"]})
    assert r.status_code == 200, r.text
    d = r.json()
    assert d["sampleToken"] == tok and d["bevUrl"].endswith(f"/bev/{tok}.png")
    assert d["timestamp"] > 0 and d["rank"] >= 1 and d["bestCam"] == "LIDAR_TOP"
    # stage lidar_index xuất phần HIỂN THỊ cho viewer (E2E 2026-10-08: viewer báo "không có LiDAR")
    assert d["lidar"] is not None and d["lidar"]["numPoints"] > 0
    assert len(d["cams"]) >= 1 and len(d["camPoses"]) == len(d["cams"])
    assert len(d["boxes3d"]) >= 1  # dataset giả có annotation


def test_analysis_and_export_for_lidar_selection(client, env):
    base = f"/jobs/{env['jid']}/selections/{env['sid']}"
    a = client.get(f"{base}/analysis")
    assert a.status_code == 200, a.text
    assert a.json()["pool"]["hasLidar"] is True and a.json()["pool"]["frames"] == N
    e = client.get(f"{base}/export.csv")
    assert e.status_code == 200 and e.text.splitlines()[0] == "method,seed,rank,sample_token," \
        "scene_token,s,max_sim,mmr_util,reason,budget_B"
    assert "hybrid" in e.text
