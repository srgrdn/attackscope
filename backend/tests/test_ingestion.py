import json
from concurrent.futures import ThreadPoolExecutor
from typing import Any
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from helpers import NOW, event
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError, OperationalError

from attackscope.api.apps import create_app
from attackscope.api.runtime import Runtime
from attackscope.core.time import detail_cutoff, from_us, to_us
from attackscope.normalization.events import Normalized, batch_adapter, normalize
from attackscope.storage.schema import delivery_keys, event_rollups, events, pending_events


def count(runtime: Runtime, table=events) -> int:
    with runtime.store.engine.connect() as connection:
        return connection.execute(select(func.count()).select_from(table)).scalar_one()


@pytest.mark.parametrize("kind", ["http", "ssh", "firewall"])
def test_ingest_and_read_roundtrip(runtime: Runtime, client: TestClient, kind: str) -> None:
    response = client.post(
        "/api/v1/ingest/events",
        json=[event(kind)],
        headers={"Authorization": f"Bearer {runtime.test_tokens[kind]}"},
    )
    assert response.status_code == 200, response.text
    assert response.json() == {"accepted": 1, "duplicates": 0, "schema_version": 1}
    with runtime.store.engine.connect() as connection:
        row = connection.execute(select(events)).mappings().one()
    assert row["host_id"] == runtime.test_host_id
    assert row["classification"] is None
    with TestClient(create_app(runtime.store.engine, runtime=runtime)) as reader:
        detail = reader.get(f"/api/v1/events/{row['id']}")
        assert detail.status_code == 200
        assert detail.json()["source"] == kind
        assert detail.json()["timestamp"].endswith("Z")
        assert "source_id" not in detail.json()


@pytest.mark.parametrize(
    "authorization",
    [None, "Bearer invalid", "Basic dGVzdA==", "Bearer " + "0" * 36 + "." + "A" * 43],
)
def test_unauthenticated_rejected(runtime: Runtime, authorization: str | None) -> None:
    with TestClient(create_app(runtime.store.engine, ingestion=True, runtime=runtime)) as caller:
        response = caller.post(
            "/api/v1/ingest/events",
            json=[event()],
            headers={"Authorization": authorization} if authorization else {},
        )
    assert response.status_code == 401
    assert response.headers["www-authenticate"] == "Bearer"
    assert count(runtime) == 0


def test_wrong_secret_and_duplicate_authorization(client: TestClient, runtime: Runtime) -> None:
    wrong = runtime.test_tokens["http"][:-1] + "Z"
    assert (
        client.post(
            "/api/v1/ingest/events", json=[event()], headers={"Authorization": f"Bearer {wrong}"}
        ).status_code
        == 401
    )
    assert (
        client.post(
            "/api/v1/ingest/events",
            json=[event()],
            headers=[("Authorization", f"Bearer {wrong}"), ("Authorization", f"Bearer {wrong}")],
        ).status_code
        == 401
    )


def test_host_and_source_spoofing(client: TestClient, runtime: Runtime) -> None:
    forged = event()
    forged["host_id"] = str(uuid4())
    assert client.post("/api/v1/ingest/events", json=[forged]).status_code == 403
    assert client.post("/api/v1/ingest/events", json=[event("ssh")]).status_code == 403
    assert count(runtime) == 0


def test_revoked_source(client: TestClient, runtime: Runtime) -> None:
    runtime.store.disable_source(runtime.test_tokens["http"].split(".")[0])
    assert client.post("/api/v1/ingest/events", json=[event()]).status_code == 401


@pytest.mark.parametrize(
    "payload",
    [
        {"status": 99},
        {"status": True},
        {"remote_addr": "not-an-ip"},
        {"remote_addr": "fe80::1%eth0"},
        {"dst_port": 65536},
        {"dst_port": True},
        {"timestamp": "2026-11-03T00:00:00"},
        {"timestamp": 1793664000},
        {"path": "x"},
        {"duration_ms": -1},
        {"path": "/" + "x" * 2048},
    ],
)
def test_invalid_batch_is_atomic(
    client: TestClient, runtime: Runtime, payload: dict[str, Any]
) -> None:
    response = client.post(
        "/api/v1/ingest/events",
        json=[event(reference="valid"), event(reference="invalid", **payload)],
    )
    assert response.status_code == 422, response.text
    assert count(runtime) == count(runtime, delivery_keys) == count(runtime, event_rollups) == 0


@pytest.mark.parametrize(
    "body",
    [
        "{",
        "[]",
        "null",
        "{}",
        '[{"source":"unknown"}]',
        '[{"transport_version":2,"source":"http","payload":{}}]',
    ],
)
def test_malformed_json_and_versions(client: TestClient, body: str) -> None:
    response = client.post(
        "/api/v1/ingest/events", content=body, headers={"Content-Type": "application/json"}
    )
    assert response.status_code == 422
    assert "input" not in response.json()["error"]


def test_redaction_and_bounded_fields(client: TestClient, runtime: Runtime) -> None:
    request = event(
        path="/.env?api_key=secret-value#secret-fragment",
        Authorization="secret-value",
        Cookie="secret-value",
        headers={"Authorization": "secret-value"},
        user_agent="<script>example</script>\r\n" + "Ж" * 400,
    )
    request["payload"]["attributes"] = {"password": "secret-value"}
    response = client.post("/api/v1/ingest/events", json=[request])
    assert response.status_code == 200
    with runtime.store.engine.connect() as connection:
        row = connection.execute(select(events)).mappings().one()
    saved = json.dumps(dict(row))
    assert "secret-value" not in saved and "secret-fragment" not in saved
    assert row["attributes"]["path"] == "/.env"
    assert row["severity"] == "info" and row["classification"] is None
    assert len(row["attributes"]["user_agent"].encode()) <= 512
    assert "\r" not in row["attributes"]["user_agent"]
    assert row["attributes"]["sanitized_fields"] == ["user_agent"]
    assert row["safe_original"]["path"] == "/.env"


def test_deduplication_and_first_payload_wins(client: TestClient, runtime: Runtime) -> None:
    assert client.post("/api/v1/ingest/events", json=[event(), event()]).json()["duplicates"] == 1
    assert (
        client.post("/api/v1/ingest/events", json=[event(path="/different")]).json()["duplicates"]
        == 1
    )
    assert count(runtime) == count(runtime, delivery_keys) == count(runtime, pending_events) == 1
    with runtime.store.engine.connect() as connection:
        assert connection.execute(select(func.sum(event_rollups.c.event_count))).scalar() == 1
        assert connection.execute(select(events.c.http_path)).scalar() == "/"


def test_no_reference_is_not_deduplicated(client: TestClient, runtime: Runtime) -> None:
    assert (
        client.post(
            "/api/v1/ingest/events", json=[event(reference=None), event(reference=None)]
        ).json()["accepted"]
        == 2
    )
    assert count(runtime) == 2 and count(runtime, delivery_keys) == 0


def test_reference_is_scoped_to_source(client: TestClient, runtime: Runtime) -> None:
    client.post("/api/v1/ingest/events", json=[event()])
    response = client.post(
        "/api/v1/ingest/events",
        json=[event("ssh")],
        headers={"Authorization": f"Bearer {runtime.test_tokens['ssh']}"},
    )
    assert response.json()["accepted"] == 1
    assert count(runtime) == 2


def test_concurrent_duplicate_delivery(runtime: Runtime) -> None:
    identity = runtime.store.authenticate(f"Bearer {runtime.test_tokens['http']}")
    envelope = batch_adapter.validate_python([event()])[0]
    normalized = normalize(envelope, identity.host_id, identity.kind, to_us(NOW), 30)
    with ThreadPoolExecutor(max_workers=8) as executor:
        results = list(
            executor.map(lambda _: runtime.store.persist(identity, [normalized], 30), range(8))
        )
    assert sum(result["accepted"] for result in results) == 1
    assert sum(result["duplicates"] for result in results) == 7
    assert count(runtime) == 1


def test_database_failure_rolls_back_all_side_effects(runtime: Runtime) -> None:
    identity = runtime.store.authenticate(f"Bearer {runtime.test_tokens['http']}")
    first = normalize(
        batch_adapter.validate_python([event()])[0], identity.host_id, identity.kind, to_us(NOW), 30
    )
    second = Normalized({**first.values, "attributes": {"oversized": "x" * 9000}}, "test:2")
    with pytest.raises(IntegrityError):
        runtime.store.persist(identity, [first, second], 30)
    for table in (events, delivery_keys, pending_events, event_rollups):
        assert count(runtime, table) == 0


def test_writer_backpressure_and_recovery(client: TestClient, runtime: Runtime) -> None:
    runtime.store.writer.acquire()
    try:
        response = client.post("/api/v1/ingest/events", json=[event()])
    finally:
        runtime.store.writer.release()
    assert response.status_code == 503
    assert response.headers["Retry-After"] == "1"
    assert client.post("/api/v1/ingest/events", json=[event()]).status_code == 200


def test_time_boundaries_and_ipv4_mapped_ipv6(client: TestClient, runtime: Runtime) -> None:
    cutoff = detail_cutoff(to_us(NOW), 30)
    assert (
        client.post(
            "/api/v1/ingest/events", json=[event(timestamp=from_us(cutoff - 1))]
        ).status_code
        == 422
    )
    assert (
        client.post(
            "/api/v1/ingest/events", json=[event(timestamp=from_us(to_us(NOW) + 300_000_001))]
        ).status_code
        == 422
    )
    assert (
        client.post(
            "/api/v1/ingest/events",
            json=[event(timestamp=from_us(cutoff), remote_addr="::ffff:192.0.2.50")],
        ).status_code
        == 200
    )
    with runtime.store.engine.connect() as connection:
        assert connection.execute(select(events.c.src_ip)).scalar() == "192.0.2.50"


def test_storage_errors_do_not_expose_parameters(
    client: TestClient, runtime: Runtime, monkeypatch: pytest.MonkeyPatch
) -> None:
    def fail(*args, **kwargs):
        raise OperationalError("secret SQL", {"token": "do-not-echo"}, Exception("private path"))

    monkeypatch.setattr(runtime.store, "persist", fail)
    response = client.post("/api/v1/ingest/events", json=[event()])
    assert response.status_code == 503
    assert "do-not-echo" not in response.text and "secret SQL" not in response.text
    assert (
        response.json()["error"]["request_id"]
        == response.headers["x-request-id"].split(",")[0].strip()
    )


def test_unexpected_errors_do_not_reach_server_tracebacks(
    client: TestClient,
    runtime: Runtime,
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    def fail(*args, **kwargs):
        raise RuntimeError("SECRET_AUTH_DO_NOT_LOG")

    monkeypatch.setattr(runtime.store, "persist", fail)
    response = client.post("/api/v1/ingest/events", json=[event()])
    assert response.status_code == 500
    assert "SECRET_AUTH_DO_NOT_LOG" not in response.text + caplog.text
    assert "request_failed" in caplog.text


@pytest.mark.parametrize("timestamp", ["1793664000", "2026-11-03 00:00:00Z", "2026-11-03"])
def test_timestamp_requires_rfc3339(client: TestClient, timestamp: str) -> None:
    assert (
        client.post("/api/v1/ingest/events", json=[event(timestamp=timestamp)]).status_code == 422
    )


def test_hour_rollups_match_observations_across_offsets(
    client: TestClient, runtime: Runtime
) -> None:
    batch = [
        event(
            reference="offset",
            timestamp="2026-11-03T07:59:59.123456+08:00",
            remote_addr="192.0.2.1",
            dst_port=443,
        ),
        event(
            reference="utc",
            timestamp="2026-11-02T23:59:59.123456Z",
            remote_addr="192.0.2.1",
            dst_port=443,
        ),
        event(reference="next", timestamp=NOW.isoformat(), remote_addr="192.0.2.1"),
    ]
    assert client.post("/api/v1/ingest/events", json=batch).json()["accepted"] == 3
    with runtime.store.engine.connect() as connection:
        rows = (
            connection.execute(select(event_rollups).order_by(event_rollups.c.bucket))
            .mappings()
            .all()
        )
    assert [row["event_count"] for row in rows] == [2, 1]
    assert [row["dst_port_key"] for row in rows] == [443, -1]
    assert rows[0]["first_seen"] == rows[0]["last_seen"]
