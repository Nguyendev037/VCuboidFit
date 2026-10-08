import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError

from service.main import create_app
from service.models import SelectParamsIn
from service.settings import Settings


@pytest.fixture
def client(tmp_path):
    return TestClient(create_app(Settings(workspace=tmp_path)))


def test_budget_out_of_range_rejected():
    with pytest.raises(ValidationError):
        SelectParamsIn(budget=0.5)
    with pytest.raises(ValidationError):
        SelectParamsIn(budget=0.001)


@pytest.mark.parametrize("field,value", [
    ("maxPerScene", 0), ("maxPerScene", 51), ("minGap", 0), ("alpha", 1.5), ("beta", -0.1),
    ("minLuma", 256), ("minBlurVar", 1001), ("queries", []), ("queries", ["x"] * 13),
    ("queries", [""]), ("queries", ["x" * 201]), ("cameras", []), ("cameras", ["CAM_X"]),
    ("tier", 2), ("tier", -1), ("k", 2), ("k", 51), ("lam", 1.5), ("lam", -0.1)])
def test_out_of_range_fields_rejected(field, value):
    with pytest.raises(ValidationError):
        SelectParamsIn.model_validate({field: value})


def test_camel_case_round_trip_and_defaults():
    p = SelectParamsIn.model_validate({"maxPerScene": 4, "minGap": 2, "minLuma": 10})
    assert (p.max_per_scene, p.min_gap, p.min_luma) == (4, 2, 10)
    assert p.model_dump(by_alias=True)["maxPerScene"] == 4
    assert p.budget == 0.05 and p.preset == "balanced" and p.diversity == "medium"


def test_to_select_params_maps_fields():
    p = SelectParamsIn.model_validate({
        "budget": 0.08, "preset": "rare_first", "queries": ["xe máy"], "cameras": ["CAM_FRONT"],
        "maxPerScene": 3, "minBlurVar": 20})
    sp = p.to_select_params()
    assert (sp.budget, sp.preset, sp.queries, sp.cameras) == \
        (0.08, "rare_first", ["xe máy"], ["CAM_FRONT"])
    assert (sp.max_per_scene, sp.min_blur_var, sp.min_gap) == (3, 20, None)


def test_bad_preset_rejected():
    with pytest.raises(ValidationError):
        SelectParamsIn(preset="nope")


def test_to_lidar_params_maps_advanced_fields():
    p = SelectParamsIn.model_validate({"tier": 1, "k": 7, "lam": 0.4, "maxPerScene": 6,
                                       "quotaOff": False, "alpha": 0.5, "beta": 0.25,
                                       "gamma": 0.25})
    lp = p.to_lidar_params()
    assert (lp.tier, lp.k, lp.lam, lp.max_per_scene, lp.quota_off) == (1, 7, 0.4, 6, False)
    assert (lp.alpha, lp.beta, lp.gamma) == (0.5, 0.25, 0.25)


def test_lidar_param_defaults_are_none_so_yaml_wins():
    lp = SelectParamsIn().to_lidar_params()
    assert (lp.tier, lp.k, lp.lam, lp.max_per_scene, lp.alpha) == (None,) * 5
    assert lp.quota_off is False and lp.preset == "balanced" and lp.diversity == "medium"


def test_health(client):
    r = client.get("/health")
    assert r.status_code == 200
    body = r.json()
    assert body["ok"] is True and isinstance(body["gpu"], bool) and body["profile"] == "local-4060"


def test_unknown_route_uses_error_envelope_vietnamese(client):
    r = client.get("/khong-co")
    assert r.status_code == 404
    err = r.json()["error"]
    assert err["code"] == "not_found" and "Không tìm thấy" in err["message"]

