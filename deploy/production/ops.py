#!/usr/bin/python3
"""Root-operated maintenance for the approved single-VM deployment; no shell eval."""

from __future__ import annotations

import argparse
import fcntl
import http.client
import json
import os
import shutil
import socket
import sqlite3
import subprocess
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path("/srv/attackscope/production")
BACKUPS = ROOT / "backups"
BACKEND = "attackscope-production-backend-1"
FRONTEND = "attackscope-production-frontend-1"
COLLECTOR = "attackscope-production-collector-1"
RESERVE = 2 * 1024**3
BUDGET = 2 * 1024**3


def docker(*arguments: str, timeout: int = 120) -> str:
    result = subprocess.run(["docker", *arguments], capture_output=True, text=True, timeout=timeout)
    if result.returncode:
        raise RuntimeError("Docker operation failed; inspect the affected service privately")
    return result.stdout


def inspect(name: str) -> dict[str, Any]:
    return json.loads(docker("inspect", name))[0]


def snapshots() -> list[Path]:
    return sorted(BACKUPS.glob("scheduled-*.db"), key=lambda path: path.name, reverse=True)


def verify_snapshot(path: Path) -> int:
    connection = sqlite3.connect(path.as_uri() + "?mode=ro", uri=True)
    try:
        if connection.execute("PRAGMA integrity_check").fetchone() != ("ok",):
            raise RuntimeError("Backup integrity check failed")
        if connection.execute("PRAGMA foreign_key_check").fetchone() is not None:
            raise RuntimeError("Backup foreign key check failed")
        return int(connection.execute("SELECT count(*) FROM events").fetchone()[0])
    finally:
        connection.close()


def backup() -> None:
    BACKUPS.mkdir(mode=0o700, exist_ok=True)
    os.chmod(BACKUPS, 0o700)
    mounted = next(m for m in inspect(BACKEND)["Mounts"] if m["Destination"] == "/data")
    size = (Path(mounted["Source"]) / "attackscope.db").stat().st_size
    if shutil.disk_usage(ROOT).free < RESERVE + size * 3:
        raise RuntimeError("Insufficient disk space for safe backup")
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    name = "scheduled-" + stamp + ".db"
    destination = BACKUPS / name
    if destination.exists():
        raise RuntimeError("Backup name already exists")
    staged = "/data/backups/" + name
    docker("exec", BACKEND, "python", "-m", "attackscope.backup", "--output", staged, timeout=300)
    partial = BACKUPS / (name + ".partial")
    docker("cp", BACKEND + ":" + staged, str(partial), timeout=300)
    os.chmod(partial, 0o600)
    os.chown(partial, 0, 0)
    verify_snapshot(partial)
    credentials = destination.with_suffix(".sources.json")
    with credentials.open("x") as file:
        os.chmod(credentials, 0o600)
        json.dump(json.loads((ROOT / "secrets/sources.json").read_text()), file)
        file.flush()
        os.fsync(file.fileno())
    metadata = destination.with_suffix(".metadata.json")
    with metadata.open("x") as file:
        os.chmod(metadata, 0o600)
        json.dump(
            {
                "schema": 1,
                "created_at": stamp,
                "backend_image": inspect(BACKEND)["Image"],
                "frontend_image": inspect(FRONTEND)["Image"],
                "collector_image": inspect(COLLECTOR)["Image"],
            },
            file,
        )
        file.flush()
        os.fsync(file.fileno())
    with partial.open("rb") as file:
        os.fsync(file.fileno())
    partial.rename(destination)
    descriptor = os.open(BACKUPS, os.O_DIRECTORY)
    try:
        os.fsync(descriptor)
    finally:
        os.close(descriptor)
    docker(
        "exec",
        BACKEND,
        "python",
        "-c",
        "import pathlib,sys; pathlib.Path(sys.argv[1]).unlink()",
        staged,
    )
    # Only this helper's generated snapshots are eligible for retention.
    used = 0
    for index, path in enumerate(snapshots()):
        used += path.stat().st_size
        if index > 0 and (index >= 7 or used > BUDGET):
            path.unlink()
            for suffix in (".sources.json", ".metadata.json"):
                path.with_suffix(suffix).unlink(missing_ok=True)
    print("Backup verified; up to 7 snapshots, 2 GiB budget, newest always retained")


def restore_check() -> None:
    available = snapshots()
    if not available:
        raise RuntimeError("No scheduled backup available")
    expected = verify_snapshot(available[0])
    credentials = available[0].with_suffix(".sources.json")
    if not credentials.is_file():
        raise RuntimeError("Selected backup does not include source credentials")
    with tempfile.TemporaryDirectory(prefix="restore-check-", dir=ROOT) as temporary:
        directory = Path(temporary)
        image = inspect(BACKEND)["Image"]
        source = directory / "snapshot.db"
        shutil.copyfile(available[0], source)
        os.chown(source, 10001, 10001)
        os.chmod(source, 0o400)
        source_credentials = directory / "sources.json"
        shutil.copyfile(credentials, source_credentials)
        os.chown(source_credentials, 10001, 10001)
        os.chmod(source_credentials, 0o400)
        restored = directory / "restored"
        restored.mkdir(mode=0o700)
        os.chown(restored, 10001, 10001)
        code = """import shutil,sys,json
from pathlib import Path
from sqlalchemy import text
from attackscope.storage.database import create_database
from attackscope.storage.migrations import upgrade_database
from attackscope.storage.store import Store
shutil.copyfile('/input/snapshot.db', '/restore/restored.db')
engine = create_database(Path('/restore/restored.db'))
upgrade_database(engine)
with engine.connect() as connection:
    assert connection.exec_driver_sql('PRAGMA integrity_check').scalar_one() == 'ok'
    assert not connection.exec_driver_sql('PRAGMA foreign_key_check').fetchall()
    assert connection.execute(text('SELECT count(*) FROM events')).scalar_one() == int(sys.argv[1])
store=Store(engine)
identities=[]
for kind,token in json.load(open('/input/sources.json')).items():
    identity=store.authenticate('Bearer '+token)
    assert identity.kind==kind
    identities.append(identity.host_id)
assert len(set(identities))==1
engine.dispose()
print('Isolated restore: migrations, integrity, event count and source credentials verified')
"""
        result = docker(
            "run",
            "--rm",
            "--pull=never",
            "--network",
            "none",
            "--read-only",
            "--tmpfs",
            "/tmp:rw,noexec,nosuid,size=16m",
            "--cap-drop",
            "ALL",
            "--security-opt",
            "no-new-privileges:true",
            "--memory",
            "128m",
            "--cpus",
            "0.25",
            "--pids-limit",
            "64",
            "-v",
            str(source) + ":/input/snapshot.db:ro",
            "-v",
            str(source_credentials) + ":/input/sources.json:ro",
            "-v",
            str(restored) + ":/restore",
            image,
            "python",
            "-c",
            code,
            str(expected),
            timeout=300,
        )
        print(result.strip())


def check() -> None:
    for name in (BACKEND, FRONTEND, COLLECTOR):
        state = inspect(name)["State"]
        if (
            not state["Running"]
            or state["OOMKilled"]
            or state.get("Paused")
            or state.get("Restarting")
        ):
            raise RuntimeError("Application container is unavailable")
        if state.get("Health", {}).get("Status", "healthy") != "healthy":
            raise RuntimeError("Application container readiness failed")
    connection = http.client.HTTPConnection("localhost", timeout=10)
    connection.sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    connection.sock.settimeout(10)
    connection.sock.connect(str(ROOT / "run/ui.sock"))
    try:
        connection.request("GET", "/api/v1/health/ready", headers={"Host": "localhost"})
        response = connection.getresponse()
        if response.status != 200 or json.loads(response.read()).get("status") != "ready":
            raise RuntimeError("Read API readiness failed")
    finally:
        connection.close()
    if shutil.disk_usage(ROOT).free < RESERVE:
        raise RuntimeError("Disk reserve below 2 GiB")
    available = snapshots()
    now = datetime.now(timezone.utc).timestamp()
    if not available or now - available[0].stat().st_mtime > 26 * 3600:
        raise RuntimeError("Daily backup is missing or older than 26 hours")
    for suffix in (".sources.json", ".metadata.json"):
        if not available[0].with_suffix(suffix).is_file():
            raise RuntimeError("Latest backup is missing source credentials or image metadata")
    # Diagnostics stay private; log bodies are never copied into monitoring output.
    logs = subprocess.run(
        ["docker", "logs", "--since", "5m", "--tail", "200", COLLECTOR],
        capture_output=True,
        text=True,
        timeout=20,
    )
    if logs.returncode or "ERROR" in logs.stdout + logs.stderr:
        raise RuntimeError("Collector reported errors in the last five minutes")
    print("Containers, API, collector error log, disk reserve and daily backup checked")


def rotate() -> None:
    subprocess.run(
        [
            "/usr/sbin/logrotate",
            "--state",
            str(ROOT / "logrotate.status"),
            "/etc/attackscope/logrotate.conf",
        ],
        check=True,
        timeout=120,
        capture_output=True,
        text=True,
    )
    print("Dedicated HTTP log rotation checked")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("command", choices=("backup", "restore-check", "check", "rotate"))
    args = parser.parse_args()
    if os.geteuid() != 0:
        parser.exit(1, "Run this operator helper as root\n")
    try:
        with open("/run/attackscope-maintenance.lock", "a") as lock:
            fcntl.flock(lock, fcntl.LOCK_EX)
            {"backup": backup, "restore-check": restore_check, "check": check, "rotate": rotate}[
                args.command
            ]()
    except Exception as error:
        detail = str(error) if isinstance(error, RuntimeError) else type(error).__name__
        parser.exit(1, "Maintenance failed: " + detail + "\n")


if __name__ == "__main__":
    main()
