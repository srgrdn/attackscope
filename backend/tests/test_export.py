import csv
import io
import json

import pytest
from fastapi.testclient import TestClient
from helpers import event

from attackscope.api.apps import create_app
from attackscope.api.export import csv_cell
from attackscope.api.runtime import Runtime
from attackscope.classification.engine import process_pending


@pytest.mark.parametrize("value", ["=1+1", "+cmd", "-2", "@SUM(A1)", "  =cmd", "\tcmd", "\rtest"])
def test_formula_injection(value: str) -> None:
    assert csv_cell(value).startswith("'")


def test_overview_and_filtered_export(client: TestClient, runtime: Runtime) -> None:
    assert (
        client.post(
            "/api/v1/ingest/events",
            json=[
                event(reference="one", path="/.env?secret=removed"),
                event(reference="two", remote_addr="192.0.2.1", status=404),
            ],
        ).status_code
        == 200
    )
    process_pending(runtime.store, runtime.settings)
    with TestClient(create_app(runtime.store.engine, runtime=runtime)) as read:
        params = {"from": "2026-11-02T23:00:00Z", "to": "2026-11-03T00:00:00Z"}
        overview = read.get("/api/v1/overview", params=params).json()
        assert overview["http_requests"] == 2
        assert overview["suspicious_http_requests"] == 1
        assert overview["suspicious_sources"] == 1
        for kind in ("csv", "json"):
            response = read.get(
                f"/api/v1/events/export.{kind}", params={**params, "ip": "2001:db8::10"}
            )
            assert response.status_code == 200
            assert "attachment" in response.headers["content-disposition"]
            assert "removed" not in response.text
            items = (
                json.loads(response.text)
                if kind == "json"
                else list(csv.DictReader(io.StringIO(response.text)))
            )
            assert len(items) == 1
            assert items[0]["src_ip"] == "2001:db8::10"


def test_export_limit_does_not_return_partial_download(
    client: TestClient, runtime: Runtime, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr("attackscope.api.export.MAX_EXPORT_EVENTS", 1)
    assert (
        client.post(
            "/api/v1/ingest/events", json=[event(reference="a"), event(reference="b")]
        ).status_code
        == 200
    )
    with TestClient(create_app(runtime.store.engine, runtime=runtime)) as read:
        result = read.get(
            "/api/v1/events/export.json",
            params={"from": "2026-11-02T23:00:00Z", "to": "2026-11-03T00:00:00Z"},
        )
        assert result.status_code == 413
        assert "content-disposition" not in result.headers
        assert result.json()["error"]["code"] == "export_limit"
