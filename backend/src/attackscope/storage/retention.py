"""Small restart-safe transactions. Never subtract counters when deleting detail."""

from typing import Any

from sqlalchemy import Table, delete, select, tuple_

from attackscope.core.config import Settings
from attackscope.core.time import detail_cutoff, to_us
from attackscope.storage.database import statement_deadline
from attackscope.storage.schema import delivery_keys, event_rollups, events, findings
from attackscope.storage.store import Store


def cleanup(store: Store, settings: Settings, batch_size: int = 1000) -> dict[str, int]:
    now = to_us(store.clock())
    detail = detail_cutoff(now, settings.detail_retention_days)
    historical = detail_cutoff(now, settings.aggregate_retention_days)
    counts: dict[str, int] = {}
    with (
        store.write() as connection,
        statement_deadline(connection, settings.query_timeout_seconds),
    ):

        def remove(table: Table, condition: Any) -> None:
            columns = list(table.primary_key.columns)
            key = tuple_(*columns)
            candidates = select(*columns).where(condition).limit(batch_size)
            result = connection.execute(delete(table).where(key.in_(candidates)))
            counts[table.name] = result.rowcount

        remove(events, events.c.timestamp < detail)
        remove(event_rollups, event_rollups.c.bucket < historical)
        remove(findings, findings.c.timestamp < historical)
        remove(delivery_keys, delivery_keys.c.expires_at < now)
    return counts
