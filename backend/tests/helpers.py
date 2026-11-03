from datetime import UTC, datetime, timedelta
from typing import Any

NOW = datetime(2026, 11, 3, tzinfo=UTC)


def event(kind: str = "http", reference: str | None = "test:1", **overrides: Any) -> dict[str, Any]:
    payload: dict[str, Any] = {"timestamp": (NOW - timedelta(minutes=1)).isoformat()}
    if kind == "http":
        payload.update(remote_addr="2001:db8::10", request_method="GET", path="/", status=200)
    elif kind == "ssh":
        payload.update(src_ip="192.0.2.10", outcome="failure", dst_port=22)
    else:
        payload.update(src_ip="203.0.113.20", action="drop", protocol="tcp", dst_port=443)
    payload.update(overrides)
    return {
        "transport_version": 1,
        "source": kind,
        "source_reference": reference,
        "payload": payload,
    }
