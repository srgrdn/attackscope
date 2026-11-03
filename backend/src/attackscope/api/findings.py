from typing import Any

from sqlalchemy import select

from attackscope.api.queries import EventsQuery, read_connection
from attackscope.api.timeline import validate_range
from attackscope.core.time import from_us
from attackscope.storage.schema import events, findings
from attackscope.storage.store import Store


def list_findings(store: Store, query: EventsQuery, days: int, seconds: float) -> dict[str, Any]:
    lower, upper = validate_range(store, query, days)
    statement = select(findings).where(findings.c.timestamp >= lower, findings.c.timestamp < upper)
    for key, value in (
        ("host_id", str(query.host_id) if query.host_id else None),
        ("src_ip", query.ip),
        ("source", query.source),
        ("category", query.category),
        ("severity", query.severity),
    ):
        if value is not None:
            statement = statement.where(findings.c[key] == value)
    if query.port is not None:
        statement = statement.where(
            select(events.c.id)
            .where(
                events.c.host_id == findings.c.host_id,
                events.c.src_ip == findings.c.src_ip,
                events.c.source == findings.c.source,
                events.c.timestamp >= findings.c.window_start,
                events.c.timestamp < findings.c.window_end,
                events.c.dst_port == query.port,
            )
            .exists()
        )
    with read_connection(store.engine, seconds) as connection:
        rows = [
            dict(row)
            for row in connection.execute(
                statement.order_by(findings.c.timestamp.desc(), findings.c.id).limit(501)
            ).mappings()
        ]
    more = len(rows) > 500
    rows = rows[:500]
    for row in rows:
        for key in ("timestamp", "window_start", "window_end"):
            row[key] = from_us(row[key])
    return {"items": rows, "truncated": more, "limit": 500}
