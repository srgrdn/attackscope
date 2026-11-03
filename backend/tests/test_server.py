import json
import os
import socket
import subprocess
import sys
import time
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path

import httpx2 as httpx
import pytest


@contextmanager
def free_port() -> Iterator[int]:
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        yield sock.getsockname()[1]


def environment(tmp_path: Path, read_port: int, ingest_port: int) -> dict[str, str]:
    return {
        **os.environ,
        "ATTACKSCOPE_DATABASE_PATH": str(tmp_path / "server.db"),
        "ATTACKSCOPE_BIND_HOST": "127.0.0.1",
        "ATTACKSCOPE_READ_PORT": str(read_port),
        "ATTACKSCOPE_INGEST_PORT": str(ingest_port),
    }


def wait_ready(process: subprocess.Popen[bytes], port: int) -> None:
    deadline = time.monotonic() + 10
    while time.monotonic() < deadline:
        if process.poll() is not None:
            pytest.fail(f"Server exited early: {process.returncode}")
        try:
            if httpx.get(f"http://127.0.0.1:{port}/health/ready", timeout=0.3).status_code == 200:
                return
        except httpx.TransportError:
            pass
        time.sleep(0.05)
    pytest.fail("Server did not become ready")


def test_dual_listener_and_sigterm(tmp_path: Path) -> None:
    with free_port() as read_port, free_port() as ingest_port:
        pass
    process = subprocess.Popen(
        [sys.executable, "-m", "attackscope"],
        env=environment(tmp_path, read_port, ingest_port),
    )
    try:
        wait_ready(process, read_port)
        wait_ready(process, ingest_port)
        assert httpx.get(f"http://127.0.0.1:{ingest_port}/openapi.json").status_code == 404
        process.terminate()
        assert process.wait(timeout=15) == 0
        for port in (read_port, ingest_port):
            with pytest.raises(httpx.TransportError):
                httpx.get(f"http://127.0.0.1:{port}/health/live", timeout=0.5)
    finally:
        if process.poll() is None:
            process.kill()
        process.wait(timeout=5)


def test_occupied_ingestion_port_prevents_partial_start(tmp_path: Path) -> None:
    with socket.socket() as occupied:
        occupied.bind(("127.0.0.1", 0))
        occupied.listen()
        ingest_port = occupied.getsockname()[1]
        with free_port() as read_port:
            pass
        result = subprocess.run(
            [sys.executable, "-m", "attackscope"],
            env=environment(tmp_path, read_port, ingest_port),
            timeout=10,
            check=False,
            capture_output=True,
        )
        assert result.returncode == 1
        assert str(tmp_path).encode() not in result.stderr
        with socket.socket() as probe:
            probe.bind(("127.0.0.1", read_port))


def test_real_http_demo_roundtrip_and_repeated_delivery(tmp_path: Path) -> None:
    with free_port() as read_port, free_port() as ingest_port:
        pass
    env = environment(tmp_path, read_port, ingest_port)
    process = subprocess.Popen([sys.executable, "-m", "attackscope"], env=env)
    try:
        wait_ready(process, read_port)
        wait_ready(process, ingest_port)
        results = []
        for _ in range(2):
            completed = subprocess.run(
                [sys.executable, "-m", "attackscope.demo"],
                env=env,
                check=True,
                capture_output=True,
                text=True,
                timeout=15,
            )
            results.append(json.loads(completed.stdout))
        assert results[0]["accepted"] == 8 and results[0]["duplicates"] == 0
        assert results[1]["accepted"] == 0 and results[1]["duplicates"] == 8
        response = httpx.get(
            f"http://127.0.0.1:{read_port}/api/v1/events", params=results[0]["query"]
        )
        assert response.status_code == 200, response.text
        assert len(response.json()["items"]) == 8
        assert {item["source"] for item in response.json()["items"]} == {"ssh", "http", "firewall"}
        assert "not-a-real-secret" not in response.text and "discard-this" not in response.text
    finally:
        process.terminate()
        process.wait(timeout=15)
