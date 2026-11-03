"""Force backend IP reassignment and verify UI recovery without restarting Nginx."""

import http.client
import json
import os
import socket
import subprocess
import tempfile
import time
from pathlib import Path
from uuid import uuid4

root = Path(__file__).resolve().parents[1]
network = "attackscope-dns-" + uuid4().hex[:10]
containers = []


def docker(*arguments: str) -> str:
    return subprocess.check_output(["docker", *arguments], text=True, timeout=90).strip()


def inspect(container: str) -> dict:
    return json.loads(docker("inspect", container))[0]


with tempfile.TemporaryDirectory(prefix="attackscope-dns-") as directory:
    os.chmod(directory, 0o700)
    docker("network", "create", "--internal", network)
    try:

        def run(*arguments: str) -> str:
            container = docker(
                "run",
                "-d",
                "--rm",
                "--pull=never",
                "--network",
                network,
                "--read-only",
                "--cap-drop",
                "ALL",
                "--security-opt",
                "no-new-privileges:true",
                "--pids-limit",
                "128",
                "--tmpfs",
                "/tmp:rw,noexec,nosuid,size=16m",
                *arguments,
            )
            containers.append(container)
            return container

        def backend() -> str:
            return run(
                "--network-alias",
                "backend",
                "--memory",
                "128m",
                "--tmpfs",
                "/data:rw,noexec,nosuid,size=16m,uid=10001,gid=10001",
                "-e",
                "ATTACKSCOPE_BIND_HOST=0.0.0.0",
                "attackscope-backend:production-0.1-20261103",
            )

        first = backend()
        frontend = run(
            "--memory",
            "64m",
            "--user",
            f"{os.getuid()}:{os.getgid()}",
            "-v",
            directory + ":/run/attackscope",
            "-v",
            str(root / "deploy/nginx-vm-listen.conf") + ":/etc/nginx/attackscope-listen.conf:ro",
            "attackscope-frontend:production-0.1-20261103",
        )
        start = inspect(frontend)["State"]["StartedAt"]

        def ready() -> bool:
            connection = http.client.HTTPConnection("localhost", timeout=3)
            connection.sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
            connection.sock.settimeout(3)
            try:
                connection.sock.connect(directory + "/ui.sock")
                connection.request("GET", "/api/v1/health/ready", headers={"Host": "localhost"})
                response = connection.getresponse()
                return response.status == 200 and json.loads(response.read())["status"] == "ready"
            except (OSError, ValueError):
                return False
            finally:
                connection.close()

        def wait() -> None:
            deadline = time.monotonic() + 45
            while time.monotonic() < deadline:
                if ready():
                    return
                time.sleep(1)
            raise AssertionError("UI did not reach a ready backend")

        wait()
        old_ip = inspect(first)["NetworkSettings"]["Networks"][network]["IPAddress"]
        # Start its replacement before releasing the original endpoint: Docker
        # must allocate another IP, without a fixed subnet or an address holder.
        second = backend()
        assert inspect(second)["NetworkSettings"]["Networks"][network]["IPAddress"] != old_ip
        docker("stop", "--time", "10", first)
        containers.remove(first)
        wait()
        assert inspect(frontend)["State"]["StartedAt"] == start
        print(
            "DNS recovery passed: backend received a different IP; "
            "UI recovered without frontend restart"
        )
    except Exception:
        for container in containers:
            subprocess.run(["docker", "logs", "--tail", "6", container], timeout=10)
        raise
    finally:
        for container in reversed(containers):
            subprocess.run(
                ["docker", "stop", "--time", "10", container], capture_output=True, timeout=30
            )
        subprocess.run(["docker", "network", "rm", network], capture_output=True, timeout=30)
