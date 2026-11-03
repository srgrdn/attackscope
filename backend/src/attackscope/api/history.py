from typing import Any

from sqlalchemy import func, select

from attackscope.api.queries import EventsQuery, read_connection
from attackscope.core.errors import ServiceError
from attackscope.core.time import DAY_US, HOUR_US, detail_cutoff, from_us, to_us
from attackscope.storage.schema import event_rollups as rollups
from attackscope.storage.store import Store


def historical_statistics(
    store: Store, query: EventsQuery, days: int, seconds: float
) -> dict[str, Any]:
    lower, upper = to_us(query.from_time), to_us(query.to_time)
    if lower >= upper or upper - lower > days * DAY_US:
        raise ServiceError(422, "time_range", "Invalid or excessive historical range")
    if lower < detail_cutoff(to_us(store.clock()), days):
        raise ServiceError(410, "history_unavailable", "Historical aggregates expired")
    if query.severity is not None:
        raise ServiceError(422, "unsupported_filter", "Historical rollups do not retain severity")
    # Full UTC hours only: exact counts, no proportional estimates of partial buckets.
    effective_lower = (lower + HOUR_US - 1) // HOUR_US * HOUR_US
    effective_upper = upper // HOUR_US * HOUR_US
    condition = [rollups.c.bucket >= effective_lower, rollups.c.bucket < effective_upper]
    for key, value in (
        ("host_id", str(query.host_id) if query.host_id else None),
        ("src_ip_key", query.ip),
        ("source", query.source),
        ("category", query.category),
        ("dst_port_key", query.port),
    ):
        if value is not None:
            condition.append(rollups.c[key] == value)
    with read_connection(store.engine, seconds) as connection:
        count, unique = connection.execute(
            select(
                func.coalesce(func.sum(rollups.c.event_count), 0),
                func.count(func.distinct(func.nullif(rollups.c.src_ip_key, ""))),
            ).where(*condition)
        ).one()
        width = HOUR_US if upper - lower <= 31 * DAY_US else DAY_US
        bucket = rollups.c.bucket // width * width
        activity = [
            {"timestamp": from_us(row.bucket), "count": row._mapping["count"]}
            for row in connection.execute(
                select(bucket.label("bucket"), func.sum(rollups.c.event_count).label("count"))
                .where(*condition)
                .group_by(bucket)
                .order_by(bucket)
            )
        ]
        dimensions: dict[str, Any] = {}
        for name, key in (
            ("hosts", "host_id"),
            ("ips", "src_ip_key"),
            ("categories", "category"),
            ("ports", "dst_port_key"),
            ("sources", "source"),
        ):
            column = rollups.c[key]
            statement = (
                select(column.label("value"), func.sum(rollups.c.event_count).label("count"))
                .where(
                    *condition,
                    column != ("" if key == "src_ip_key" else -1)
                    if key in ("src_ip_key", "dst_port_key")
                    else column.is_not(None),
                )
                .group_by(column)
                .order_by(func.sum(rollups.c.event_count).desc(), column)
                .limit(101)
            )
            rows = [dict(row) for row in connection.execute(statement).mappings()]
            dimensions[name] = {"items": rows[:100], "truncated": len(rows) > 100}
    return {
        "total_events": count,
        "unique_ips": unique,
        "activity": activity,
        **dimensions,
        "coverage": {
            "kind": "hourly_rollups",
            "effective_from": from_us(effective_lower),
            "effective_to": from_us(max(effective_lower, effective_upper)),
            "partial_hours_excluded": True,
            "bucket_seconds": width // 1_000_000,
            "detail_fields_unavailable": [
                "path",
                "http_status",
                "ssh_outcome",
                "severity",
                "safe_original",
            ],
        },
    }
