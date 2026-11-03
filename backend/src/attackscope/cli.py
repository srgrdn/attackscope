import argparse
import json
import os
import secrets
from pathlib import Path
from typing import cast
from uuid import UUID, uuid4

from attackscope.core.config import Settings
from attackscope.normalization.events import SourceKind
from attackscope.storage.database import create_database
from attackscope.storage.migrations import schema_is_current
from attackscope.storage.store import Store


def provision_source(store: Store, host_id: str, kind: SourceKind, path: Path) -> str:
    if not path.is_absolute():
        raise ValueError("Token file path must be absolute")
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    source_id = str(uuid4())
    token = f"{source_id}.{secrets.token_urlsafe(32)}"
    descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
    try:
        with os.fdopen(descriptor, "w") as file:
            file.write(token + "\n")
            file.flush()
            os.fsync(file.fileno())
        store.create_source(host_id, kind, source_id, token)
    except BaseException:
        path.unlink(missing_ok=True)  # only the file exclusively created by this invocation
        raise
    return source_id


def main() -> None:
    parser = argparse.ArgumentParser(description="Local AttackScope source provisioning")
    subcommands = parser.add_subparsers(dest="command", required=True)
    host_parser = subcommands.add_parser("create-host")
    host_parser.add_argument("--name", required=True)
    source_parser = subcommands.add_parser("create-source")
    source_parser.add_argument("--host-id", type=UUID, required=True)
    source_parser.add_argument("--kind", choices=["ssh", "http", "firewall"], required=True)
    source_parser.add_argument("--token-file", type=Path, required=True)
    disable_parser = subcommands.add_parser("disable-source")
    disable_parser.add_argument("--source-id", type=UUID, required=True)
    args = parser.parse_args()
    settings = Settings()
    engine = create_database(settings.database_path, settings.sqlite_busy_timeout_ms)
    try:
        with engine.connect() as connection:
            if not schema_is_current(connection):
                raise ValueError("Run the backend migrations first")
        store = Store(engine, write_timeout=settings.write_wait_seconds)
        result: dict[str, object]
        if args.command == "create-host":
            result = {"host_id": store.create_host(args.name)}
        elif args.command == "create-source":
            source_id = provision_source(
                store, str(args.host_id), cast(SourceKind, args.kind), args.token_file
            )
            result = {
                "source_id": source_id,
                "host_id": str(args.host_id),
                "token_file": str(args.token_file),
            }
        else:
            store.disable_source(str(args.source_id))
            result = {"source_id": str(args.source_id), "enabled": False}
        print(json.dumps(result))
    except Exception as error:
        # Never echo credentials, SQL parameters, filesystem paths or validation input.
        parser.exit(
            1, f"Command failed ({type(error).__name__}); check arguments and database readiness\n"
        )
    finally:
        engine.dispose()


if __name__ == "__main__":
    main()
