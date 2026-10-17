"""A15: offline fakes only; execution awaits the requested test approval.

D29: ambiguous creates are never retried, including after the 20-minute window.
"""
import json
import threading
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime
from types import SimpleNamespace

import httpx
import pytest
from fastapi.testclient import TestClient

from service.gpu_warm import GpuWarmer, LABEL, VastClient, VastError, _iso
from service.main import create_app
from service.settings import Settings

NOW = 1_800_000_000.0
OFFER = {"id": 7, "gpu_name": "RTX_3090", "num_gpus": 1,
         "cuda_max_good": 11.8, "reliability": 0.99, "dph_total": 0.3}


class FakeVast:
    def __init__(self):
        self.existing = []
        self.available = [OFFER]
        self.calls = []
        self.created = []

    def instances(self):
        self.calls.append("instances")
        return self.existing

    def offers(self, max_dph):
        self.calls.append(("offers", max_dph))
        return self.available

    def create(self, offer_id, payload):
        self.calls.append("create")
        self.created.append((offer_id, payload))
        return 123


@pytest.fixture
def setup(tmp_path, monkeypatch):
    monkeypatch.setenv("VAST_API_KEY", "fake-account-secret")
    monkeypatch.setenv("VCF_GPU_AUTOSTART", "1")
    monkeypatch.setenv("VCF_SERVER", "https://example.test/api")
    monkeypatch.delenv("VCF_VAST_MAX_DPH", raising=False)
    monkeypatch.delenv("VCF_VAST_REF", raising=False)
    settings = Settings(workspace=tmp_path, remote_token="fake-remote-secret")
    remote = SimpleNamespace(last_seen=None)
    fake = FakeVast()
    manager = GpuWarmer(settings, remote, lambda _key: fake, clock=lambda: NOW)
    return manager, fake


def test_a15_existing_instance_never_creates(setup):
    manager, fake = setup
    fake.existing = [{"id": 123, "label": LABEL}]
    assert manager.status(warm=True).state == "starting"
    assert manager.status(warm=True).state == "starting"
    assert fake.created == []
    assert fake.calls == ["instances", "instances"]


def test_a15_parallel_warm_uses_shared_file_lock(setup):
    manager, fake = setup
    # Separate managers deliberately rule out a manager-local thread mutex.
    other = GpuWarmer(manager.settings, manager.remote, lambda _key: fake, clock=lambda: NOW)
    barrier = threading.Barrier(2)

    def warm(target):
        barrier.wait(timeout=5)
        return target.status(warm=True).state

    with ThreadPoolExecutor(max_workers=2) as pool:
        assert list(pool.map(warm, (manager, other))) == ["starting", "starting"]
    assert len(fake.created) == 1
    record = json.loads(manager.path.read_text())
    assert record["instanceId"] == 123
    assert "secret" not in manager.path.read_text()


@pytest.mark.parametrize("missing", ["VAST_API_KEY", "VCF_GPU_AUTOSTART"])
def test_a15_disabled_never_constructs_client_or_calls_network(setup, monkeypatch, missing):
    manager, fake = setup
    monkeypatch.delenv(missing)

    def forbidden(_key):
        pytest.fail("disabled constructed a network client")

    manager.client_factory = forbidden
    assert manager.status(warm=True).model_dump() == {
        "state": "disabled", "reason": None, "since": None}
    assert manager.status().state == "disabled"
    assert not manager.directory.exists()
    assert fake.calls == []


def test_recent_agent_is_ready_without_vast_calls(setup):
    manager, fake = setup
    manager.remote.last_seen = _iso(NOW - 119)
    assert manager.status(warm=True).state == "ready"
    assert fake.calls == []


def test_status_does_not_rent_and_stale_agent_is_not_ready(setup):
    manager, fake = setup
    manager.remote.last_seen = _iso(NOW - 121)
    assert manager.status().state == "idle"
    assert fake.created == []


def test_creation_payload_cheapest_eligible_and_no_key_persisted(setup, monkeypatch):
    manager, fake = setup
    monkeypatch.setenv("VCF_VAST_REF", "feature/gpu")
    fake.available = [dict(OFFER, id=1, dph_total=0.5),
                      dict(OFFER, id=2, dph_total=0.2, num_gpus=2),
                      dict(OFFER, id=3, dph_total=0.1, reliability=0.98),
                      dict(OFFER, id=4, dph_total=0.7), OFFER]
    assert manager.status(warm=True).state == "starting"
    offer_id, payload = fake.created[0]
    assert offer_id == OFFER["id"]
    assert payload["disk"] == 40
    assert payload["label"] == LABEL
    assert payload["image"] == "pytorch/pytorch:2.1.2-cuda11.8-cudnn8-devel"
    assert payload["env"] == {
        "VCF_SERVER": "https://example.test/api", "VCF_REMOTE_TOKEN": "fake-remote-secret",
        "VCF_IDLE_MIN": "15", "VCF_VAST_REF": "feature/gpu"}
    assert "/feature/gpu/deploy/vast/onstart.sh" in payload["onstart"]
    assert "curl" not in payload["onstart"] and payload["onstart"].startswith("python3 -c ")
    assert "fake-account-secret" not in str(payload)
    assert "secret" not in manager.path.read_text()


def test_no_eligible_offer_returns_no_offer(setup):
    manager, fake = setup
    fake.available = []
    assert manager.status(warm=True).reason == "no-offer"
    assert fake.created == []


def test_creation_time_survives_restart_and_timeout_does_not_delete(setup):
    manager, fake = setup
    assert manager.status(warm=True).state == "starting"
    later = GpuWarmer(manager.settings, manager.remote, lambda _key: fake,
                      clock=lambda: NOW + 25 * 60)
    assert later.status().model_dump() == {
        "state": "error", "reason": "agent-timeout", "since": _iso(NOW)}
    assert len(fake.created) == 1
    assert later.status(warm=True).reason == "agent-timeout"
    assert len(fake.created) == 1


def test_completed_agent_does_not_permanently_block_future_warm(setup):
    manager, fake = setup
    manager.status(warm=True)
    manager.remote.last_seen = _iso(NOW + 60)
    manager.clock = lambda: NOW + 60
    assert manager.status().state == "ready"
    manager.clock = lambda: NOW + 30 * 60
    assert manager.status(warm=True).state == "starting"
    assert len(fake.created) == 2


def test_successful_create_cooldown_still_applies_after_agent_disappears(setup):
    manager, fake = setup
    manager.status(warm=True)
    manager.remote.last_seen = _iso(NOW + 60)
    manager.clock = lambda: NOW + 5 * 60
    assert manager.status(warm=True).reason == "vast-unreachable"
    assert len(fake.created) == 1
    manager.clock = lambda: NOW + 10 * 60
    assert manager.status(warm=True).state == "starting"
    assert len(fake.created) == 2


@pytest.mark.parametrize("failure", ["5xx", "timeout"])
def test_ambiguous_create_not_retried_and_survives_restart(setup, failure):
    manager, fake = setup
    calls = []

    def handler(request):
        calls.append(request)
        if failure == "timeout":
            raise httpx.ReadTimeout("upstream-secret", request=request)
        return httpx.Response(503, json={"message": "upstream-secret"})

    def uncertain(_offer, _payload):
        fake.calls.append("create-uncertain")
        return VastClient("secret", httpx.MockTransport(handler)).create(_offer, _payload)

    fake.create = uncertain
    assert manager.status(warm=True).model_dump() == {
        "state": "starting", "reason": None, "since": _iso(NOW)}
    record = json.loads(manager.path.read_text())
    assert record == {"attemptedAt": _iso(NOW), "ambiguous": True}
    later = GpuWarmer(manager.settings, manager.remote, lambda _key: fake,
                      clock=lambda: NOW + 20 * 60 - 1)
    for warm in (False, True):
        assert later.status(warm=warm).model_dump() == {
            "state": "starting", "reason": None, "since": _iso(NOW)}
    for elapsed in (20 * 60, 60 * 60):
        later.clock = lambda: NOW + elapsed
        for warm in (False, True):
            assert later.status(warm=warm).model_dump() == {
                "state": "error", "reason": "create-unknown", "since": _iso(NOW)}
    assert fake.calls.count("create-uncertain") == 1
    assert len(calls) == 1
    assert json.loads(manager.path.read_text()) == record
    fake.existing = [{"id": 123, "label": LABEL}]
    assert later.status(warm=True).state == "starting"
    assert json.loads(manager.path.read_text())["ambiguous"] is False
    assert fake.calls.count("create-uncertain") == 1
    assert len(calls) == 1


def test_ambiguous_create_discovered_before_deadline(setup):
    manager, fake = setup
    manager.directory.mkdir()
    manager._save({"attemptedAt": _iso(NOW - 60), "ambiguous": True})
    fake.existing = [{"id": 123, "label": LABEL}]
    assert manager.status(warm=True).state == "starting"
    assert json.loads(manager.path.read_text())["ambiguous"] is False
    assert fake.created == []


def test_create_auth_error_is_reported_without_retry(setup):
    manager, fake = setup

    def unauthorized(_offer, _payload):
        fake.calls.append("create-unauthorized")
        raise VastError("vast-auth")

    fake.create = unauthorized
    assert manager.status(warm=True).model_dump() == {
        "state": "error", "reason": "vast-auth", "since": None}
    assert fake.calls.count("create-unauthorized") == 1


def test_corrupt_state_fails_closed(setup):
    manager, fake = setup
    manager.directory.mkdir()
    manager.path.write_text("broken", encoding="utf-8")
    assert manager.status(warm=True).reason == "vast-unreachable"
    assert fake.calls == []


@pytest.mark.parametrize("server", [None, "", "   "])
def test_missing_server_configuration_never_constructs_client(setup, monkeypatch, server):
    manager, fake = setup
    if server is None:
        monkeypatch.delenv("VCF_SERVER")
    else:
        monkeypatch.setenv("VCF_SERVER", server)

    def forbidden(_key):
        pytest.fail("missing server URL constructed a network client")

    manager.client_factory = forbidden
    manager.remote.last_seen = None  # a live agent is "ready" regardless (checked first)
    for warm in (False, True):
        assert manager.status(warm=warm).model_dump() == {
            "state": "disabled", "reason": "no-server-url", "since": None}
    assert not manager.directory.exists()
    assert fake.calls == []
    assert fake.created == []


@pytest.mark.parametrize("code", [401, 403])
def test_vast_auth_never_retried_or_leaked(code):
    calls = []

    def handler(request):
        calls.append(request)
        return httpx.Response(code, json={"message": "upstream-secret"})

    with pytest.raises(VastError, match="^vast-auth$"):
        VastClient("secret", httpx.MockTransport(handler)).instances()
    assert len(calls) == 1


@pytest.mark.parametrize("failure", ["5xx", "timeout"])
def test_vast_reads_retry_once_then_sanitize(failure):
    calls = []

    def handler(request):
        calls.append(request)
        if failure == "timeout":
            raise httpx.ReadTimeout("upstream-secret", request=request)
        return httpx.Response(503, json={"message": "upstream-secret"})

    with pytest.raises(VastError, match="^vast-unreachable$"):
        VastClient("secret", httpx.MockTransport(handler)).instances()
    assert len(calls) == 2


def test_vast_create_ambiguous_timeout_is_not_retried():
    calls = []

    def handler(request):
        calls.append(request)
        raise httpx.ReadTimeout("secret", request=request)

    with pytest.raises(VastError, match="^vast-unreachable$"):
        VastClient("secret", httpx.MockTransport(handler)).create(7, {})
    assert len(calls) == 1


def test_vast_search_rest_contract():
    calls = []

    def handler(request):
        calls.append(request)
        return httpx.Response(200, json={"offers": [OFFER]})

    assert VastClient("secret", httpx.MockTransport(handler)).offers(0.6) == [OFFER]
    request = calls[0]
    body = json.loads(request.content)
    assert request.method == "POST" and request.url.path == "/api/v0/bundles/"
    assert request.extensions["timeout"] == {
        "connect": 10.0, "read": 10.0, "write": 10.0, "pool": 10.0}
    assert body["dph_total"] == {"lte": 0.6}
    assert body["cuda_max_good"] == {"gte": 11.8}
    assert body["num_gpus"] == {"eq": 1}
    assert body["reliability"] == {"gt": 0.98}
    assert body["order"] == [["dph_total", "asc"]]
    assert body["gpu_name"] == {"in": ["RTX 3060", "RTX 3090", "RTX 4090", "RTX A5000"]}


def test_vast_instances_use_v1_listing():
    # GET /api/v0/instances/ answers 410 deprecated_endpoint (measured 2026-10-17).
    calls = []

    def handler(request):
        calls.append(request)
        return httpx.Response(200, json={"instances": [{"id": 1, "label": "x"}]})

    assert VastClient("secret", httpx.MockTransport(handler)).instances() == [{"id": 1, "label": "x"}]
    assert calls[0].method == "GET" and calls[0].url.path == "/api/v1/instances/"


def test_routes_mounted_session_required_and_remote_next_updates_seen(tmp_path, monkeypatch):
    monkeypatch.delenv("VAST_API_KEY", raising=False)
    settings = Settings(workspace=tmp_path, sessions=True, remote_token="agent-secret")
    app = create_app(settings)
    client = TestClient(app)
    assert client.post("/gpu/warm").status_code == 404
    assert client.get("/gpu/status").status_code == 404
    headers = {"X-VCF-Session": "a" * 32}
    assert client.post("/gpu/warm", headers=headers).json()["state"] == "disabled"
    assert client.get("/gpu/status", headers=headers).json()["state"] == "disabled"
    assert client.get("/remote/t1/next").status_code == 401
    assert app.state.remote.last_seen is None
    assert client.get("/remote/t1/next", headers={
        "Authorization": "Bearer agent-secret"}).status_code == 204
    assert app.state.remote.last_seen is not None


def test_successful_heartbeat_refreshes_last_seen(tmp_path):
    from service.remote import RemoteQueue

    settings = Settings(workspace=tmp_path, remote_lease_sec=5400)
    queue = RemoteQueue(settings, clock=lambda: datetime(2026, 10, 16, 12, 0))
    queue._save({"taskId": "t1_" + "a" * 12, "state": "leased", "leaseId": "lease",
                 "leaseUntil": "2026-10-16T13:00:00", "jobId": "a" * 12})
    queue.heartbeat("t1_" + "a" * 12, "inference", 0.5, "lease")
    assert queue.last_seen == "2026-10-16T12:00:00"


@pytest.mark.parametrize("missing", ["VAST_API_KEY", "VCF_GPU_AUTOSTART"])
def test_live_agent_is_ready_even_when_autostart_is_off(setup, monkeypatch, missing):
    # A GPU rented by hand must show "ready" on the dashboard without a Vast key.
    manager, fake = setup
    monkeypatch.delenv(missing)
    manager.remote.last_seen = _iso(NOW - 30)
    assert manager.status(warm=True).state == "ready"
    assert fake.calls == []
