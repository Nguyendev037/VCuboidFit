#!/usr/bin/env python
"""Colab agent: keo viec Tang 1 tu worker, train + suy luan, day signals.parquet ve.

Dung: python colab_agent.py --server https://<tunnel> --token $VCF_REMOTE_TOKEN --work /content/vcf [--once]
Chi dung thu vien chuan + requests (pandas/pyarrow chi nap lazily o --dry-run).
Token KHONG BAO GIO duoc in ra log.
"""
from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
import tarfile
import tempfile
import threading
import time
from pathlib import Path

import requests

# Hanh vi theo bang loi 01-CONTRACTS §5
BACKOFF = (5, 15, 45)  # retry mang/5xx
IDLE_SEC = 60


class Stop(Exception):
    """Loi cau hinh/bao mat: dung agent, khong retry."""

    def __init__(self, msg: str, code: int):
        super().__init__(msg)
        self.code = code


class NotLeased(Exception):
    """409 not_leased: bo task, quay lai next."""


class TaskRejected(Exception):
    """422/413 khi gui ket qua: bao /fail, khong lap vo han."""


def log(msg: str) -> None:
    print(time.strftime("%H:%M:%S"), msg, flush=True)


class Client:
    def __init__(self, server: str, token: str, sleep=time.sleep):
        self.base = server.rstrip("/")
        self.s = requests.Session()
        self.s.headers["Authorization"] = f"Bearer {token}"
        self.sleep = sleep

    def _code(self, r: requests.Response) -> str:
        try:
            return (r.json().get("error") or {}).get("code", "")
        except ValueError:
            return ""

    def check(self, r: requests.Response) -> requests.Response:
        """Anh xa ma loi -> hanh vi; 5xx tra ve cho vong retry."""
        if r.status_code == 401:
            raise Stop("token bi tu choi (401) - dung, khong retry", 2)
        if r.status_code == 404 and self._code(r) == "remote_disabled":
            raise Stop("worker chua bat VCF_REMOTE_TOKEN", 3)
        if r.status_code == 409 and self._code(r) == "not_leased":
            raise NotLeased()
        if r.status_code in (413, 422):
            raise TaskRejected(f"{r.status_code} {self._code(r)}")
        if r.status_code >= 500:
            raise requests.ConnectionError(f"HTTP {r.status_code}")
        return r

    def call(self, method: str, path: str, **kw) -> requests.Response:
        """Retry 3 lan backoff 5/15/45 s cho mang/5xx; loi cuoi ne ra ngoai."""
        kw.setdefault("timeout", 60)
        for i in range(len(BACKOFF) + 1):
            try:
                return self.check(self.s.request(method, self.base + path, **kw))
            except (requests.ConnectionError, requests.Timeout) as e:
                if i == len(BACKOFF):
                    raise
                log(f"loi mang ({type(e).__name__}), thu lai sau {BACKOFF[i]} s")
                self.sleep(BACKOFF[i])
        raise AssertionError("unreachable")


def safe_extract(tf: tarfile.TarFile, member: tarfile.TarInfo, dest: Path) -> None:
    name = member.name
    parts = Path(name).parts
    if (not member.isreg() or name.startswith(("/", "\\")) or ".." in parts
            or (parts and ":" in parts[0])):
        return  # bo qua: chi nhan file thuong, duong dan tuong doi
    target = dest.joinpath(*parts)
    target.parent.mkdir(parents=True, exist_ok=True)
    src = tf.extractfile(member)
    with open(target, "wb") as f:
        shutil.copyfileobj(src, f, 1 << 20)


def fetch_bundle(c: Client, task: dict, work: Path) -> tuple[Path, Path]:
    """Tai bundle. Tra ve (exp_dir, data_dir). Cache data/ theo datasetId."""
    tid, ds = task["taskId"], task["datasetId"]
    exp = work / tid / "exp"
    exp.mkdir(parents=True, exist_ok=True)
    cache = work / "cache" / ds
    data = cache / "data"
    hit = data.is_dir()
    tmp_data = Path(tempfile.mkdtemp(prefix="data.", dir=str(work))) if not hit else None
    r = c.call("GET", f"/remote/t1/{tid}/bundle", stream=True, timeout=(30, 300))
    try:
        with tarfile.open(fileobj=r.raw, mode="r|") as tf:
            for m in tf:
                if m.name == "index.parquet":
                    safe_extract(tf, m, exp)
                    if hit:
                        log(f"cache hit: dataset {ds} - bo qua tai data/")
                        break  # index la phan tu dau; dong ket noi, khong keo data/
                elif m.name.startswith("data/") and not hit:
                    safe_extract(tf, m, tmp_data)
    finally:
        r.close()
    if not (exp / "index.parquet").is_file():
        raise TaskRejected("bundle thieu index.parquet")
    if not hit:
        sub = tmp_data / "data"
        cache.mkdir(parents=True, exist_ok=True)
        if sub.is_dir():
            os.replace(sub, data)
        else:
            data.mkdir(parents=True, exist_ok=True)
        shutil.rmtree(tmp_data, ignore_errors=True)
        log(f"cache miss: da tai data/ cho dataset {ds}")
    return exp, data


class Heartbeat(threading.Thread):
    def __init__(self, c: Client, tid: str, interval: float):
        super().__init__(daemon=True)
        self.c, self.tid, self.interval = c, tid, interval
        self.stage, self.progress = "train", 0.0
        self.stop_ev = threading.Event()
        self.sent = 0

    def run(self):
        while True:  # nhip dau gui ngay lap tuc
            try:
                self.c.call("POST", f"/remote/t1/{self.tid}/heartbeat",
                            json={"stage": self.stage, "progress": self.progress})
                self.sent += 1
            except Exception as e:  # heartbeat hong khong duoc giet viec dang chay
                log(f"heartbeat loi: {type(e).__name__}")
            if self.stop_ev.wait(self.interval):
                return

    def stop(self):
        self.stop_ev.set()
        self.join(timeout=10)


def dry_signals(exp: Path) -> Path:
    import pandas as pd  # lazy: chi o --dry-run
    toks = pd.read_parquet(exp / "index.parquet", columns=["sample_token"])["sample_token"]
    df = pd.DataFrame(dict(sample_token=toks.astype("string").to_numpy(dtype=object),
                           ent=0.0, inc=0.0, n_det=0, nov=0.0))
    df = df.astype(dict(sample_token="string", ent="float32", inc="float32", n_det="int32",
                        nov="float32"))
    out = exp / "t1" / "signals.parquet"
    out.parent.mkdir(parents=True, exist_ok=True)
    df.to_parquet(out, index=False)
    return out


class StageError(Exception):
    pass


def run_stage(args_list: list[str], env: dict, cwd: Path) -> None:
    log("chay: " + " ".join(args_list))
    p = subprocess.run(args_list, env=env, cwd=str(cwd), stdout=subprocess.PIPE,
                       stderr=subprocess.PIPE, text=True, errors="replace")
    if p.stdout:
        print(p.stdout[-4000:], flush=True)
    if p.returncode != 0:
        raise StageError((p.stderr or "")[-2000:] or f"exit {p.returncode}")


def process(c: Client, task: dict, a) -> None:
    tid = task["taskId"]
    work = Path(a.work)
    work.mkdir(parents=True, exist_ok=True)
    params = task.get("params") or {}
    ep, sw, ba = params.get("epochs", 20), params.get("sweeps", 1), params.get("batch", 4)
    log(f"nhan viec {tid} (job {task['jobId']}, epochs={ep} sweeps={sw} batch={ba})")
    hb = None
    try:
        exp, data = fetch_bundle(c, task, work)
        hb = Heartbeat(c, tid, a.heartbeat_sec)
        hb.start()
        t0 = time.monotonic()
        if a.dry_run:
            sig = dry_signals(exp)
            train_s = infer_s = 0.0
            hb.stage, hb.progress = "infer", 0.9
        else:
            env = dict(os.environ)
            py = sys.executable
            run_stage([py, "-m", "c4.lidar.tier1.train_seed", "--exp", str(exp), "--nusc",
                       str(data), "--sweeps", str(sw), "--epochs", str(ep), "--batch", str(ba)],
                      env, work)
            train_s = time.monotonic() - t0
            hb.stage, hb.progress = "infer", 0.7
            t1 = time.monotonic()
            run_stage([py, "-m", "c4.lidar.tier1.infer_t1", "--exp", str(exp), "--batch",
                       str(ba)], env, work)
            infer_s = time.monotonic() - t1
            sig = exp / "t1" / "signals.parquet"
        hb.stop()
        hb = None
        man = sig.with_suffix(".manifest.json")
        meta = dict(trainSec=round(train_s, 2), inferSec=round(infer_s, 2),
                    gpu=gpu_name(a.dry_run), seedEval={})
        files = {"signals": ("signals.parquet", open(sig, "rb"))}
        if man.is_file():
            files["manifest"] = ("signals.manifest.json", open(man, "rb"))
        try:
            c.call("POST", f"/remote/t1/{tid}/result", files=files,
                   data={"meta": json.dumps(meta)}, timeout=(30, 600))
        finally:
            for _, f in files.values():
                f.close()
        log(f"da gui ket qua {tid}")
    except StageError as e:
        _fail(c, tid, str(e))
    except TaskRejected as e:
        _fail(c, tid, f"bi tu choi: {e}")
    finally:
        if hb is not None:
            hb.stop()


def _fail(c: Client, tid: str, msg: str) -> None:
    log(f"viec {tid} that bai: {msg[-300:]}")
    try:
        c.call("POST", f"/remote/t1/{tid}/fail", json={"error": msg[-2000:]})
    except NotLeased:
        pass


def gpu_name(dry: bool) -> str:
    if dry:
        return "dry-run"
    try:
        out = subprocess.run(["nvidia-smi", "--query-gpu=name", "--format=csv,noheader"],
                             capture_output=True, text=True, timeout=10).stdout.strip()
        return out.splitlines()[0] if out else "cpu"
    except Exception:
        return "unknown"


def loop(a, sleep=time.sleep) -> int:
    c = Client(a.server, a.token, sleep)
    try:
        while True:
            try:
                r = c.call("GET", "/remote/t1/next")
            except (requests.ConnectionError, requests.Timeout) as e:
                log(f"khong ket noi duoc worker ({type(e).__name__})")
                if a.once:
                    return 1
                sleep(IDLE_SEC)
                continue
            if r.status_code == 204:
                if a.once:
                    log("khong co viec")
                    return 0
                sleep(IDLE_SEC)
                continue
            task = r.json()
            try:
                process(c, task, a)
            except NotLeased:
                log(f"viec {task['taskId']} het han lease, bo qua")
            except (requests.ConnectionError, requests.Timeout) as e:
                log(f"mat ket noi khi xu ly {task['taskId']}: {type(e).__name__}")
                if a.once:
                    return 1
                sleep(IDLE_SEC)
                continue
            if a.once:
                return 0
    except Stop as e:
        log(str(e))
        return e.code


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="Colab agent Tang 1 (keo viec tu worker).")
    ap.add_argument("--server", required=True, help="URL tunnel cua worker")
    ap.add_argument("--token", default=os.environ.get("VCF_REMOTE_TOKEN", ""),
                    help="mac dinh lay tu bien VCF_REMOTE_TOKEN")
    ap.add_argument("--work", default="/content/vcf", help="thu muc lam viec + cache")
    ap.add_argument("--once", action="store_true", help="xu ly toi da 1 viec roi thoat")
    ap.add_argument("--dry-run", action="store_true",
                    help="bo train/infer, ghi signals.parquet gia (test khong GPU)")
    ap.add_argument("--heartbeat-sec", type=float, default=60, help=argparse.SUPPRESS)
    a = ap.parse_args(argv)
    if not a.token:
        ap.error("thieu --token (hoac bien VCF_REMOTE_TOKEN)")
    return loop(a)


if __name__ == "__main__":
    sys.exit(main())
