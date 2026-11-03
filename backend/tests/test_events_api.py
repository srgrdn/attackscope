from datetime import timedelta
from uuid import uuid4

from fastapi.testclient import TestClient
from helpers import NOW, event
from sqlalchemy import select

from attackscope.api.apps import create_app
from attackscope.api.runtime import Runtime
from attackscope.storage.schema import events


def parameters(**values):
    return {
        "from": (NOW - timedelta(hours=1)).isoformat(),
        "to": (NOW + timedelta(minutes=1)).isoformat(),
        **values,
    }


def test_filters_and_detail(client: TestClient, runtime: Runtime) -> None:
    client.post(
        "/api/v1/ingest/events",
        json=[
            event(reference="a", remote_addr="192.0.2.1", dst_port=443),
            event(reference="b", remote_addr="2001:db8::2", dst_port=80),
        ],
    )
    with TestClient(create_app(runtime.store.engine, runtime=runtime)) as reader:
        for values in (
            {"ip": "192.0.2.1"},
            {"port": 443},
            {"host_id": runtime.test_host_id, "port": 443},
            {"category": "http_request", "ip": "::ffff:192.0.2.1"},
        ):
            response = reader.get("/api/v1/events", params=parameters(**values))
            assert response.status_code == 200, response.text
            assert len(response.json()["items"]) == 1
        assert reader.get("/api/v1/events", params=parameters(source="ssh")).json()["items"] == []
        assert reader.get(f"/api/v1/events/{uuid4()}").status_code == 404
        assert reader.get("/api/v1/events/not-a-uuid").status_code == 422
        hosts = reader.get("/api/v1/hosts").json()
        assert hosts["items"][0]["id"] == runtime.test_host_id
        assert "token" not in str(hosts)


def test_half_open_range(client: TestClient, runtime: Runtime) -> None:
    client.post(
        "/api/v1/ingest/events",
        json=[
            event(reference=str(i), timestamp=(NOW + timedelta(seconds=i)).isoformat())
            for i in (-60, -30, 0)
        ],
    )
    with TestClient(create_app(runtime.store.engine, runtime=runtime)) as reader:
        result = reader.get(
            "/api/v1/events",
            params={"from": (NOW - timedelta(seconds=60)).isoformat(), "to": NOW.isoformat()},
        )
        assert result.status_code == 200, result.text
        assert len(result.json()["items"]) == 2


def test_cursor_ties_and_late_delivery_snapshot(client: TestClient, runtime: Runtime) -> None:
    client.post("/api/v1/ingest/events", json=[event(reference=str(i)) for i in range(7)])
    with TestClient(create_app(runtime.store.engine, runtime=runtime)) as reader:
        query = parameters(limit=2)
        first = reader.get("/api/v1/events", params=query).json()
        assert first["next_cursor"]
        client.post("/api/v1/ingest/events", json=[event(reference="late")])
        seen = [item["id"] for item in first["items"]]
        cursor = first["next_cursor"]
        while cursor:
            response = reader.get("/api/v1/events", params={**query, "cursor": cursor})
            assert response.status_code == 200, response.text
            page = response.json()
            seen.extend(item["id"] for item in page["items"])
            cursor = page["next_cursor"]
        assert len(seen) == len(set(seen)) == 7
        assert seen == sorted(seen, reverse=True)
        assert len(reader.get("/api/v1/events", params=parameters()).json()["items"]) == 8


def test_ascending_order_and_cursor_validation(client: TestClient, runtime: Runtime) -> None:
    client.post("/api/v1/ingest/events", json=[event(reference=str(i)) for i in range(3)])
    with TestClient(create_app(runtime.store.engine, runtime=runtime)) as reader:
        page = reader.get("/api/v1/events", params=parameters(limit=1, order="asc")).json()
        cursor = page["next_cursor"]
        assert (
            reader.get("/api/v1/events", params=parameters(cursor=cursor, order="desc")).status_code
            == 422
        )
        assert (
            reader.get("/api/v1/events", params=parameters(cursor="invalid@@")).status_code == 422
        )
        runtime.store.clock = lambda: NOW + timedelta(minutes=16)
        assert (
            reader.get("/api/v1/events", params=parameters(cursor=cursor, order="asc")).status_code
            == 410
        )


def test_invalid_filters_are_safe(client: TestClient, runtime: Runtime) -> None:
    with TestClient(create_app(runtime.store.engine, runtime=runtime)) as reader:
        for values in (
            {"ip": "1' OR 1=1 --"},
            {"limit": 501},
            {"sort": "timestamp; DROP TABLE events"},
            {"unknown": "parameter"},
            {"category": "invented"},
            {"port": 65536},
            {"from": "2026-11-01T00:00:00"},
            {"from": NOW.isoformat(), "to": NOW.isoformat()},
        ):
            response = reader.get("/api/v1/events", params=parameters(**values))
            assert response.status_code == 422, response.text
        assert reader.get(
            "/api/v1/events", params=parameters(**{"from": (NOW - timedelta(days=31)).isoformat()})
        ).status_code in (410, 422)
        assert (
            reader.get(
                "/api/v1/events",
                params=parameters(),
                headers={"Origin": "https://attacker.example"},
            ).status_code
            == 403
        )
    with runtime.store.engine.connect() as connection:
        assert connection.execute(select(events)).all() == []
