"""Create private, consistent SQLite backups without replacing any existing file."""

import argparse
import os
import sqlite3
from contextlib import closing
from pathlib import Path

from attackscope.core.config import Settings


def create_backup(source_path: Path, output: Path) -> None:
    if not output.is_absolute() or source_path.resolve() == output.resolve():
        raise ValueError("Use a separate absolute backup path")
    output.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    descriptor = os.open(output, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
    os.close(descriptor)
    try:
        with closing(
            sqlite3.connect(source_path.as_uri() + "?mode=ro", uri=True, timeout=10)
        ) as source:
            destination = sqlite3.connect(output, timeout=10)
            try:
                source.backup(destination)
                destination.execute("PRAGMA journal_mode=DELETE")
                if destination.execute("PRAGMA integrity_check").fetchone() != ("ok",):
                    raise ValueError("Backup integrity check failed")
                if destination.execute("PRAGMA foreign_key_check").fetchone() is not None:
                    raise ValueError("Backup foreign key check failed")
            finally:
                destination.close()
    except BaseException:
        output.unlink(missing_ok=True)
        raise


def main() -> None:
    parser = argparse.ArgumentParser(description="Create and verify a private SQLite backup")
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    try:
        create_backup(Settings().database_path, args.output)
        print("Backup created and integrity verified")
    except (OSError, ValueError, sqlite3.Error) as error:
        parser.exit(1, f"Backup failed ({type(error).__name__}); no existing file replaced\n")


if __name__ == "__main__":
    main()
