from pathlib import Path

from fastapi.testclient import TestClient
from sqlalchemy import Engine

from attackscope.api.apps import create_app
from attackscope.storage.database import create_database


def test_health_and_readiness(engine: Engine) -> None:
    with TestClient(create_app(engine)) as client:
        assert client.get("/health/live").json() == {"status": "ok"}
        assert client.get("/health/ready").json() == {"status": "ready"}
        assert client.get("/openapi.json").status_code == 200


def test_schema_drift_is_unready_without_leaking_sql(engine: Engine) -> None:
    with engine.begin() as connection:
        connection.exec_driver_sql("UPDATE alembic_version SET version_num = 'unknown'")
    with TestClient(create_app(engine)) as client:
        response = client.get("/health/ready")
        assert response.status_code == 503
        assert response.json() == {"error": {"code": "not_ready"}}
        assert client.get("/health/live").status_code == 200


def test_ingestion_exposes_no_admin_or_unauthenticated_ingest(engine: Engine) -> None:
    app = create_app(engine, ingestion=True)
    with TestClient(app) as client:
        assert client.get("/health/ready").status_code == 200
        for path in ("/docs", "/openapi.json", "/api/v1/hosts", "/api/v1/events"):
            assert client.get(path).status_code == 404
        assert client.post("/api/v1/ingest/events", json=[]).status_code == 401


def test_unmigrated_database_is_unready(tmp_path: Path) -> None:
    database = create_database(tmp_path / "unmigrated.db")
    try:
        with TestClient(create_app(database)) as client:
            assert client.get("/health/ready").status_code == 503
    finally:
        database.dispose()
