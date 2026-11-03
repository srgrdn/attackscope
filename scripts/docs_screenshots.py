#!/usr/bin/env python3
"""Generate wiki screenshots on an isolated tmpfs-backed local demo stack."""

import argparse
import json
import os
import shutil
import socket
import subprocess
import tempfile
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PROJECT = "attackscope-docs"
COMPOSE = [
    "docker",
    "compose",
    "--env-file",
    "deploy/docs.env.example",
    "-p",
    PROJECT,
    "-f",
    "compose.yaml",
    "-f",
    "deploy/compose.docs.yaml",
]


def run(args, **kwargs):
    return subprocess.run(args, cwd=ROOT, check=True, timeout=1200, **kwargs)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--keep-running", action="store_true")
    args = parser.parse_args()
    # Ignore user Compose overrides so this tool cannot select the production project.
    for name in list(os.environ):
        if name.startswith(("COMPOSE_", "ATTACKSCOPE_")):
            os.environ.pop(name)
    existing = run(
        [
            "docker",
            "ps",
            "-a",
            "--filter",
            "label=com.docker.compose.project=" + PROJECT,
            "--format",
            "{{.ID}}",
        ],
        capture_output=True,
        text=True,
    ).stdout.strip()
    if existing:
        parser.error("The documentation project already exists; stop that project explicitly first")
    with socket.socket() as port:
        port.bind(("127.0.0.1", 18182))
    run(COMPOSE + ["config", "--quiet"])
    started = False
    success = False
    try:
        started = True
        run(COMPOSE + ["up", "--build", "--wait", "--wait-timeout", "120"])
        seeded = run(
            COMPOSE + ["exec", "-T", "backend", "python", "-"],
            text=True,
            input=(ROOT / "scripts/seed_documentation.py").read_text(),
            capture_output=True,
        )
        metadata = json.loads(seeded.stdout)
        for _ in range(120):
            pending = run(
                COMPOSE
                + [
                    "exec",
                    "-T",
                    "backend",
                    "python",
                    "-c",
                    "import sqlite3; c=sqlite3.connect('/data/attackscope.db'); "
                    "print(c.execute('SELECT count(*) FROM pending_events').fetchone()[0])",
                ],
                text=True,
                capture_output=True,
            )
            if int(pending.stdout) == 0:
                break
            time.sleep(1)
        else:
            raise RuntimeError("Documentation classification queue did not drain")
        run(
            [
                "docker",
                "build",
                "-f",
                "deploy/browser.Dockerfile",
                "-t",
                "attackscope-docs-browser:local",
                ".",
            ]
        )
        with tempfile.TemporaryDirectory(prefix="attackscope-wiki-") as temporary:
            output = Path(temporary)
            metadata["source_commit"] = run(
                ["git", "rev-parse", "HEAD"], text=True, capture_output=True
            ).stdout.strip()
            metadata["source_tree_dirty"] = bool(
                run(["git", "status", "--porcelain"], text=True, capture_output=True).stdout.strip()
            )
            (output / "seed.json").write_text(json.dumps(metadata))
            try:
                captured = run(
                    [
                        "docker",
                        "run",
                        "--rm",
                        "--init",
                        "--network",
                        "host",
                        "--shm-size",
                        "256m",
                        "--user",
                        f"{os.getuid()}:{os.getgid()}",
                        "--cap-drop",
                        "ALL",
                        "--security-opt",
                        "no-new-privileges:true",
                        "-v",
                        str(ROOT / "scripts") + ":/scripts:ro",
                        "-v",
                        str(output) + ":/output",
                        "attackscope-docs-browser:local",
                        "/scripts/capture_documentation.py",
                    ],
                    capture_output=True,
                    text=True,
                )
            except subprocess.CalledProcessError as error:
                print(error.stdout)
                print(error.stderr.split("Aria snapshot:")[0])
                raise
            print(captured.stdout)
            destination = ROOT / "docs/images"
            destination.mkdir(parents=True, exist_ok=True)
            for path in output.iterdir():
                if path.suffix == ".png" or path.name == "manifest.json":
                    shutil.copyfile(path, destination / path.name)
        success = True
        print("Wiki screenshots generated from synthetic data only")
    finally:
        if started and not (success and args.keep_running):
            run(COMPOSE + ["down", "--timeout", "20"])


if __name__ == "__main__":
    main()
