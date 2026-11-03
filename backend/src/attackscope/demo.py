import argparse
import json
import os
import re
import time
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from attackscope.cli import provision_source
from attackscope.core.config import Settings
from attackscope.core.time import utc_now
from attackscope.storage.database import create_database
from attackscope.storage.migrations import BACKEND_ROOT, schema_is_current
from attackscope.storage.store import Store


def write_manifest(path: Path, data: dict[str, Any]) -> None:
    # Manifest contains no tokens. Replace atomically to allow rerunning an interrupted seed.
    temporary = path.with_suffix(".tmp")
    with temporary.open("w") as file:
        json.dump(data, file)
        file.flush()
        os.fsync(file.fileno())
    temporary.replace(path)


def send_batch(request: Request) -> dict[str, Any]:
    for attempt in range(5):
        try:
            with urlopen(request, timeout=10) as response:
                result: dict[str, Any] = json.load(response)
                return result
        except HTTPError as error:
            code = error.code
            error.close()
            if code not in (429, 503) or attempt == 4:
                raise
        except (URLError, TimeoutError):
            if attempt == 4:
                raise
        time.sleep(min(2, 0.25 * 2**attempt))
    raise RuntimeError("Unreachable retry state")


def send_demo(settings: Settings, run_name: str, scenario: str = "basic") -> dict[str, Any]:
    if not re.fullmatch(r"[A-Za-z0-9_-]{1,40}", run_name):
        raise ValueError("Invalid run name")
    directory = settings.database_path.parent / "demo" / run_name
    directory.mkdir(parents=True, exist_ok=True, mode=0o700)
    manifest_path = directory / "manifest.json"
    engine = create_database(settings.database_path)
    try:
        with engine.connect() as connection:
            if not schema_is_current(connection):
                raise ValueError("Migrations required")
        store = Store(engine)
        if manifest_path.exists():
            manifest = json.loads(manifest_path.read_text())
        else:
            manifest = {
                "host_id": store.create_host(f"demo-{run_name}"),
                "base_time": utc_now().replace(microsecond=0).isoformat(),
            }
            write_manifest(manifest_path, manifest)
        base = datetime.fromisoformat(manifest["base_time"])
        fixture_name = "investigation.json" if scenario == "investigation" else "events.json"
        fixtures = json.loads((BACKEND_ROOT / "fixtures" / fixture_name).read_text())
        total = {"accepted": 0, "duplicates": 0}
        for kind in ("ssh", "http", "firewall"):
            token_path = directory / f"{kind}.token"
            if not token_path.exists():
                provision_source(store, manifest["host_id"], kind, token_path)
            token = token_path.read_text().strip()
            identity = store.authenticate(f"Bearer {token}")
            if identity.host_id != manifest["host_id"] or identity.kind != kind:
                raise ValueError("Demo source mismatch")
            batch = []
            for item in fixtures:
                if item["source"] != kind:
                    continue
                payload = {
                    **item["payload"],
                    "timestamp": (base + timedelta(seconds=item["offset_seconds"])).isoformat(),
                }
                batch.append(
                    {
                        "transport_version": 1,
                        "source": kind,
                        "source_reference": item["source_reference"],
                        "payload": payload,
                    }
                )
            for offset in range(0, len(batch), 500):
                request = Request(
                    f"http://127.0.0.1:{settings.ingest_port}/api/v1/ingest/events",
                    data=json.dumps(batch[offset : offset + 500]).encode(),
                    headers={
                        "Content-Type": "application/json",
                        "Authorization": f"Bearer {token}",
                    },
                    method="POST",
                )
                result = send_batch(request)
                for key in total:
                    total[key] += result[key]
        query = {
            "from": (base - timedelta(minutes=10)).isoformat(),
            "to": (base + timedelta(seconds=1)).isoformat(),
            "host_id": manifest["host_id"],
        }
        return {
            "events_path": "/api/v1/events?" + urlencode(query),
            **total,
            "host_id": manifest["host_id"],
            "query": query,
        }
    finally:
        engine.dispose()


def main() -> None:
    parser = argparse.ArgumentParser(description="Send sanitized demo fixtures to local ingestion")
    parser.add_argument("--run-name", default="default")
    parser.add_argument("--scenario", choices=["basic", "investigation"], default="basic")
    args = parser.parse_args()
    try:
        print(json.dumps(send_demo(Settings(), args.run_name, args.scenario)))
    except Exception as error:
        parser.exit(
            1, f"Demo failed ({type(error).__name__}); check backend readiness and demo age\n"
        )


if __name__ == "__main__":
    main()
