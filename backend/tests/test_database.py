import sqlite3
from pathlib import Path

import pytest
from alembic import command
from sqlalchemy import Engine, inspect
from sqlalchemy.exc import IntegrityError

from attackscope.storage.database import check_sqlite_version, create_database
from attackscope.storage.migrations import migration_config, schema_is_current, upgrade_database


def test_connection_pragmas_and_foreign_keys(engine: Engine) -> None:
    # Check two independently opened connections, not only one pooled connection.
    with engine.connect() as first, engine.connect() as second:
        for connection in (first, second):
            assert connection.exec_driver_sql("PRAGMA journal_mode").scalar() == "wal"
            assert connection.exec_driver_sql("PRAGMA foreign_keys").scalar() == 1
            assert connection.exec_driver_sql("PRAGMA busy_timeout").scalar() == 5000
    with engine.begin() as connection:
        connection.exec_driver_sql("CREATE TABLE parent(id INTEGER PRIMARY KEY)")
        connection.exec_driver_sql(
            "CREATE TABLE child(id INTEGER PRIMARY KEY, parent_id INTEGER REFERENCES parent(id))"
        )
    with pytest.raises(IntegrityError), engine.begin() as connection:
        connection.exec_driver_sql("INSERT INTO child(id, parent_id) VALUES (1, 999)")


def test_transaction_rollback(engine: Engine) -> None:
    with engine.begin() as connection:
        connection.exec_driver_sql("CREATE TABLE example(value TEXT)")
    with pytest.raises(RuntimeError), engine.begin() as connection:
        connection.exec_driver_sql("INSERT INTO example VALUES ('test')")
        raise RuntimeError("rollback")
    with engine.connect() as connection:
        assert connection.exec_driver_sql("SELECT count(*) FROM example").scalar() == 0


def test_migrations_empty_idempotent_and_persistent(tmp_path: Path) -> None:
    path = tmp_path / "persistent.db"
    first = create_database(path)
    upgrade_database(first)
    upgrade_database(first)
    with first.connect() as connection:
        assert schema_is_current(connection)
        assert set(inspect(connection).get_table_names()) == {
            "alembic_version",
            "hosts",
            "sources",
            "events",
            "delivery_keys",
            "event_rollups",
            "pending_events",
            "findings",
        }
    first.dispose()
    second = create_database(path)
    with second.connect() as connection:
        assert schema_is_current(connection)
    second.dispose()


def test_migration_roundtrip_preserves_unrelated_data(engine: Engine) -> None:
    with engine.begin() as connection:
        connection.exec_driver_sql("CREATE TABLE operator_data(value TEXT)")
        connection.exec_driver_sql("INSERT INTO operator_data VALUES ('preserved')")
        config = migration_config()
        config.attributes["connection"] = connection
        command.downgrade(config, "base")
        assert not schema_is_current(connection)
        command.upgrade(config, "head")
        assert schema_is_current(connection)
        assert connection.exec_driver_sql("SELECT value FROM operator_data").scalar() == "preserved"


@pytest.mark.parametrize("version", [(3, 51, 2), (3, 40, 1)])
def test_unsafe_sqlite_runtime_is_rejected(
    monkeypatch: pytest.MonkeyPatch, version: tuple[int, ...]
) -> None:
    monkeypatch.setattr(sqlite3, "sqlite_version_info", version)
    with pytest.raises(RuntimeError, match="WAL fix"):
        check_sqlite_version()


@pytest.mark.parametrize("version", [(3, 51, 3), (3, 53, 4), (3, 44, 6), (3, 50, 7)])
def test_fixed_sqlite_runtime_is_accepted(
    monkeypatch: pytest.MonkeyPatch, version: tuple[int, ...]
) -> None:
    monkeypatch.setattr(sqlite3, "sqlite_version_info", version)
    check_sqlite_version()


def test_migration_metadata_and_indexes_match(engine: Engine) -> None:
    config = migration_config()
    with engine.begin() as connection:
        config.attributes["connection"] = connection
        command.check(config)
        indexes = {item["name"] for item in inspect(connection).get_indexes("events")}
        assert {
            "ix_events_time_id",
            "ix_events_host_id_time_id",
            "ix_events_src_ip_time_id",
            "ix_events_category_time_id",
        } <= indexes
