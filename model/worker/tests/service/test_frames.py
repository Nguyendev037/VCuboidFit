import csv
import io
import os
import shutil
import time

import pytest
from fastapi.testclient import TestClient

from c4.contracts import CAMS, SELECTED
from service.datasets import _save, validate_dataset
from service.main import create_app
from service.settings import Settings
from tests.fixtures.make_nuscenes import make_nuscenes

# pipeline camera cần torch (cài `.[gpu]`); bản CPU chỉ chạy LiDAR ⇒ bỏ qua module này
pytest.importorskip("torch", reason="pipeline camera cần torch (.[gpu])")

PARAMS = {"minLuma": 0, "minBlurVar": 0}  # ảnh giả là màu phẳng: không để chất lượng loại hết


@pytest.fixture(scope="module")
def env(tmp_path_factory):
    """Một job thật (model giả) trên nuScenes giả 4 scene × 10 frame, scene1 mất CAM_BACK."""
    old = os.environ.get("C4_FAKE_MODELS")
    os.environ["C4_FAKE_MODELS"] = "1"
    ws = tmp_path_factory.mktemp("ws")
    settings = Settings(workspace=ws, sevenzip="__khong_co_7z__")
    data = make_nuscenes(settings.datasets / "d1", n_scenes=4, frames_per_scene=10,
                         drop_cams={"scene1": ["CAM_BACK"]})
    _save(settings, validate_dataset(data, "d1"))
    app = create_app(settings)
    with TestClient(app) as c:
        jid = c.post("/jobs", json={"datasetId": "d1", "pipeline": "camera"}).json()["jobId"]
        t0 = time.monotonic()
        while (st := c.get(f"/jobs/{jid}").json())["state"] not in ("done", "failed"):
            assert time.monotonic() - t0 < 600, "job quá lâu"
            time.sleep(0.5)
        assert st["state"] == "done", st
        sid = c.post(f"/jobs/{jid}/select", json=PARAMS).json()["selectionId"]
        yield dict(app=app, settings=settings, jid=jid, sid=sid)
    if old is None:
        os.environ.pop("C4_FAKE_MODELS", None)
    else:
        os.environ["C4_FAKE_MODELS"] = old


@pytest.fixture
def client(env):
    with TestClient(env["app"]) as c:
        yield c


def frames(client, env, **q):
    r = client.get(f"/jobs/{env['jid']}/selections/{env['sid']}/frames", params=q)
    assert r.status_code == 200, r.text
    return r.json()


def test_frames_default_budget(client, env):
    body = frames(client, env)
    assert body["budgetB"] == 2 and body["total"] == 2 and len(body["items"]) == 2
    assert [i["rank"] for i in body["items"]] == [1, 2]
    assert all(isinstance(i["tags"], list) for i in body["items"])


def test_budget_independent_of_selection_budget(client, env):
    body = frames(client, env, budget=0.08)
    assert body["budgetB"] == 4 and body["total"] == 4  # ceil(0.08 * 40), selection chỉ 5 %
    assert [i["rank"] for i in body["items"]] == [1, 2, 3, 4]
    assert all("tags" in i and i["thumbUrl"].endswith(".webp") for i in body["items"])
    item = body["items"][0]
    assert item["sceneName"].startswith("scene") and item["camsAvailable"]


def test_pagination(client, env):
    p1 = frames(client, env, budget=0.10, pageSize=3, page=1)
    p2 = frames(client, env, budget=0.10, pageSize=3, page=2)
    assert p1["total"] == p2["total"] == 4 and len(p1["items"]) == 3 and len(p2["items"]) == 1
    assert p2["items"][0]["rank"] == 4


def test_sort_by_score_descending(client, env):
    s = [i["S"] for i in frames(client, env, budget=0.10, sort="score")["items"]]
    assert s == sorted(s, reverse=True)


def test_tag_filter_exact_and_prefix(client, env):
    allrows = frames(client, env, budget=0.10)["items"]
    tags = [t for i in allrows for t in i["tags"]]
    assert tags, "dữ liệu giả phải sinh ít nhất một tag"
    tag = tags[0]
    exact = frames(client, env, budget=0.10, tag=tag)
    assert exact["total"] >= 1 and all(tag in i["tags"] for i in exact["items"])
    prefix = tag[:3]  # tiền tố ngắn hơn hẳn tag: khớp theo startswith, không phải bằng nhau
    assert len(prefix) < len(tag)
    pf = frames(client, env, budget=0.10, tag=prefix)
    assert pf["total"] >= exact["total"]
    assert all(any(t.startswith(prefix) for t in i["tags"]) for i in pf["items"])
    assert frames(client, env, budget=0.10, tag="Không-có-tag-này")["total"] == 0


def test_frames_bad_params_and_unknown_ids(client, env):
    base = f"/jobs/{env['jid']}/selections/{env['sid']}/frames"
    assert client.get(base, params={"budget": 0.5}).status_code == 400
    assert client.get(base, params={"pageSize": 0}).status_code == 400
    assert client.get(base, params={"sort": "lung-tung"}).status_code == 400
    assert client.get(f"/jobs/{env['jid']}/selections/000000000000/frames").status_code == 404
    assert client.get(f"/jobs/zzz/selections/{env['sid']}/frames").status_code == 404


def _detail(client, env, token):
    r = client.get(f"/jobs/{env['jid']}/frames/{token}", params={"sid": env["sid"]})
    assert r.status_code == 200, r.text
    return r.json()


def test_detail_lists_only_cams_on_disk_in_order(client, env):
    d1 = _detail(client, env, "scene1_f3")  # scene1 mất CAM_BACK
    assert [c["cam"] for c in d1["cams"]] == [c for c in CAMS if c != "CAM_BACK"]
    d0 = _detail(client, env, "scene0_f3")
    assert [c["cam"] for c in d0["cams"]] == CAMS
    assert d0["cams"][0]["imageUrl"] == \
        f"/api/media/{env['jid']}/images/samples/CAM_FRONT/scene0_f3__CAM_FRONT.jpg"
    assert all(c["width"] == 1600 and c["height"] == 900 for c in d0["cams"])
    assert [p["cam"] for p in d0["camPoses"]] == CAMS
    assert len(d0["camPoses"][0]["intrinsic"]) == 9 and d0["timestamp"] > 0


def test_detail_boxes_lidar_and_3d(client, env):
    d = _detail(client, env, "scene0_f3")
    boxes = [b for c in d["cams"] for b in c["boxes"]]
    assert boxes and all(len(b["corners"]) == 16 for b in boxes)
    assert {b["category"] for b in boxes} <= {"human.pedestrian.adult", "vehicle.motorcycle"}
    assert d["lidar"] == {"url": f"/api/media/{env['jid']}/lidar/scene0_f3.f16",
                          "numPoints": 300, "format": "f16-xyzi"}
    assert len(d["boxes3d"]) == 2 and all(len(b["corners"]) == 24 for b in d["boxes3d"])


@pytest.mark.parametrize("extra", [{}, {"preset": "hard_for_model"}, {"alpha": 1, "beta": 0,
                                                                         "gamma": 0.5}])
def test_detail_camera_score_matches_frame_score_for_best_cam(client, env, extra):
    """Chống lệch công thức: camera tốt nhất của frame phải có điểm = frame_scores (đủ ba trọng
    số khác nhau để một hoán đổi α/β/γ không lọt)."""
    sid = client.post(f"/jobs/{env['jid']}/select", json={**PARAMS, **extra}).json()["selectionId"]
    url = f"/jobs/{env['jid']}/selections/{sid}/frames"
    items = client.get(url, params={"budget": 0.10}).json()["items"]
    assert items
    for it in items:
        d = client.get(f"/jobs/{env['jid']}/frames/{it['sampleToken']}", params={"sid": sid}).json()
        best = next(c for c in d["cams"] if c["cam"] == it["bestCam"])
        assert best["qOk"] is True
        assert best["score"]["s"] == pytest.approx(it["S"], abs=1e-5)
        assert best["score"]["nov"] == pytest.approx(it["rNov"], abs=1e-5)
        assert best["score"]["unc"] == pytest.approx(it["rUnc"], abs=1e-5)
        assert best["score"]["qry"] == pytest.approx(it["rQry"], abs=1e-5)
        assert d["rank"] == it["rank"] and d["tags"] == it["tags"]


def test_detail_of_unselected_frame_has_rank_zero(client, env):
    ranked = {i["sampleToken"] for i in frames(client, env, budget=0.10)["items"]}
    token = next(f"scene3_f{i}" for i in range(10) if f"scene3_f{i}" not in ranked)
    d = _detail(client, env, token)
    assert d["rank"] == 0 and d["tags"] == []


def test_detail_without_annotations_or_lidar(client, env):
    s = env["settings"]
    shutil.copytree(s.jobs / env["jid"], s.jobs / "noann")
    shutil.rmtree(s.jobs / "noann" / "gt")
    shutil.rmtree(s.jobs / "noann" / "media" / "lidar")
    r = client.get("/jobs/noann/frames/scene0_f3", params={"sid": env["sid"]})
    assert r.status_code == 200, r.text
    d = r.json()
    assert d["boxes3d"] == [] and d["lidar"] is None
    assert all(c["boxes"] == [] for c in d["cams"])


def test_detail_unknown_token_or_missing_sid(client, env):
    assert client.get(f"/jobs/{env['jid']}/frames/khong-co",
                      params={"sid": env["sid"]}).status_code == 404
    assert client.get(f"/jobs/{env['jid']}/frames/scene0_f3").status_code == 400
    assert client.get(f"/jobs/{env['jid']}/frames/scene0_f3",
                      params={"sid": "000000000000"}).status_code == 404


def test_analysis_endpoint(client, env):
    r = client.get(f"/jobs/{env['jid']}/selections/{env['sid']}/analysis")
    assert r.status_code == 200, r.text
    a = r.json()
    assert {"pool", "selected", "histogram"} == set(a)
    assert a["pool"]["frames"] == 40 and len(a["histogram"]["counts"]) == 20
    assert isinstance(a["histogram"]["budgetThreshold"], float)


def test_export_csv(client, env):
    base = f"/jobs/{env['jid']}/selections/{env['sid']}/export.csv"
    r = client.get(base)
    assert r.status_code == 200 and r.headers["content-type"].startswith("text/csv")
    assert f"selected_{env['sid']}_5pct.csv" in r.headers["content-disposition"]
    rows = list(csv.reader(io.StringIO(r.text)))
    assert rows[0] == list(SELECTED)
    assert len(rows) - 1 == 2 and {row[0] for row in rows[1:]} == {"hybrid"}
    r10 = client.get(base, params={"budget": 0.10})
    assert len(list(csv.reader(io.StringIO(r10.text)))) - 1 == 4
    assert "10pct.csv" in r10.headers["content-disposition"]
    assert client.get(base, params={"budget": 0.5}).status_code == 400
