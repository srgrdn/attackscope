#!/usr/bin/env python3
"""Run tested frontend-only deployment over the existing SSH operator connection."""

from __future__ import annotations

import argparse
import contextlib
import fcntl
import hashlib
import os
import secrets
import shlex
import socket
import subprocess
import sys
import tempfile
import time
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
REMOTE = "/srv/attackscope/production"
BROWSER = "attackscope-deploy-browser:local"


def run(*args: str, capture: bool = False, **kwargs) -> str:
    result = subprocess.run(
        args,
        cwd=ROOT,
        check=True,
        text=True,
        stdout=subprocess.PIPE if capture else None,
        timeout=kwargs.pop("timeout", 1800),
        **kwargs,
    )
    return result.stdout.strip() if capture else ""


def clean(commit: str | None = None) -> str:
    if run("git", "status", "--porcelain", "--untracked-files=all", capture=True):
        raise RuntimeError("Working tree must be clean; commit reviewed changes first")
    current = run("git", "rev-parse", "HEAD", capture=True)
    if commit is not None and commit != current:
        raise RuntimeError("Git HEAD changed during the deployment")
    return current


def remote(ssh: list[str], phase: str, release: str, *args: str) -> None:
    command = shlex.join(["sudo", "-n", "python3", "-", phase, release, *args])
    run(
        *ssh,
        command,
        input=(ROOT / "deploy/production/update_frontend.py").read_text(),
        timeout=300,
    )


@contextlib.contextmanager
def tunnel(ssh: list[str], socket_path: str):
    with socket.socket() as reservation:
        reservation.bind(("127.0.0.1", 0))
        port = reservation.getsockname()[1]
    # ExitOnForwardFailure makes the small bind handoff race fail closed.
    command = ssh[:-1] + [
        "-N",
        "-o",
        "ExitOnForwardFailure=yes",
        "-L",
        f"127.0.0.1:{port}:{socket_path}",
        ssh[-1],
    ]
    process = subprocess.Popen(command, stdin=subprocess.DEVNULL)
    try:
        url = f"http://127.0.0.1:{port}"
        for _ in range(40):
            if process.poll() is not None:
                raise RuntimeError("Temporary SSH tunnel failed")
            try:
                with urllib.request.urlopen(url + "/api/v1/health/ready", timeout=2) as response:
                    if response.status == 200:
                        break
            except OSError:
                pass
            time.sleep(0.25)
        else:
            raise RuntimeError("Temporary tunnel readiness timed out")
        yield url
    finally:
        process.terminate()
        try:
            process.wait(timeout=10)
        except subprocess.TimeoutExpired:
            process.kill()
            process.wait()


def browser(url: str) -> None:
    run(
        "docker",
        "run",
        "--rm",
        "--init",
        "--network",
        "host",
        "--shm-size",
        "256m",
        "--cap-drop",
        "ALL",
        "--security-opt",
        "no-new-privileges:true",
        "-e",
        "ATTACKSCOPE_BROWSER_URL=" + url,
        "-v",
        str(ROOT / "tests") + ":/tests:ro",
        BROWSER,
        "/tests/timeline_navigation_smoke.py",
    )


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("target", choices=("production",))
    parser.add_argument("--component", choices=("frontend",), default="frontend")
    parser.add_argument("--abort", metavar="RELEASE", help="Recover an interrupted transaction")
    parser.add_argument("--host", required=True)
    parser.add_argument("--user", required=True)
    parser.add_argument("--port", type=int, default=22)
    parser.add_argument("--identity", type=Path, default=Path.home() / ".ssh/id_ed25519")
    args = parser.parse_args()
    ssh = [
        "ssh",
        "-a",
        "-o",
        "BatchMode=yes",
        "-o",
        "StrictHostKeyChecking=yes",
        "-o",
        "ConnectTimeout=10",
        "-o",
        "ServerAliveInterval=15",
        "-o",
        "ServerAliveCountMax=3",
        "-o",
        "IdentitiesOnly=yes",
        "-i",
        str(args.identity),
        "-p",
        str(args.port),
        f"{args.user}@{args.host}",
    ]
    with open(Path(tempfile.gettempdir()) / f"attackscope-deploy-{os.getuid()}.lock", "a") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        if args.abort:
            remote(ssh, "abort", args.abort)
            return
        commit = clean()
        run(
            sys.executable,
            "-m",
            "unittest",
            "discover",
            "-s",
            "tests",
            "-p",
            "test_frontend_deploy.py",
        )
        release = commit[:12] + "-" + datetime.now(timezone.utc).strftime("%Y%m%d%H%M%S")
        release += "-" + secrets.token_hex(2)
        image = "attackscope-frontend:git-" + commit
        print("Deploying frontend commit " + commit + "; transaction " + release, flush=True)
        test_image = "attackscope-frontend-test:git-" + commit
        run(
            "docker",
            "build",
            "-f",
            "deploy/frontend.Dockerfile",
            "--target",
            "test",
            "-t",
            test_image,
            ".",
        )
        run(
            "docker",
            "run",
            "--rm",
            "--network",
            "none",
            test_image,
            "sh",
            "-ec",
            "npm run lint && npm run format:check && npm run typecheck && npm test "
            "&& npm run build -- --outDir /tmp/dist",
        )
        run(
            "docker",
            "build",
            "-f",
            "deploy/frontend.Dockerfile",
            "--target",
            "runtime",
            "-t",
            image,
            ".",
        )
        run("docker", "build", "-f", "deploy/browser.Dockerfile", "-t", BROWSER, ".")
        clean(commit)
        image_id = run("docker", "image", "inspect", "--format", "{{.Id}}", image, capture=True)
        with tempfile.TemporaryDirectory(prefix="attackscope-deploy-") as temporary:
            archive = Path(temporary) / "frontend.tar"
            run("docker", "image", "save", "--output", str(archive), image)
            digest = hashlib.sha256()
            with archive.open("rb") as stream:
                for chunk in iter(lambda: stream.read(1024 * 1024), b""):
                    digest.update(chunk)
            incoming = REMOTE + "/incoming"
            upload = "umask 077; mkdir -p " + shlex.quote(incoming)
            upload += "; set -C; cat > " + shlex.quote(incoming + "/" + release + ".tar")
            with archive.open("rb") as stream:
                subprocess.run([*ssh, upload], stdin=stream, cwd=ROOT, check=True, timeout=300)
            try:
                remote(
                    ssh,
                    "stage",
                    release,
                    "--commit",
                    commit,
                    "--image-id",
                    image_id,
                    "--checksum",
                    digest.hexdigest(),
                )
                with tunnel(ssh, REMOTE + "/updates/" + release + "/run/ui.sock") as url:
                    browser(url)
                clean(commit)
                remote(ssh, "promote", release)
                with tunnel(ssh, REMOTE + "/run/ui.sock") as url:
                    browser(url)
                remote(ssh, "finish", release)
            except BaseException:
                print("Deployment interrupted; attempting rollback: " + release, flush=True)
                try:
                    remote(ssh, "abort", release)
                except Exception:
                    print(
                        "Recovery required: ./scripts/deploy production --abort " + release,
                        flush=True,
                    )
                raise
        print("Production frontend verified: " + commit, flush=True)


if __name__ == "__main__":
    try:
        main()
    except (RuntimeError, OSError, subprocess.SubprocessError) as error:
        raise SystemExit("Deploy failed: " + str(error)) from None
