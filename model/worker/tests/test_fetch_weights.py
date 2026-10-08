import http.server
import importlib.util
import threading
from pathlib import Path

import pytest

SCRIPT = Path(__file__).resolve().parents[2] / "scripts" / "fetch_weights.py"
spec = importlib.util.spec_from_file_location("fetch_weights", SCRIPT)
fw = importlib.util.module_from_spec(spec)
spec.loader.exec_module(fw)

PAYLOAD = bytes(range(256)) * 400  # 102 400 byte


def _serve(cut_first=0, always_cut=False):
    """Server: lần đầu cắt giữa chừng `cut_first` lần; hỗ trợ Range."""
    state = {"cuts": cut_first, "ranges": []}

    class H(http.server.BaseHTTPRequestHandler):
        def log_message(self, *a):
            pass

        def do_GET(self):
            rng = self.headers.get("Range")
            state["ranges"].append(rng)
            start = int(rng.split("=")[1].split("-")[0]) if rng else 0
            body = PAYLOAD[start:]
            self.send_response(206 if rng else 200)
            self.send_header("Content-Length", str(len(body)))
            if rng:
                last = len(PAYLOAD) - 1
                self.send_header("Content-Range", f"bytes {start}-{last}/{len(PAYLOAD)}")
            self.end_headers()
            if always_cut or state["cuts"] > 0:
                state["cuts"] -= 1
                self.wfile.write(body[: len(body) // 3])
                self.wfile.flush()
                self.close_connection = True
                return
            self.wfile.write(body)

    srv = http.server.ThreadingHTTPServer(("127.0.0.1", 0), H)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    return srv, state


def test_truncated_download_resumes_and_matches(tmp_path):
    srv, state = _serve(cut_first=2)
    try:
        target = tmp_path / "w.pt"
        fw.download(f"http://127.0.0.1:{srv.server_port}/w.pt", target, retries=3, backoff=0)
    finally:
        srv.shutdown()
    assert target.read_bytes() == PAYLOAD
    assert not (tmp_path / "w.pt.part").exists()
    assert state["ranges"][0] is None and all(r for r in state["ranges"][1:])


def test_incomplete_download_never_leaves_final_file(tmp_path):
    srv, _ = _serve(always_cut=True)
    try:
        target = tmp_path / "w.pt"
        with pytest.raises(RuntimeError):
            fw.download(f"http://127.0.0.1:{srv.server_port}/w.pt", target, retries=3, backoff=0)
    finally:
        srv.shutdown()
    assert not target.exists()
    assert (tmp_path / "w.pt.part").exists()
