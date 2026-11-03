"""Bounded timeline queries; all intervals are half-open UTC."""

from typing import Any

from pydantic import Field
from sqlalchemy import Select, func, select

from attackscope.api.queries import EventsQuery, read_connection
from attackscope.core.errors import ServiceError
from attackscope.core.time import DAY_US, detail_cutoff, from_us, to_us
from attackscope.storage.schema import events
from attackscope.storage.store import Store, public_event


class TimelineQuery(EventsQuery):
    target_buckets: int = Field(default=60, ge=20, le=500)


def event_filter(query: EventsQuery) -> Select[Any]:
    statement = select(events).where(
        events.c.timestamp >= to_us(query.from_time), events.c.timestamp < to_us(query.to_time)
    )
    for key, value in (
        ("host_id", str(query.host_id) if query.host_id else None),
        ("src_ip", query.ip),
        ("source", query.source),
        ("category", query.category),
        ("dst_port", query.port),
        ("severity", query.severity),
    ):
        if value is not None:
            statement = statement.where(events.c[key] == value)
    return statement


def validate_range(store: Store, query: EventsQuery, days: int) -> tuple[int, int]:
    lower, upper = to_us(query.from_time), to_us(query.to_time)
    if lower >= upper or upper - lower > days * DAY_US:
        raise ServiceError(422, "time_range", "Invalid or excessive time range")
    if lower < detail_cutoff(to_us(store.clock()), days):
        raise ServiceError(410, "detail_unavailable", "Requested detail has expired")
    return lower, upper


def timeline(
    store: Store, query: EventsQuery, days: int, seconds: float, target_buckets: int = 60
) -> dict[str, Any]:
    lower, upper = validate_range(store, query, days)
    statement = event_filter(query)
    detail_limit = min(1500, target_buckets * 3)
    with read_connection(store.engine, seconds) as connection:
        rows = list(
            connection.execute(
                statement.order_by(events.c.timestamp, events.c.id).limit(detail_limit + 1)
            ).mappings()
        )
        if len(rows) <= detail_limit:
            return {
                "mode": "events",
                "total": len(rows),
                "items": [public_event(dict(row)) for row in rows],
                "buckets": [],
                "bucket_seconds": None,
            }
        # At most 500 time cells × 4 source/category combinations = 2004 rows.
        width = next(
            (
                n
                for n in (1, 5, 15, 60, 300, 900, 3600, 21600, 86400)
                if (upper - lower) / (n * 1_000_000) <= target_buckets
            ),
            86400,
        )
        bucket = (events.c.timestamp // (width * 1_000_000)) * (width * 1_000_000)
        condition = statement.whereclause
        assert condition is not None
        grouped = (
            select(
                bucket.label("bucket"),
                events.c.source,
                events.c.category,
                func.count().label("count"),
            )
            .where(condition)
            .group_by(bucket, events.c.source, events.c.category)
            .order_by(bucket)
        )
        buckets = [
            {
                "from": from_us(max(row.bucket, lower)),
                "to": from_us(min(row.bucket + width * 1_000_000, upper)),
                "source": row.source,
                "category": row.category,
                "count": row._mapping["count"],
            }
            for row in connection.execute(grouped)
        ]
    return {
        "mode": "buckets",
        "total": sum(item["count"] for item in buckets),
        "items": [],
        "buckets": buckets,
        "bucket_seconds": width,
    }
