from datetime import timedelta

from fastapi.testclient import TestClient
from helpers import NOW, event

from attackscope.api.apps import create_app
from attackscope.api.runtime import Runtime


def test_timeline_edges_filters_and_empty(client: TestClient, runtime: Runtime) -> None:
    lower = NOW - timedelta(hours=1)
    for index, timestamp in enumerate((lower, NOW - timedelta(seconds=1), NOW)):
        assert (
            client.post(
                "/api/v1/ingest/events",
                json=[event(reference=f"e:{index}", timestamp=timestamp.isoformat())],
            ).status_code
            == 200
        )
    with TestClient(create_app(runtime.store.engine, runtime=runtime)) as read:
        params = {"from": lower.isoformat(), "to": NOW.isoformat()}
        result = read.get("/api/v1/timeline", params=params)
        assert result.status_code == 200
        assert result.json()["total"] == 2
        assert result.json()["mode"] == "events"
        assert (
            read.get("/api/v1/timeline", params={**params, "ip": "192.0.2.1"}).json()["total"] == 0
        )
        assert (
            read.get("/api/v1/timeline", params={**params, "from": NOW.isoformat()}).status_code
            == 422
        )


def test_dense_timeline_exact_count(client: TestClient, runtime: Runtime) -> None:
    for batch in range(4):
        response = client.post(
            "/api/v1/ingest/events",
            json=[event(reference=f"dense:{batch}:{index}") for index in range(500)],
        )
        assert response.status_code == 200
    with TestClient(create_app(runtime.store.engine, runtime=runtime)) as read:
        result = read.get(
            "/api/v1/timeline",
            params={"from": (NOW - timedelta(hours=1)).isoformat(), "to": NOW.isoformat()},
        ).json()
        assert result["mode"] == "buckets"
        assert result["total"] == 2000
        assert len(result["buckets"]) == 1
        assert result["buckets"][0]["count"] == 2000
        assert result["items"] == []
