import pytest
from fastapi.testclient import TestClient
from helpers import event

from attackscope.normalization.journal import parse_journal


@pytest.mark.parametrize(
    ("message", "outcome", "ip"),
    [
        (
            "Accepted publickey for alice from 2001:db8::10 port 4321 ssh2: SHA256:ignored",
            "success",
            "2001:db8::10",
        ),
        (
            "Failed password for invalid user root from 192.0.2.1 port 1234 ssh2",
            "invalid_user",
            "192.0.2.1",
        ),
        ("Failed password for alice from 192.0.2.1 port 1234 ssh2", "failure", "192.0.2.1"),
        ("Invalid user admin from 192.0.2.1 port 1234", "invalid_user", "192.0.2.1"),
        ("Disconnected from user alice 192.0.2.1 port 1234", "disconnect", "192.0.2.1"),
        (
            "Received disconnect from 2001:db8::1 port 1234:11: disconnected",
            "disconnect",
            "2001:db8::1",
        ),
    ],
)
def test_ssh_formats(message: str, outcome: str, ip: str) -> None:
    result = parse_journal("ssh", "2026-11-03T00:00:00Z", message)
    assert result["outcome"] == outcome
    assert result["src_ip"] == ip
    assert "message" not in result


def test_firewall_nullable_verdict_and_ipv6() -> None:
    result = parse_journal(
        "firewall",
        "2026-11-03T00:00:00Z",
        "kernel: IN=eth0 OUT= SRC=2001:db8::1 DST=2001:db8::2 PROTO=TCP SPT=1234 DPT=443",
    )
    assert result["dst_port"] == 443
    assert result["protocol"] == "tcp"
    assert "action" not in result
    assert parse_journal("firewall", None, "AS_DROP: SRC=192.0.2.1 PROTO=ICMP")["action"] == "drop"


@pytest.mark.parametrize("message", ["unsupported message", "x" * 8193])
def test_unsupported_rejected(message: str) -> None:
    with pytest.raises(ValueError):
        parse_journal("ssh", None, message)


def test_journal_ingestion_drops_original(client: TestClient, runtime: object) -> None:
    client.headers["Authorization"] = f"Bearer {runtime.test_tokens['ssh']}"  # type: ignore[attr-defined]
    item = event("ssh")
    item["payload"] = {
        "timestamp": item["payload"]["timestamp"],
        "journal_message": (
            "Failed password for root from 192.0.2.1 port 1234 ssh2 SECRET_NOT_STORED"
        ),
    }
    assert client.post("/api/v1/ingest/events", json=[item]).json()["accepted"] == 1
    from sqlalchemy import select

    from attackscope.storage.schema import events

    with runtime.store.engine.connect() as connection:  # type: ignore[attr-defined]
        row = str(connection.execute(select(events)).mappings().first())
    assert "SECRET_NOT_STORED" not in row
    assert "journal_message" not in row
