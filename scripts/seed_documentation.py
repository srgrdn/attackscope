"""Seed only the explicitly isolated documentation container, never production."""

import json
import os
from datetime import datetime, timedelta, timezone
from urllib.request import Request

if os.environ.get("ATTACKSCOPE_DOCUMENTATION_MODE") != "1":
    raise SystemExit("Documentation mode is required; refusing to access the database")

from attackscope.core.config import Settings  # noqa: E402 - check the target before app imports
from attackscope.demo import BACKEND_ROOT, send_batch, send_demo  # noqa: E402

settings = Settings()
result = send_demo(settings, "wiki", "investigation")
directory = settings.database_path.parent / "demo/wiki"
manifest = json.loads((directory / "manifest.json").read_text())
base = datetime.fromisoformat(manifest["base_time"])
# Put the cloud sequence in a single completed classification window.
window = datetime.fromtimestamp(int(base.timestamp()) // 300 * 300 - 300 + 60, timezone.utc)
fixtures = json.loads((BACKEND_ROOT / "fixtures/documentation.json").read_text())
batch = [
    {
        "transport_version": 1,
        "source": "http",
        "source_reference": item["source_reference"],
        "payload": {
            **item["payload"],
            "timestamp": (window + timedelta(seconds=item["offset_seconds"])).isoformat(),
        },
    }
    for item in fixtures
]
token = (directory / "http.token").read_text().strip()
request = Request(
    f"http://127.0.0.1:{settings.ingest_port}/api/v1/ingest/events",
    data=json.dumps(batch).encode(),
    headers={"Content-Type": "application/json", "Authorization": "Bearer " + token},
    method="POST",
)
extra = send_batch(request)
print(
    json.dumps(
        {
            "host_id": result["host_id"],
            "base_time": manifest["base_time"],
            "cloud_time": window.isoformat(),
            "events": result["accepted"] + extra["accepted"],
            "synthetic": True,
        }
    )
)
