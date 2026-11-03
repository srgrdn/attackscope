"""Verify a seeded private VM deployment through its Unix socket (stdlib only)."""

import argparse
import http.client
import json
import socket
import stat
import subprocess
from datetime import datetime, timedelta, timezone
from pathlib import Path
from urllib.parse import urlencode


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--socket", type=Path, required=True)
    parser.add_argument("--project", required=True)
    args = parser.parse_args()
    assert stat.S_ISSOCK(args.socket.stat().st_mode)
    assert stat.S_IMODE(args.socket.parent.stat().st_mode) == 0o700

    def request(path: str, expected: int = 200, host: str = "localhost") -> bytes:
        connection = http.client.HTTPConnection("localhost", timeout=20)
        connection.sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        connection.sock.settimeout(20)
        connection.sock.connect(str(args.socket))
        try:
            connection.request("GET", path, headers={"Host": host})
            response = connection.getresponse()
            body = response.read()
            assert response.status == expected, (path, response.status)
            return body
        finally:
            connection.close()

    assert b"AttackScope" in request("/")
    assert json.loads(request("/api/v1/health/ready"))["status"] == "ready"
    request("/", 421, "untrusted.example")
    request("/api/v1/ingest/events", 404)
    now = datetime.now(timezone.utc)
    query = urlencode({"from": (now - timedelta(days=1)).isoformat(), "to": now.isoformat()})
    overview = json.loads(request("/api/v1/overview?" + query))
    assert overview["total_events"] == 2086, overview["total_events"]
    timeline = json.loads(request("/api/v1/timeline?" + query))
    assert timeline["mode"] == "buckets"
    assert sum(item["count"] for item in timeline["buckets"]) == 2086
    assert {item["source"] for item in timeline["buckets"]} == {"ssh", "http", "firewall"}
    events = json.loads(request("/api/v1/events?" + query))
    assert len(events["items"]) == 100 and events["next_cursor"]
    assert json.loads(request("/api/v1/findings?" + query))["items"]
    ip = json.loads(request("/api/v1/ips/203.0.113.42?" + query))
    assert ip["total_events"] > 0 and ip["findings"]["items"]
    assert len(json.loads(request("/api/v1/events/export.json?" + query))) == 2086
    assert len(request("/api/v1/events/export.csv?" + query).splitlines()) == 2087

    def docker(*arguments: str) -> str:
        return subprocess.check_output(["docker", *arguments], text=True, timeout=30)

    ids = docker("ps", "-q", "--filter", "label=com.docker.compose.project=" + args.project).split()
    assert len(ids) == 2
    containers = json.loads(docker("inspect", *ids))
    for container in containers:
        config = container["HostConfig"]
        service = container["Config"]["Labels"]["com.docker.compose.service"]
        assert container["State"]["Health"]["Status"] == "healthy"
        assert not container["State"]["OOMKilled"]
        assert not config.get("PortBindings") and not config["Privileged"]
        assert config["ReadonlyRootfs"] and "ALL" in config["CapDrop"]
        assert "no-new-privileges:true" in config["SecurityOpt"]
        assert int(container["Config"]["User"].split(":")[0]) != 0
        assert config["Memory"] == (256 if service == "backend" else 64) * 1024**2
        assert config["NanoCpus"] == (400_000_000 if service == "backend" else 100_000_000)
        for network in container["NetworkSettings"]["Networks"]:
            assert json.loads(docker("network", "inspect", network))[0]["Internal"]
    print("VM smoke passed: private socket, API, timeline counts, findings, IP, exports, isolation and limits")


if __name__ == "__main__":
    main()
