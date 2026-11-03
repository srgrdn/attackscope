from collections.abc import Iterator
from pathlib import Path
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from helpers import NOW
from sqlalchemy import Engine

from attackscope.api.apps import create_app
from attackscope.api.runtime import Runtime
from attackscope.core.config import Settings
from attackscope.storage.database import create_database
from attackscope.storage.migrations import upgrade_database
from attackscope.storage.store import Store


@pytest.fixture
def engine(tmp_path: Path) -> Iterator[Engine]:
    database = create_database(tmp_path / "test.db")
    upgrade_database(database)
    yield database
    database.dispose()


@pytest.fixture
def runtime(engine: Engine) -> Runtime:
    store = Store(engine, clock=lambda: NOW)
    result = Runtime(store, Settings(source_burst=100, source_requests_per_second=100))
    host_id = store.create_host("test-vm")
    result.test_host_id = host_id  # test-only handles, never part of API
    result.test_tokens = {}
    for index, kind in enumerate(("http", "ssh", "firewall")):
        source_id = str(uuid4())
        token = f"{source_id}." + chr(65 + index) * 43
        store.create_source(host_id, kind, source_id, token)
        result.test_tokens[kind] = token
    return result


@pytest.fixture
def client(runtime: Runtime) -> Iterator[TestClient]:
    with TestClient(create_app(runtime.store.engine, ingestion=True, runtime=runtime)) as result:
        result.headers["Authorization"] = f"Bearer {runtime.test_tokens['http']}"
        yield result
