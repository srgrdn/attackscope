"""Actual Vector HTTP encoding check using synthetic Nginx input only."""

import json
import os
import subprocess
import tempfile
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path

received = []


class Receiver(BaseHTTPRequestHandler):
    def do_POST(self) -> None:
        assert self.path == "/api/v1/ingest/events"
        assert self.headers["Authorization"] == "Bearer vector-smoke-placeholder"
        received.extend(json.loads(self.rfile.read(int(self.headers["Content-Length"]))))
        self.send_response(200)
        self.end_headers()
        self.wfile.write(b'{"accepted":1,"duplicates":0,"schema_version":1}')

    def log_message(self, *args: object) -> None:
        pass


root = Path(__file__).resolve().parents[1]
with (
    HTTPServer(("127.0.0.1", 0), Receiver) as server,
    tempfile.TemporaryDirectory(prefix="attackscope-vector-") as directory,
):
    threading.Thread(target=server.serve_forever, daemon=True).start()
    original = (root / "deploy/vector/nginx.yaml").read_text()
    config = (
        "data_dir: /tmp/vector-data\nsources:\n  nginx:\n    type: stdin\n"
        + original[original.index("transforms:") :]
    )
    config_path = Path(directory) / "vector.yaml"
    config_path.write_text(config)
    message = {
        "timestamp": "2026-11-03T00:00:00Z",
        "remote_addr": "2001:db8::1",
        "request_id": "vector-smoke:1",
        "hostname": "synthetic",
        "request_method": "GET",
        "path": "/.env?secret=removed",
        "status": 404,
        "dst_port": 443,
        "duration_seconds": 0.1,
        "user_agent": "synthetic",
        "Authorization": "NEVER_SEND",
        "Cookie": "NEVER_SEND",
    }
    subprocess.run(
        [
            "docker",
            "run",
            "--rm",
            "-i",
            "--network",
            "host",
            "--user",
            f"{os.getuid()}:{os.getgid()}",
            "--cap-drop",
            "ALL",
            "--security-opt",
            "no-new-privileges:true",
            "-e",
            f"ATTACKSCOPE_INGEST_URL=http://127.0.0.1:{server.server_port}/api/v1/ingest/events",
            "-e",
            "ATTACKSCOPE_SOURCE_TOKEN=vector-smoke-placeholder",
            "-v",
            f"{directory}:/config:ro",
            "timberio/vector:0.61.0-debian@sha256:f6c23b5a7e16fb2838d33619ef7acf4bad2289a7cf22bc90efc2371f520c4ea2",
            "--dangerously-allow-env-var-interpolation",
            "--config",
            "/config/vector.yaml",
        ],
        input=json.dumps(message) + "\n",
        text=True,
        capture_output=True,
        check=True,
        timeout=40,
    )
    server.shutdown()
assert len(received) == 1, received
assert received[0]["payload"]["path"] == "/.env"
assert received[0]["payload"]["duration_ms"] == 100
assert "NEVER_SEND" not in json.dumps(received)
print("Vector stdin → Nginx transform → authenticated HTTP JSON array: passed")
