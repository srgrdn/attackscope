import hashlib
import hmac
import re
import threading
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import datetime
from typing import Any
from uuid import UUID, uuid4

from sqlalchemy import Connection, Engine, func, select, update
from sqlalchemy.dialects.sqlite import insert

from attackscope.core.errors import ServiceError
from attackscope.core.time import DAY_US, HOUR_US, to_us, utc_now
from attackscope.normalization.events import Normalized, SourceKind, clean_text
from attackscope.storage.schema import (
    delivery_keys,
    event_rollups,
    events,
    hosts,
    pending_events,
    sources,
)


@dataclass(frozen=True)
class Identity:
    id: str
    host_id: str
    kind: str


def token_digest(token: str) -> str:
    return hashlib.sha256(token.encode("ascii")).hexdigest()


class Store:
    def __init__(
        self, engine: Engine, clock: Callable[[], datetime] = utc_now, write_timeout: float = 0.25
    ) -> None:
        self.engine = engine
        self.clock = clock
        self.write_timeout = write_timeout
        self.writer = threading.Lock()

    @contextmanager
    def write(self) -> Iterator[Connection]:
        if not self.writer.acquire(timeout=self.write_timeout):
            raise ServiceError(503, "writer_busy", "Storage is busy; retry later")
        try:
            with (
                self.engine.connect().execution_options(sqlite_begin_immediate=True) as connection,
                connection.begin(),
            ):
                yield connection
        finally:
            self.writer.release()

    def create_host(self, name: str) -> str:
        name = clean_text(name, 128)
        if not name:
            raise ValueError("A host name is required")
        host_id = str(uuid4())
        with self.write() as connection:
            connection.execute(
                hosts.insert().values(
                    id=host_id, name=name, created_at=to_us(self.clock()), disabled=False
                )
            )
        return host_id

    def create_source(self, host_id: str, kind: SourceKind, source_id: str, token: str) -> None:
        with self.write() as connection:
            host = connection.execute(
                select(hosts.c.id).where(hosts.c.id == host_id, hosts.c.disabled.is_(False))
            ).first()
            if host is None:
                raise ValueError("Host does not exist or is disabled")
            connection.execute(
                sources.insert().values(
                    id=source_id,
                    host_id=host_id,
                    kind=kind,
                    token_digest=token_digest(token),
                    enabled=True,
                    created_at=to_us(self.clock()),
                )
            )

    def authenticate(self, authorization: str) -> Identity:
        error = ServiceError(401, "unauthorized", "Valid source credentials required")
        if not re.fullmatch(r"Bearer [0-9a-f-]{36}\.[A-Za-z0-9_-]{43}", authorization):
            raise error
        token = authorization.removeprefix("Bearer ")
        source_id, _ = token.split(".", 1)
        try:
            source_id = str(UUID(source_id))
        except ValueError:
            raise error from None
        with self.engine.connect() as connection:
            row = (
                connection.execute(
                    select(sources.c.id, sources.c.host_id, sources.c.kind, sources.c.token_digest)
                    .join(hosts)
                    .where(
                        sources.c.id == source_id,
                        sources.c.enabled.is_(True),
                        hosts.c.disabled.is_(False),
                    )
                )
                .mappings()
                .first()
            )
        actual = token_digest(token)
        expected = row["token_digest"] if row else "0" * 64
        matches = hmac.compare_digest(actual, expected)
        if row is None or not matches:
            raise error
        return Identity(row["id"], row["host_id"], row["kind"])

    def persist(
        self, identity: Identity, batch: list[Normalized], dedup_days: int
    ) -> dict[str, int]:
        with self.write() as connection:
            active = connection.execute(
                select(sources.c.id)
                .join(hosts)
                .where(
                    sources.c.id == identity.id,
                    sources.c.host_id == identity.host_id,
                    sources.c.kind == identity.kind,
                    sources.c.enabled.is_(True),
                    hosts.c.disabled.is_(False),
                )
            ).first()
            if active is None:
                raise ServiceError(401, "unauthorized", "Valid source credentials required")
            previous = connection.execute(select(func.max(events.c.received_at))).scalar() or 0
            received = max(to_us(self.clock()), previous + 1)
            references = {item.reference for item in batch if item.reference is not None}
            known = (
                connection.execute(
                    select(delivery_keys.c.source_reference, delivery_keys.c.expires_at).where(
                        delivery_keys.c.source_id == identity.id,
                        delivery_keys.c.source_reference.in_(references),
                    )
                ).all()
                if references
                else []
            )
            seen = {row.source_reference for row in known if row.expires_at > received}
            expired = [row.source_reference for row in known if row.expires_at <= received]
            if expired:
                connection.execute(
                    delivery_keys.delete().where(
                        delivery_keys.c.source_id == identity.id,
                        delivery_keys.c.source_reference.in_(expired),
                    )
                )
            event_rows: list[dict[str, Any]] = []
            key_rows: list[dict[str, Any]] = []
            pending_rows: list[dict[str, Any]] = []
            buckets: dict[tuple[Any, ...], dict[str, Any]] = {}
            dimensions = ("bucket", "host_id", "src_ip_key", "source", "category", "dst_port_key")
            for item in batch:
                if item.reference is not None and item.reference in seen:
                    continue
                event_id = str(uuid4())
                values = {
                    **item.values,
                    "id": event_id,
                    "source_id": identity.id,
                    "received_at": received,
                }
                event_rows.append(values)
                if item.reference is not None:
                    seen.add(item.reference)
                    key_rows.append(
                        {
                            "source_id": identity.id,
                            "source_reference": item.reference,
                            "event_id": event_id,
                            "first_received_at": received,
                            "expires_at": received + dedup_days * DAY_US,
                        }
                    )
                pending_rows.append({"event_id": event_id, "created_at": received})
                key = (
                    (values["timestamp"] // HOUR_US) * HOUR_US,
                    identity.host_id,
                    values["src_ip"] or "",
                    values["source"],
                    values["category"],
                    values["dst_port"] if values["dst_port"] is not None else -1,
                )
                bucket = buckets.setdefault(
                    key,
                    {
                        **dict(zip(dimensions, key, strict=True)),
                        "event_count": 0,
                        "first_seen": values["timestamp"],
                        "last_seen": values["timestamp"],
                    },
                )
                bucket["event_count"] += 1
                bucket["first_seen"] = min(bucket["first_seen"], values["timestamp"])
                bucket["last_seen"] = max(bucket["last_seen"], values["timestamp"])
            if event_rows:
                # executemany batches stay in the same transaction as dedup and counters.
                connection.execute(events.insert(), event_rows)
                if key_rows:
                    connection.execute(delivery_keys.insert(), key_rows)
                connection.execute(pending_events.insert(), pending_rows)
                statement = insert(event_rollups)
                connection.execute(
                    statement.on_conflict_do_update(
                        index_elements=list(dimensions),
                        set_={
                            "event_count": event_rollups.c.event_count
                            + statement.excluded.event_count,
                            "first_seen": func.min(
                                event_rollups.c.first_seen, statement.excluded.first_seen
                            ),
                            "last_seen": func.max(
                                event_rollups.c.last_seen, statement.excluded.last_seen
                            ),
                        },
                    ),
                    list(buckets.values()),
                )
        return {
            "accepted": len(event_rows),
            "duplicates": len(batch) - len(event_rows),
            "schema_version": 1,
        }

    def disable_source(self, source_id: str) -> None:
        with self.write() as connection:
            result = connection.execute(
                update(sources).where(sources.c.id == source_id).values(enabled=False)
            )
            if result.rowcount != 1:
                raise ValueError("Source does not exist")


def public_event(row: dict[str, Any]) -> dict[str, Any]:
    from attackscope.core.time import from_us

    return {
        key: from_us(value) if key in ("timestamp", "received_at") else value
        for key, value in row.items()
        if key not in ("source_id", "http_path", "http_status", "ssh_outcome")
    }
