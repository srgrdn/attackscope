"""Reject private runtime artifacts in the tracked public source distribution."""

import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def main():
    paths = subprocess.check_output(["git", "ls-files", "-z"], cwd=ROOT, text=True).split("\0")
    errors = []
    count = 0
    for name in filter(None, paths):
        path = Path(name)
        count += 1
        private = (
            any(
                part in {".publication", "secrets", "backups", "node_modules"}
                for part in path.parts
            )
            or path.name in {".env", "sources.json", "id_rsa", "id_ed25519"}
            or (
                "env" in path.name.split(".")
                and path.name.startswith(".env")
                and not path.name.endswith(".example")
            )
            or path.suffix
            in {
                ".token",
                ".pem",
                ".key",
                ".p12",
                ".pfx",
                ".db",
                ".sqlite",
                ".sqlite3",
                ".tar",
                ".tgz",
                ".log",
                ".logs",
            }
            or any(marker in path.name for marker in (".db-", ".sqlite-", ".sqlite3-"))
            or name.endswith(".tar.gz")
        )
        if private or (ROOT / path).is_symlink():
            errors.append("Unexpected private artifact or symlink: " + name)
    if not count:
        errors.append("No tracked files: stage the intended publication first")
    if errors:
        raise SystemExit("\n".join(errors))
    print(f"Publication file policy: {count} tracked files passed")


if __name__ == "__main__":
    main()
