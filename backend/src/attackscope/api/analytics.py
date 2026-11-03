from typing import Any

from sqlalchemy import Column, func, select

from attackscope.api.findings import list_findings
from attackscope.api.queries import EventsQuery, read_connection
from attackscope.api.timeline import event_filter, validate_range
from attackscope.core.time import HOUR_US, detail_cutoff, from_us, to_us
from attackscope.enrichment import UnavailableEnrichment
from attackscope.storage.schema import event_rollups, events, hosts
from attackscope.storage.store import Store


def detail_statistics(
    store: Store, query: EventsQuery, days: int, seconds: float
) -> dict[str, Any]:
    validate_range(store, query, days)
    condition = event_filter(query).whereclause
    assert condition is not None
    with read_connection(store.engine, seconds) as connection:
        count, first, last, unique, suspicious, http, suspicious_http = connection.execute(
            select(
                func.count(),
                func.min(events.c.timestamp),
                func.max(events.c.timestamp),
                func.count(func.distinct(events.c.src_ip)),
                func.count().filter(events.c.classification.is_not(None)),
                func.count().filter(events.c.source == "http"),
                func.count().filter(
                    events.c.source == "http", events.c.classification.is_not(None)
                ),
            ).where(condition)
        ).one()

        def distribution(column: Column[Any], limit: int = 100) -> list[dict[str, Any]]:
            statement = (
                select(column.label("value"), func.count().label("count"))
                .where(condition, column.is_not(None))
                .group_by(column)
                .order_by(func.count().desc(), column)
                .limit(limit + 1)
            )
            rows = [dict(row) for row in connection.execute(statement).mappings()]
            return rows

        result: dict[str, Any] = {
            "total_events": count,
            "unique_ips": unique,
            "suspicious_events": suspicious,
            "http_requests": http,
            "suspicious_http_requests": suspicious_http,
            "first_seen": from_us(first) if first is not None else None,
            "last_seen": from_us(last) if last is not None else None,
        }
        for name, column in (
            ("types", events.c.event_type),
            ("categories", events.c.category),
            ("hosts", events.c.host_id),
            ("ports", events.c.dst_port),
            ("paths", events.c.http_path),
            ("http_statuses", events.c.http_status),
            ("ssh_outcomes", events.c.ssh_outcome),
            ("top_ips", events.c.src_ip),
        ):
            values = distribution(column)
            result[name] = {"items": values[:100], "truncated": len(values) > 100}
        host_ids = [row["value"] for row in result["hosts"]["items"]]
        names = dict(
            connection.execute(select(hosts.c.id, hosts.c.name).where(hosts.c.id.in_(host_ids)))
            .tuples()
            .all()
        )
        for row in result["hosts"]["items"]:
            row["name"] = names.get(row["value"], row["value"])
        bucket = events.c.timestamp // HOUR_US * HOUR_US
        result["activity"] = [
            {"timestamp": from_us(row.bucket), "count": row._mapping["count"]}
            for row in connection.execute(
                select(bucket.label("bucket"), func.count().label("count"))
                .where(condition)
                .group_by(bucket)
                .order_by(bucket)
            )
        ]
        result["suspicious_sources"] = connection.scalar(
            select(func.count(func.distinct(events.c.src_ip))).where(
                condition, events.c.classification.is_not(None)
            )
        )
    result["coverage"] = {"kind": "detail", "range": "selected_period", "distribution_limit": 100}
    return result


def ip_explorer(
    store: Store, query: EventsQuery, days: int, seconds: float, aggregate_days: int = 365
) -> dict[str, Any]:
    result = detail_statistics(store, query, days, seconds)
    result["ip"] = query.ip
    result["enrichment"] = UnavailableEnrichment().lookup(query.ip or "")
    with read_connection(store.engine, seconds) as connection:
        first, last = connection.execute(
            select(func.min(event_rollups.c.first_seen), func.max(event_rollups.c.last_seen)).where(
                event_rollups.c.src_ip_key == query.ip,
                event_rollups.c.bucket >= detail_cutoff(to_us(store.clock()), aggregate_days),
            )
        ).one()
    result["retained_first_seen"] = from_us(first) if first is not None else None
    result["retained_last_seen"] = from_us(last) if last is not None else None
    result["findings"] = list_findings(store, query, days, seconds)
    return result
