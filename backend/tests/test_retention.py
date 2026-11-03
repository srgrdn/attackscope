from datetime import timedelta

from fastapi.testclient import TestClient
from helpers import NOW, event
from sqlalchemy import func, select

from attackscope.api.history import historical_statistics
from attackscope.api.queries import EventsQuery
from attackscope.api.runtime import Runtime
from attackscope.classification.engine import process_pending
from attackscope.storage.retention import cleanup
from attackscope.storage.schema import delivery_keys, event_rollups, events


def test_retention_keeps_rollups_and_delivery_keys(client: TestClient, runtime: Runtime) -> None:
    assert (
        client.post(
            "/api/v1/ingest/events", json=[event(reference="old", timestamp="2026-10-20T12:30:00Z")]
        ).status_code
        == 200
    )
    process_pending(runtime.store, runtime.settings)
    runtime.store.clock = lambda: NOW + timedelta(days=25)
    first = cleanup(runtime.store, runtime.settings)
    assert first["events"] == 1
    assert cleanup(runtime.store, runtime.settings)["events"] == 0
    with runtime.store.engine.connect() as connection:
        assert connection.scalar(select(func.count()).select_from(events)) == 0
        assert connection.scalar(select(func.sum(event_rollups.c.event_count))) == 1
        assert connection.execute(select(delivery_keys.c.event_id)).scalar() is None
        assert connection.scalar(select(func.count()).select_from(delivery_keys)) == 1
    query = EventsQuery.model_validate(
        {"from": "2026-10-20T12:00:00Z", "to": "2026-10-20T13:00:00Z"}
    )
    history = historical_statistics(runtime.store, query, 365, 5)
    assert history["total_events"] == 1
    assert history["unique_ips"] == 1
    runtime.store.clock = lambda: NOW + timedelta(days=400)
    cleanup(runtime.store, runtime.settings)
    with runtime.store.engine.connect() as connection:
        assert connection.scalar(select(func.count()).select_from(event_rollups)) == 0


def test_historical_partial_hours_are_explicit(client: TestClient, runtime: Runtime) -> None:
    assert (
        client.post(
            "/api/v1/ingest/events", json=[event(timestamp="2026-11-02T23:30:00Z")]
        ).status_code
        == 200
    )
    query = EventsQuery.model_validate(
        {"from": "2026-11-02T23:15:00Z", "to": "2026-11-03T00:00:00Z"}
    )
    result = historical_statistics(runtime.store, query, 365, 5)
    assert result["total_events"] == 0
    assert result["coverage"]["partial_hours_excluded"]
