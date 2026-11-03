import json
import sqlite3
import time
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path

from sqlalchemy import Connection, Engine, create_engine, event
from sqlalchemy.engine import URL
from sqlalchemy.pool import QueuePool

# SQLite documents WAL fixes in these releases and all newer releases.
MIN_SQLITE_VERSION = (3, 51, 3)
BACKPORTED_SQLITE_VERSIONS = {(3, 44, 6), (3, 50, 7)}


def check_sqlite_version() -> None:
    version = sqlite3.sqlite_version_info
    if version < MIN_SQLITE_VERSION and version not in BACKPORTED_SQLITE_VERSIONS:
        raise RuntimeError("SQLite runtime lacks the required WAL fix; update the runtime image")


def create_database(path: Path, busy_timeout_ms: int = 5000) -> Engine:
    check_sqlite_version()
    engine = create_engine(
        URL.create("sqlite+pysqlite", database=str(path)),
        connect_args={"check_same_thread": False, "timeout": busy_timeout_ms / 1000},
        poolclass=QueuePool,
        pool_size=4,
        max_overflow=0,
        pool_timeout=5,
        json_serializer=lambda value: json.dumps(
            value, ensure_ascii=False, allow_nan=False, separators=(",", ":")
        ),
    )

    @event.listens_for(engine, "connect")
    def configure_connection(connection: sqlite3.Connection, _: object) -> None:
        # Explicit SQLAlchemy BEGIN, as recommended for sqlite3 legacy transaction mode.
        connection.isolation_level = None
        cursor = connection.cursor()
        try:
            cursor.execute(f"PRAGMA busy_timeout={busy_timeout_ms:d}")
            cursor.execute("PRAGMA foreign_keys=ON")
            cursor.execute("PRAGMA synchronous=FULL")
            mode = cursor.execute("PRAGMA journal_mode=WAL").fetchone()
            if mode is None or mode[0].lower() != "wal":
                raise RuntimeError("SQLite WAL could not be enabled")
        finally:
            cursor.close()

    @event.listens_for(engine, "begin")
    def explicit_begin(connection: Connection) -> None:
        connection.exec_driver_sql(
            "BEGIN IMMEDIATE"
            if connection.get_execution_options().get("sqlite_begin_immediate")
            else "BEGIN"
        )

    return engine


@contextmanager
def statement_deadline(connection: Connection, seconds: float) -> Iterator[None]:
    driver = connection.connection.driver_connection
    assert isinstance(driver, sqlite3.Connection)
    deadline = time.monotonic() + seconds
    driver.set_progress_handler(lambda: int(time.monotonic() > deadline), 10000)
    try:
        yield
    finally:
        driver.set_progress_handler(None, 0)
