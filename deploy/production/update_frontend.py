#!/usr/bin/python3
"""Transaction helper for the approved single-VM frontend deployment only."""

from __future__ import annotations

import argparse
import hashlib
import http.client
import json
import os
import re
import shutil
import socket
import subprocess
import tempfile
import time
from pathlib import Path
from typing import Any

ROOT = Path("/srv/attackscope/production")
PROJECT = "attackscope-production"
FRONTEND = PROJECT + "-frontend-1"
PROTECTED = (PROJECT + "-backend-1", PROJECT + "-collector-1")
IMAGE = "attackscope-frontend:git-"


def run(*args: str, env: dict[str, str] | None = None) -> str:
    result = subprocess.run(
        args, cwd=ROOT / "release", env=env, capture_output=True, text=True, timeout=180
    )
    if result.returncode:
        # Compose output can contain operational details; do not echo environment or logs.
        raise RuntimeError("Command failed: " + " ".join(args[:3]))
    return result.stdout.strip()


def inspect(name: str) -> dict[str, Any]:
    return json.loads(run("docker", "inspect", name))[0]


def compose(*args: str, env: dict[str, str] | None = None) -> str:
    return run("docker", "compose", "--project-name", PROJECT, *args, env=env)


def atomic(path: Path, content: str) -> None:
    previous = path.stat() if path.exists() else None
    with tempfile.NamedTemporaryFile(mode="w", dir=path.parent, delete=False) as stream:
        temporary = Path(stream.name)
        stream.write(content)
        stream.flush()
        os.fsync(stream.fileno())
    if previous:
        os.chown(temporary, previous.st_uid, previous.st_gid)
        os.chmod(temporary, previous.st_mode & 0o777)
    os.replace(temporary, path)


def save(directory: Path, state: dict[str, Any]) -> None:
    atomic(directory / "state.json", json.dumps(state, indent=2) + "\n")


def protected() -> dict[str, str]:
    result = {}
    for name in PROTECTED:
        container = inspect(name)
        if not container["State"]["Running"]:
            raise RuntimeError("Protected component is unavailable")
        result[name] = container["Id"]
    return result


def ready(path: Path) -> None:
    connection = http.client.HTTPConnection("localhost", timeout=5)
    connection.sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    connection.sock.settimeout(5)
    try:
        connection.sock.connect(str(path))
        connection.request("GET", "/api/v1/health/ready", headers={"Host": "localhost"})
        response = connection.getresponse()
        if response.status != 200 or json.loads(response.read()).get("status") != "ready":
            raise RuntimeError("Frontend read API is not ready")
    finally:
        connection.close()


def healthy(name: str) -> None:
    deadline = time.monotonic() + 90
    while time.monotonic() < deadline:
        container = inspect(name)
        if container["State"].get("Health", {}).get("Status") == "healthy":
            return
        if not container["State"]["Running"]:
            break
        time.sleep(1)
    raise RuntimeError("Frontend health check failed")


def replace_image(content: str, image: str) -> str:
    lines = content.splitlines()
    matches = [i for i, line in enumerate(lines) if line.startswith("ATTACKSCOPE_FRONTEND_IMAGE=")]
    if len(matches) != 1:
        raise RuntimeError("Expected exactly one frontend image setting")
    lines[matches[0]] = "ATTACKSCOPE_FRONTEND_IMAGE=" + image
    return "\n".join(lines) + "\n"


def stage(args: argparse.Namespace, directory: Path) -> None:
    directory.mkdir(mode=0o700)
    owner = (ROOT / "run").stat()
    os.chown(directory, owner.st_uid, owner.st_gid)
    previous = inspect(FRONTEND)
    state = {
        "release": args.release,
        "commit": args.commit,
        "image": IMAGE + args.commit,
        "image_id": args.image_id,
        "previous_image_id": previous["Image"],
        "protected": protected(),
        "phase": "preparing",
        "candidate": "attackscope-candidate-" + args.release,
    }
    save(directory, state)
    env_file = ROOT / "release/.env"
    atomic(directory / "previous.env", env_file.read_text())
    lock = ROOT / "deploy.lock"
    lock.mkdir(mode=0o700)  # Atomic, fail closed if another transaction or recovery is pending.
    (lock / "owner").write_text(args.release)
    archive = ROOT / "incoming" / (args.release + ".tar")
    digest = hashlib.sha256()
    with archive.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    if digest.hexdigest() != args.checksum:
        raise RuntimeError("Transferred image checksum mismatch")
    if shutil.disk_usage(ROOT).free < 2 * 1024**3 + archive.stat().st_size * 3:
        raise RuntimeError("Insufficient disk space for deployment")
    run("docker", "load", "--input", str(archive))
    if inspect(state["image"])["Id"] != args.image_id:
        raise RuntimeError("Loaded image ID mismatch")
    socket_directory = directory / "run"
    socket_directory.mkdir(mode=0o700)
    os.chown(socket_directory, owner.st_uid, owner.st_gid)
    env = dict(
        os.environ,
        ATTACKSCOPE_FRONTEND_IMAGE=state["image"],
        ATTACKSCOPE_RUN_DIR=str(socket_directory),
    )
    compose(
        "run",
        "-d",
        "--no-deps",
        "--pull",
        "never",
        "--name",
        state["candidate"],
        "frontend",
        env=env,
    )
    healthy(state["candidate"])
    ready(socket_directory / "ui.sock")
    if protected() != state["protected"]:
        raise RuntimeError("Protected components changed")
    state["phase"] = "staged"
    save(directory, state)
    print("Candidate ready; live frontend unchanged")


def promote(directory: Path, state: dict[str, Any]) -> None:
    if state["phase"] != "staged":
        raise RuntimeError("Candidate is not staged")
    if inspect(FRONTEND)["Image"] != state["previous_image_id"]:
        raise RuntimeError("Live image changed outside this deployment")
    if protected() != state["protected"]:
        raise RuntimeError("Protected components changed")
    state["phase"] = "promoting"
    save(directory, state)
    atomic(
        ROOT / "release/.env",
        replace_image((directory / "previous.env").read_text(), state["image"]),
    )
    compose(
        "up",
        "-d",
        "--no-deps",
        "--no-build",
        "--pull",
        "never",
        "--wait",
        "--wait-timeout",
        "90",
        "frontend",
    )
    healthy(FRONTEND)
    ready(ROOT / "run/ui.sock")
    if inspect(FRONTEND)["Image"] != state["image_id"] or protected() != state["protected"]:
        raise RuntimeError("Deployment identity check failed")
    state["phase"] = "promoted"
    save(directory, state)
    print("Frontend promoted; backend and collector IDs unchanged")


def clean_candidate(state: dict[str, Any]) -> None:
    names = run("docker", "ps", "-a", "--format", "{{.Names}}").splitlines()
    if state["candidate"] in names:
        run("docker", "rm", "--force", state["candidate"])


def abort(directory: Path, state: dict[str, Any]) -> None:
    if state["phase"] in ("promoting", "promoted"):
        atomic(ROOT / "release/.env", (directory / "previous.env").read_text())
        compose(
            "up",
            "-d",
            "--no-deps",
            "--no-build",
            "--pull",
            "never",
            "--wait",
            "--wait-timeout",
            "90",
            "frontend",
        )
        healthy(FRONTEND)
        ready(ROOT / "run/ui.sock")
        if inspect(FRONTEND)["Image"] != state["previous_image_id"]:
            raise RuntimeError("Rollback image mismatch; operator recovery required")
    clean_candidate(state)
    if protected() != state["protected"]:
        raise RuntimeError("Protected components changed; inspect before releasing the lock")
    state["phase"] = "rolled_back" if state["phase"] in ("promoting", "promoted") else "aborted"
    save(directory, state)
    print("Transaction aborted; previous frontend retained or restored")


def finish(directory: Path, state: dict[str, Any]) -> None:
    if state["phase"] != "promoted" or protected() != state["protected"]:
        raise RuntimeError("Cannot finalize this transaction")
    ready(ROOT / "run/ui.sock")
    atomic(ROOT / "frontend-deployment.json", json.dumps(state, indent=2) + "\n")
    clean_candidate(state)
    state["phase"] = "complete"
    save(directory, state)
    print("Frontend deployment complete")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("phase", choices=("stage", "promote", "finish", "abort"))
    parser.add_argument("release")
    parser.add_argument("--commit", default="")
    parser.add_argument("--image-id", default="")
    parser.add_argument("--checksum", default="")
    args = parser.parse_args()
    if not re.fullmatch(r"[0-9a-f]{12}-[0-9]{14}-[0-9a-f]{4}", args.release):
        parser.error("Invalid release ID")
    if args.phase == "stage" and not (
        re.fullmatch(r"[0-9a-f]{40}", args.commit)
        and re.fullmatch(r"sha256:[0-9a-f]{64}", args.image_id)
        and re.fullmatch(r"[0-9a-f]{64}", args.checksum)
    ):
        parser.error("Invalid release metadata")
    if os.geteuid() != 0:
        parser.error("Remote operator helper requires root")
    os.umask(0o077)
    (ROOT / "updates").mkdir(mode=0o700, exist_ok=True)
    owner = (ROOT / "run").stat()
    os.chown(ROOT / "updates", owner.st_uid, owner.st_gid)
    directory = ROOT / "updates" / args.release
    if args.phase == "stage":
        stage(args, directory)
        return
    state = json.loads((directory / "state.json").read_text())
    lock = ROOT / "deploy.lock"
    if state["phase"] in ("complete", "rolled_back", "aborted"):
        # Recover a crash between the terminal checkpoint and lock cleanup.
        # A newer transaction may already own the lock: never release its lock.
        owner_file = lock / "owner"
        if owner_file.exists() and owner_file.read_text() == args.release:
            owner_file.unlink()
            lock.rmdir()
        print("Transaction is already terminal; no rollback performed")
        return
    if (lock / "owner").read_text() != args.release:
        raise RuntimeError("Deployment lock belongs to another transaction")
    {"promote": promote, "abort": abort, "finish": finish}[args.phase](directory, state)
    if args.phase in ("abort", "finish"):
        (lock / "owner").unlink()
        lock.rmdir()


if __name__ == "__main__":
    main()
