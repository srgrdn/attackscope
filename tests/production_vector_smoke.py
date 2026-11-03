"""Exercise production transforms, file secrets and disk-buffered HTTP delivery."""

import hashlib
import json
import subprocess
import tempfile
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path

received = []


class Receiver(BaseHTTPRequestHandler):
    def do_POST(self) -> None:
        batch = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
        for event in batch:
            assert self.headers["Authorization"] == "Bearer " + event["source"] + "-placeholder"
        received.extend(batch)
        self.send_response(200)
        self.end_headers()
        self.wfile.write(b'{"accepted":1,"duplicates":0,"schema_version":1}')

    def log_message(self, *args: object) -> None:
        pass


root = Path(__file__).resolve().parents[1]
with HTTPServer(("127.0.0.1", 0), Receiver) as server, tempfile.TemporaryDirectory() as directory:
    threading.Thread(target=server.serve_forever, daemon=True).start()
    original = (root / "deploy/production/vector.yaml").read_text()
    config = original[: original.index("sources:")]
    config += """sources:
  test_input:
    type: stdin
    decoding: {codec: json}
transforms:
  timestamp:
    type: remap
    inputs: [test_input]
    source: '.timestamp = parse_timestamp!(string!(.timestamp), format: "%+")'
  split:
    type: route
    inputs: [timestamp]
    route:
      ssh: '.kind == "ssh"'
      http: '.kind == "http"'
"""
    config += original[original.index("  ssh_normalized:") :]
    config = config.replace("inputs: [ssh]", "inputs: [split.ssh]")
    config = config.replace("inputs: [nginx]", "inputs: [split.http]")
    config = config.replace("/var/lib/vector", "/tmp/vector")
    config = config.replace("/run/secrets/sources.json", "/config/secrets.json")
    config = config.replace("http://backend:8001", f"http://127.0.0.1:{server.server_port}")
    (Path(directory) / "vector.yaml").write_text(config)
    (Path(directory) / "secrets.json").write_text(
        json.dumps(
            {
                "ssh": "ssh-placeholder",
                "http": "http-placeholder",
            }
        )
    )
    (Path(directory) / "secrets.json").chmod(0o600)
    timestamp = "2026-11-03T00:00:00Z"
    payload = {
        "timestamp": timestamp,
        "remote_addr": "2001:db8::1",
        "request_id": "production-smoke",
        "hostname": "synthetic",
        "request_method": "PROPFIND",
        "path": "/" + "x" * 3000 + "?secret=NEVER_SEND",
        "status": 404,
        "dst_port": 80,
        "duration_seconds": 0.1,
        "user_agent": "x" * 1000,
        "Authorization": "NEVER_SEND",
        "Cookie": "NEVER_SEND",
    }
    records = [
        {
            "kind": "ssh",
            "timestamp": timestamp,
            "__CURSOR": "stable-cursor",
            "message": (
                "Accepted publickey for admin from 203.0.113.42 port 54321 ssh2: RAW_FINGERPRINT"
            ),
        },
        {"kind": "ssh", "timestamp": timestamp, "message": "Unsupported SSH line"},
        {"kind": "http", "timestamp": timestamp, "message": json.dumps(payload)},
        {
            "kind": "http",
            "timestamp": timestamp,
            "message": json.dumps(
                {
                    **payload,
                    "path": "/" + "😀" * 1000,
                    "request_id": "unicode-path",
                }
            ),
        },
        {"kind": "http", "timestamp": timestamp, "message": "malformed-json"},
    ]
    subprocess.run(
        [
            "docker",
            "run",
            "--rm",
            "-i",
            "--network",
            "host",
            "--user",
            "1000:1000",
            "--read-only",
            "--tmpfs",
            "/tmp:rw,noexec,nosuid,size=768m",
            "--cap-drop",
            "ALL",
            "--security-opt",
            "no-new-privileges:true",
            "-v",
            f"{directory}:/config:ro",
            "timberio/vector:0.61.0-debian@sha256:f6c23b5a7e16fb2838d33619ef7acf4bad2289a7cf22bc90efc2371f520c4ea2",
            "--config",
            "/config/vector.yaml",
        ],
        input="\n".join(json.dumps(record) for record in records) + "\n",
        text=True,
        capture_output=True,
        check=True,
        timeout=45,
    )
    server.shutdown()
assert len(received) == 3, len(received)
ssh = next(event for event in received if event["source"] == "ssh")
http = next(event for event in received if event["source_reference"] == "production-smoke")
unicode_http = next(event for event in received if event["source_reference"] == "unicode-path")
assert ssh["payload"]["outcome"] == "success"
assert ssh["source_reference"] == hashlib.sha256(b"stable-cursor").hexdigest()
assert "RAW_FINGERPRINT" not in json.dumps(received) and "NEVER_SEND" not in json.dumps(received)
assert len(http["payload"]["path"]) == 2048 and http["payload"]["path_truncated"]
assert len(http["payload"]["user_agent"]) == 512
assert http["payload"]["request_method"] == "PROPFIND"
assert len(unicode_http["payload"]["path"].encode()) <= 2048
assert unicode_http["payload"]["path_truncated"]
print(
    "Production Vector: normalization, cursor, file secrets, redaction, "
    "bounded fields and disk delivery passed"
)
