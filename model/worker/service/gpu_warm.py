"""On-demand GPU warm-up (SPEC-P05 W2/W4/W5).

Official Vast REST references, checked 2026-10-16 (documentation only):
https://docs.vast.ai/api-reference/creating-instances-with-api
https://docs.vast.ai/api-reference/search/search-offers
https://vast.ai/developers/api (instances listing: v0 returns 410
deprecated_endpoint since 2026-10; use v1, same {"instances": [...]} shape)

D29: only read/search calls retry. An ambiguous create PUT stays starting for
20 minutes, then reports create-unknown without unlocking another rental.
The attempt is persisted before sending; no account key or token is persisted.
"""
import json
import math
import os
import shlex
import time
from datetime import datetime, timezone
from typing import Literal
from urllib.parse import quote

import httpx
from fastapi import APIRouter, Request
from filelock import FileLock
from pydantic import BaseModel

from service.errors import ApiError

LABEL = "vcuboidfit-agent"
GPU_NAMES = ("RTX_3060", "RTX_3090", "RTX_4090", "RTX_A5000")
IMAGE = "pytorch/pytorch:2.1.2-cuda11.8-cudnn8-devel"


class GpuStatus(BaseModel):
    state: Literal["ready", "starting", "idle", "disabled", "error"]
    reason: str | None = None
    since: str | None = None


class VastError(Exception):
    def __init__(self, reason="vast-unreachable"):
        self.reason = reason
        super().__init__(reason)  # never expose upstream bodies or credentials


class VastClient:
    """Small injectable REST boundary; each attempt has a 10-second timeout."""

    def __init__(self, api_key: str, transport=None):
        self._api_key = api_key
        self._transport = transport

    def _request(self, method, path, body=None, *, retry=True):
        for attempt in range(2 if retry else 1):
            try:
                with httpx.Client(timeout=10.0, transport=self._transport) as client:
                    response = client.request(
                        method, "https://console.vast.ai/api/" + path,
                        headers={"Authorization": "Bearer " + self._api_key}, json=body)
                if response.status_code in (401, 403):
                    raise VastError("vast-auth")
                if response.status_code >= 500:
                    if retry and attempt == 0:
                        continue
                    raise VastError()
                if response.is_error:
                    raise VastError()
                result = response.json()
                if not isinstance(result, dict) or result.get("success") is False:
                    raise VastError()
                return result
            except httpx.TransportError:
                if retry and attempt == 0:
                    continue
                raise VastError() from None
            except ValueError:
                raise VastError() from None
        raise VastError()

    def instances(self):
        result = self._request("GET", "v1/instances/").get("instances")
        if not isinstance(result, list) or not all(isinstance(x, dict) for x in result):
            raise VastError()
        return result

    def offers(self, max_dph):
        result = self._request("POST", "v0/bundles/", {
            # The search API matches display names ("RTX 3060"); underscores match nothing.
            "gpu_name": {"in": [name.replace("_", " ") for name in GPU_NAMES]}, "num_gpus": {"eq": 1},
            "cuda_max_good": {"gte": 11.8}, "reliability": {"gt": 0.98},
            "dph_total": {"lte": max_dph}, "disk_space": {"gte": 40},
            "rentable": {"eq": True}, "rented": {"eq": False},
            # An unverified host sat in "Creating..." for 40+ minutes (2026-10-17).
            "verified": {"eq": True},
            "type": "ondemand", "allocated_storage": 40,
            "order": [["dph_total", "asc"]],
        }).get("offers")
        if not isinstance(result, list):
            raise VastError()
        return result

    def create(self, offer_id, payload):
        result = self._request("PUT", f"v0/asks/{int(offer_id)}/", payload, retry=False)
        instance_id = result.get("new_contract")
        if not isinstance(instance_id, int) or isinstance(instance_id, bool):
            raise VastError()
        return instance_id

    def start(self, instance_id):
        # Resume a stopped instance; same endpoint the agent uses to stop itself.
        self._request("PUT", f"v0/instances/{int(instance_id)}/", {"state": "running"}, retry=False)


def _iso(ts):
    return datetime.fromtimestamp(ts, timezone.utc).isoformat(timespec="seconds")


def _timestamp(value):
    if not isinstance(value, str):
        return None
    try:
        # RemoteQueue historically uses naive local datetime.now().
        return datetime.fromisoformat(value).timestamp()
    except ValueError:
        return None


class GpuWarmer:
    def __init__(self, settings, remote, client_factory=VastClient, clock=time.time):
        self.settings, self.remote = settings, remote
        self.client_factory, self.clock = client_factory, clock
        self.directory = settings.workspace / "gpu"
        self.path = self.directory / "warm.json"

    def _load(self):
        try:
            record = json.loads(self.path.read_text(encoding="utf-8"))
            if not isinstance(record, dict):
                raise ValueError
            return record
        except FileNotFoundError:
            return {}
        except (OSError, ValueError):
            # A corrupt rate-limit record must never unlock a new rental.
            raise VastError() from None

    def _save(self, record):
        tmp = self.path.with_suffix(".tmp")
        tmp.write_text(json.dumps(record), encoding="utf-8")
        tmp.replace(self.path)

    def _offer(self, offers, max_dph):
        valid = []
        for offer in offers:
            try:
                price = float(offer["dph_total"])
                if (str(offer["gpu_name"]).replace(" ", "_") in GPU_NAMES
                        and offer["num_gpus"] == 1
                        and float(offer["cuda_max_good"]) >= 11.8
                        and float(offer["reliability"]) > 0.98
                        and math.isfinite(price) and 0 <= price <= max_dph):
                    int(offer["id"])
                    valid.append(offer)
            except (KeyError, ValueError, TypeError):
                continue
        return min(valid, key=lambda x: float(x["dph_total"])) if valid else None

    def _payload(self):
        server = os.environ.get("VCF_SERVER", "").strip()
        if not server or not self.settings.remote_token:
            raise VastError()  # incomplete server configuration: do not rent
        ref = os.environ.get("VCF_VAST_REF", "main") or "main"
        url = ("https://raw.githubusercontent.com/Nguyendev037/VCuboidFit/"
               + quote(ref, safe="/") + "/deploy/vast/onstart.sh")
        return {
            "image": IMAGE, "disk": 40, "label": LABEL, "runtype": "ssh_direct",
            "env": {"VCF_SERVER": server, "VCF_REMOTE_TOKEN": self.settings.remote_token,
                    "VCF_IDLE_MIN": "15", "VCF_VAST_REF": ref},
            # The pytorch image has no curl; fetch with Python like onstart.sh does.
            "onstart": "python3 -c " + shlex.quote(
                f"import urllib.request as u; u.urlretrieve({url!r}, '/tmp/vcf-onstart.sh')")
                       + " && bash /tmp/vcf-onstart.sh",
        }

    def status(self, *, warm=False):
        # A live agent (e.g. rented by hand) is ready even when autostart is off.
        now = self.clock()
        seen = _timestamp(self.remote.last_seen)
        if seen is not None and 0 <= now - seen <= 120:
            return GpuStatus(state="ready", since=self.remote.last_seen)
        key = os.environ.get("VAST_API_KEY", "").strip()
        if not key or os.environ.get("VCF_GPU_AUTOSTART") != "1":
            return GpuStatus(state="disabled")
        if not os.environ.get("VCF_SERVER", "").strip():
            return GpuStatus(state="disabled", reason="no-server-url")
        try:
            self.directory.mkdir(parents=True, exist_ok=True)
            # OS-backed lock shared by threads AND worker processes on this volume.
            with FileLock(str(self.directory / "warm.lock")):
                return self._locked(now, key, warm)
        except (VastError, OSError) as exc:
            return GpuStatus(state="error", reason=(
                exc.reason if isinstance(exc, VastError) else "vast-unreachable"))

    def _locked(self, now, key, warm):
        record = self._load()
        created = _timestamp(record.get("createdAt"))
        since = record.get("createdAt")
        client = self.client_factory(key)
        instances = [x for x in client.instances() if x.get("label") == LABEL]
        seen = _timestamp(self.remote.last_seen)
        contacted = created is not None and seen is not None and seen >= created
        if instances and all(x.get("cur_state") == "stopped" for x in instances):
            # Idle agents stop (not destroy) themselves: resume one instead of renting.
            # Its environment is already installed, so it is ready much sooner.
            if not warm:
                return GpuStatus(state="idle")
            target = instances[0]
            resumed = _timestamp(record.get("resumedAt"))
            if (record.get("resumedId") != target.get("id") or resumed is None
                    or now - resumed >= 10 * 60):
                client.start(target["id"])
                since = _iso(now)
                record = {"createdAt": since, "resumedAt": since, "resumedId": target["id"],
                          "instanceId": target["id"], "ambiguous": False}
                self._save(record)
            return GpuStatus(state="starting", since=record.get("createdAt"))
        if instances:
            if created is None or record.get("ambiguous"):
                # External/manual instance: remember when first observed, never rent another.
                since = _iso(now)
                record.update(createdAt=since, ambiguous=False)
                self._save(record)
                created = now
            if not contacted and now - created >= 25 * 60:
                return GpuStatus(state="error", reason="agent-timeout", since=since)
            return GpuStatus(state="starting", since=since)
        if record.get("ambiguous"):
            # Never retry an uncertain rental, including after the 20-minute window.
            attempt = _timestamp(record.get("attemptedAt"))
            if attempt is not None and now - attempt < 20 * 60:
                return GpuStatus(state="starting", since=record["attemptedAt"])
            return GpuStatus(state="error", reason="create-unknown",
                             since=record.get("attemptedAt"))
        if contacted or (created is not None and now - created >= 20 * 60):
            # A previously healthy agent has self-destroyed after idle, or a stuck
            # instance was removed by hand. Allow another dashboard visit to warm a
            # fresh instance, retaining cooldown.
            record.pop("createdAt", None)
            record.pop("instanceId", None)
            self._save(record)
            created, since = None, None
        if created is not None:
            if not contacted and now - created >= 25 * 60:
                return GpuStatus(state="error", reason="agent-timeout", since=since)
            if now - created < 20 * 60:
                return GpuStatus(state="starting", since=since)
        attempt = _timestamp(record.get("attemptedAt"))
        if attempt is not None and now - attempt < 10 * 60:
            return GpuStatus(state="error", reason="vast-unreachable",
                             since=record["attemptedAt"])
        if not warm:
            return GpuStatus(state="idle")
        if os.environ.get("VCF_VAST_ALLOW_RENT") != "1":
            # Owner rule (2026-10-17): renting a new machine needs their approval.
            # Without the opt-in only an existing labelled machine is resumed.
            return GpuStatus(state="idle", reason="rent-needs-approval")
        payload = self._payload()
        try:
            max_dph = float(os.environ.get("VCF_VAST_MAX_DPH", "0.6"))
            if not math.isfinite(max_dph) or max_dph <= 0:
                raise ValueError
        except ValueError:
            raise VastError() from None
        offer = self._offer(client.offers(max_dph), max_dph)
        if offer is None:
            return GpuStatus(state="error", reason="no-offer")
        # Persist BEFORE PUT: a crash/timeout cannot unlock an immediate duplicate.
        record = {"attemptedAt": _iso(now), "ambiguous": True}
        self._save(record)
        try:
            instance_id = client.create(offer["id"], payload)
        except VastError as exc:
            if exc.reason == "vast-auth":
                raise
            return GpuStatus(state="starting", since=record["attemptedAt"])
        record.update(createdAt=_iso(now), instanceId=instance_id, ambiguous=False)
        self._save(record)
        return GpuStatus(state="starting", since=record["createdAt"])


router = APIRouter()


def _manager(request):
    # Demo Basic Auth is enforced by the same Next middleware as /api/jobs/*.
    if request.app.state.settings.sessions and not request.state.session_id:
        raise ApiError(404, "not_found", "Không tìm thấy phiên.")
    return request.app.state.gpu_warm


@router.post("/gpu/warm", response_model=GpuStatus)
def warm_gpu(request: Request):
    return _manager(request).status(warm=True)


@router.get("/gpu/status", response_model=GpuStatus)
def gpu_status(request: Request):
    return _manager(request).status()
