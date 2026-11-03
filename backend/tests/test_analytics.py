from fastapi.testclient import TestClient
from helpers import event

from attackscope.api.apps import create_app
from attackscope.api.runtime import Runtime


def test_ip_explorer_ipv6_empty_and_distributions(client: TestClient, runtime: Runtime) -> None:
    assert (
        client.post(
            "/api/v1/ingest/events",
            json=[
                event(reference="a", path="/one", status=404),
                event(reference="b", path="/two", status=200),
            ],
        ).status_code
        == 200
    )
    with TestClient(create_app(runtime.store.engine, runtime=runtime)) as read:
        params = {"from": "2026-11-02T23:00:00Z", "to": "2026-11-03T00:00:00Z"}
        from attackscope.api.analytics import ip_explorer
        from attackscope.api.queries import EventsQuery

        ip_explorer(
            runtime.store, EventsQuery.model_validate({**params, "ip": "2001:db8::10"}), 30, 5
        )
        response = read.get("/api/v1/ips/2001:db8::10", params=params)
        assert response.status_code == 200
        data = response.json()
        assert data["total_events"] == 2
        assert data["http_requests"] == 2
        assert data["suspicious_events"] == 0
        assert data["enrichment"]["status"] == "unavailable"
        assert data["enrichment"]["country"] is None
        assert data["hosts"]["items"][0]["name"] == "test-vm"
        assert data["http_statuses"]["items"] == [
            {"value": 200, "count": 1},
            {"value": 404, "count": 1},
        ]
        assert read.get("/api/v1/ips/192.0.2.1", params=params).json()["total_events"] == 0
        assert read.get("/api/v1/ips/invalid", params=params).status_code == 422
