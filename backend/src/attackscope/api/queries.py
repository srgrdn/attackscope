import base64
import hashlib
import json
import sqlite3
import time
from collections.abc import Iterator
from contextlib import contextmanager
from ipaddress import ip_address
from typing import Any, Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, StrictInt, ValidationError, field_validator
from sqlalchemy import Connection, Engine, Select, func, select, tuple_

from attackscope.core.errors import ServiceError
from attackscope.core.time import DAY_US, detail_cutoff, from_us, to_us
from attackscope.normalization.events import Category, Severity, SourceKind, Timestamp, canonical_ip
from attackscope.storage.schema import events, hosts
from attackscope.storage.store import Store, public_event


class EventsQuery(BaseModel):
    model_config = ConfigDict(extra="forbid")
    from_time: Timestamp = Field(alias="from")
    to_time: Timestamp = Field(alias="to")
    host_id: UUID | None = None
    ip: str | None = Field(default=None, max_length=45)
    source: SourceKind | None = None
    category: Category | None = None
    port: int | None = Field(default=None, ge=0, le=65535)
    severity: Severity | None = None
    sort: Literal["timestamp"] = "timestamp"
    order: Literal["asc", "desc"] = "desc"
    limit: int = Field(default=100, ge=1, le=500)
    cursor: str | None = Field(default=None, max_length=2048)

    @field_validator("ip")
    @classmethod
    def validate_ip(cls, value: str | None) -> str | None:
        return canonical_ip(ip_address(value)) if value is not None else None


class Cursor(BaseModel):
    model_config = ConfigDict(extra="forbid")
    version: Literal[1] = 1
    timestamp: StrictInt = Field(ge=0, le=9_223_372_036_854_775_807)
    id: UUID
    watermark: StrictInt = Field(ge=0, le=9_223_372_036_854_775_807)
    fingerprint: str = Field(pattern="^[0-9a-f]{64}$")
    expires_at: StrictInt = Field(ge=0, le=9_223_372_036_854_775_807)


def encode_cursor(cursor: Cursor) -> str:
    return base64.urlsafe_b64encode(cursor.model_dump_json().encode()).decode().rstrip("=")


def decode_cursor(value: str) -> Cursor:
    try:
        data = base64.b64decode(value + "=" * (-len(value) % 4), altchars=b"-_", validate=True)
        return Cursor.model_validate_json(data)
    except (ValueError, ValidationError):
        raise ServiceError(422, "invalid_cursor", "Invalid cursor") from None


@contextmanager
def read_connection(engine: Engine, seconds: float) -> Iterator[Connection]:
    with engine.connect() as connection:
        driver = connection.connection.driver_connection
        assert isinstance(driver, sqlite3.Connection)
        deadline = time.monotonic() + seconds
        driver.set_progress_handler(lambda: int(time.monotonic() > deadline), 10000)
        try:
            yield connection
        finally:
            driver.set_progress_handler(None, 0)


def list_events(store: Store, query: EventsQuery, days: int, seconds: float) -> dict[str, Any]:
    now = to_us(store.clock())
    lower, upper = to_us(query.from_time), to_us(query.to_time)
    cutoff = detail_cutoff(now, days)
    if lower >= upper or upper - lower > days * DAY_US:
        raise ServiceError(422, "time_range", "Invalid or excessive time range")
    if lower < cutoff:
        raise ServiceError(410, "detail_unavailable", f"Detail available from {from_us(cutoff)}")
    parameters = query.model_dump(mode="json", by_alias=True, exclude={"cursor", "limit"})
    parameters.update({"from": lower, "to": upper})
    fingerprint = hashlib.sha256(json.dumps(parameters, sort_keys=True).encode()).hexdigest()
    position = decode_cursor(query.cursor) if query.cursor else None
    if position is not None:
        if position.expires_at < now:
            raise ServiceError(410, "cursor_expired", "Cursor expired; restart pagination")
        if position.fingerprint != fingerprint or position.expires_at > now + 900_000_000:
            raise ServiceError(422, "invalid_cursor", "Cursor does not match this query")
    with read_connection(store.engine, seconds) as connection:
        watermark = (
            position.watermark
            if position
            else connection.execute(select(func.max(events.c.received_at))).scalar() or 0
        )
        statement: Select[Any] = select(events).where(
            events.c.timestamp >= lower,
            events.c.timestamp < upper,
            events.c.received_at <= watermark,
        )
        for field, value in (
            ("host_id", str(query.host_id) if query.host_id else None),
            ("src_ip", query.ip),
            ("source", query.source),
            ("category", query.category),
            ("dst_port", query.port),
            ("severity", query.severity),
        ):
            if value is not None:
                statement = statement.where(events.c[field] == value)
        position_columns = tuple_(events.c.timestamp, events.c.id)
        if position:
            last = (position.timestamp, str(position.id))
            statement = statement.where(
                position_columns < last if query.order == "desc" else position_columns > last
            )
        ordering = [
            column.desc() if query.order == "desc" else column.asc()
            for column in (events.c.timestamp, events.c.id)
        ]
        rows = [
            dict(row)
            for row in connection.execute(
                statement.order_by(*ordering).limit(query.limit + 1)
            ).mappings()
        ]
    more = len(rows) > query.limit
    rows = rows[: query.limit]
    cursor = None
    if more:
        last_row = rows[-1]
        cursor = encode_cursor(
            Cursor(
                timestamp=last_row["timestamp"],
                id=UUID(last_row["id"]),
                watermark=watermark,
                fingerprint=fingerprint,
                expires_at=position.expires_at if position else now + 900_000_000,
            )
        )
    return {
        "items": [public_event(row) for row in rows],
        "next_cursor": cursor,
        "coverage": {"detail_available_from": from_us(cutoff), "kind": "detail"},
    }


def get_event(store: Store, event_id: UUID, days: int, seconds: float) -> dict[str, Any]:
    with read_connection(store.engine, seconds) as connection:
        row = (
            connection.execute(
                select(events).where(
                    events.c.id == str(event_id),
                    events.c.timestamp >= detail_cutoff(to_us(store.clock()), days),
                )
            )
            .mappings()
            .first()
        )
    if row is None:
        raise ServiceError(404, "not_found", "Event not found in retained detail")
    return public_event(dict(row))


def list_hosts(store: Store, limit: int, cursor: UUID | None, seconds: float) -> dict[str, Any]:
    statement = select(hosts).order_by(hosts.c.id).limit(limit + 1)
    if cursor:
        statement = statement.where(hosts.c.id > str(cursor))
    with read_connection(store.engine, seconds) as connection:
        rows = [dict(row) for row in connection.execute(statement).mappings()]
    more = len(rows) > limit
    rows = rows[:limit]
    for row in rows:
        row["created_at"] = from_us(row["created_at"])
    return {"items": rows, "next_cursor": rows[-1]["id"] if more else None}
