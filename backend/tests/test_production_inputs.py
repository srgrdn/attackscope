from typing import Any

import pytest
from fastapi.testclient import TestClient
from helpers import event
from sqlalchemy import select

from attackscope.storage.schema import events


@pytest.mark.parametrize("method", ["PROPFIND", "BREW", "M-SEARCH", "get"])
def test_extension_http_methods_do_not_poison_batch(client: TestClient, method: str) -> None:
    first = event("http", "normal")
    second = event("http", "extension")
    second["payload"]["request_method"] = method
    response = client.post("/api/v1/ingest/events", json=[first, second])
    assert response.status_code == 200
    assert response.json()["accepted"] == 2


@pytest.mark.parametrize("method", ["GET\r\nInjected", "G ET", "X" * 33, ""])
def test_invalid_method_tokens_rejected(client: TestClient, method: str) -> None:
    item = event("http", "invalid")
    item["payload"]["request_method"] = method
    assert client.post("/api/v1/ingest/events", json=[item]).status_code == 422


def test_path_truncation_is_explicit_in_safe_projection(client: TestClient, runtime: Any) -> None:
    item = event("http", "truncated")
    item["payload"].update(path="/" + "x" * 2047, path_truncated=True)
    assert client.post("/api/v1/ingest/events", json=[item]).status_code == 200
    with runtime.store.engine.connect() as connection:
        saved = connection.execute(select(events)).mappings().one()
    assert saved["attributes"]["path_truncated"] is True
    assert saved["safe_original"]["path_truncated"] is True
