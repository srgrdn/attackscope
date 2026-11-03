#!/usr/bin/python3
"""Create an allowlisted, secret-free production archive from prebuilt images."""

import argparse
import hashlib
import json
import shutil
import subprocess
import tarfile
import tempfile
from pathlib import Path

FILES = (
    "compose.yaml",
    "deploy/compose.vm.yaml",
    "deploy/nginx-vm-listen.conf",
    "deploy/production/compose.yaml",
    "deploy/production/vector.yaml",
    "deploy/production/ops.py",
    "deploy/production/acceptance.py",
    "deploy/production/bootstrap-vm.sh",
    "deploy/production/activate-vm.sh",
    "deploy/production/nginx-logging.conf",
    "deploy/production/logrotate.conf",
    "deploy/production/attackscope-maintenance@.service",
    "deploy/production/attackscope-backup.timer",
    "deploy/production/attackscope-check.timer",
    "deploy/production/attackscope-restore-check.timer",
    "deploy/production/attackscope-logrotate.timer",
)


def checksum(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as file:
        for chunk in iter(lambda: file.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[2]
    if args.output.exists():
        parser.exit(1, "Output already exists\n")
    with tempfile.TemporaryDirectory(prefix="attackscope-package-") as temporary:
        directory = Path(temporary)
        images = []
        manifest = {}
        for kind in ("backend", "frontend"):
            image = "attackscope-" + kind + ":production-0.1-20261103"
            images.append(image)
            manifest[kind + "_image"] = subprocess.check_output(
                ["docker", "image", "inspect", "--format", "{{.Id}}", image], text=True
            ).strip()
        manifest["source_commit"] = subprocess.check_output(
            ["git", "rev-parse", "HEAD"], cwd=root, text=True
        ).strip()
        subprocess.run(
            ["docker", "image", "save", "--output", str(directory / "images.tar"), *images],
            check=True,
        )
        for name in FILES:
            target = directory / name
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(root / name, target)
        shutil.copyfile(root / "deploy/production/env.example", directory / ".env")
        (directory / ".env").chmod(0o600)
        (directory / "MANIFEST.json").write_text(json.dumps(manifest, indent=2) + "\n")
        checksums = "".join(
            checksum(path) + "  " + str(path.relative_to(directory)) + "\n"
            for path in sorted(directory.rglob("*"))
            if path.is_file()
        )
        (directory / "SHA256SUMS").write_text(checksums)
        with (
            args.output.open("xb") as output,
            tarfile.open(fileobj=output, mode="w:gz", compresslevel=1) as archive,
        ):
            for path in sorted(directory.iterdir()):
                archive.add(path, arcname=path.name)
    args.output.chmod(0o600)
    print(checksum(args.output) + "  " + str(args.output))


if __name__ == "__main__":
    main()
