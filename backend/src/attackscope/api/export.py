import csv
import io
import json
from typing import Any, Literal

from starlette.responses import Response

from attackscope.api.queries import EventsQuery, read_connection
from attackscope.api.timeline import event_filter, validate_range
from attackscope.core.errors import ServiceError
from attackscope.storage.schema import events
from attackscope.storage.store import Store, public_event

MAX_EXPORT_EVENTS = 10000
MAX_EXPORT_BYTES = 8 * 1024 * 1024


def csv_cell(value: Any) -> str:
    text = "" if value is None else str(value)
    if text.startswith(("\t", "\r", "\n")) or text.lstrip().startswith(("=", "+", "-", "@")):
        return "'" + text
    return text


def export_events(
    store: Store, query: EventsQuery, kind: Literal["csv", "json"], days: int, seconds: float
) -> Response:
    validate_range(store, query, days)
    if query.cursor:
        raise ServiceError(422, "export_cursor", "Export applies to the entire filtered range")
    order = [
        column.desc() if query.order == "desc" else column.asc()
        for column in (events.c.timestamp, events.c.id)
    ]
    statement = event_filter(query).order_by(*order).limit(MAX_EXPORT_EVENTS + 1)
    output = io.StringIO(newline="")
    writer = csv.writer(output, quoting=csv.QUOTE_ALL)
    fields = (
        "id",
        "timestamp",
        "host_id",
        "source",
        "event_type",
        "category",
        "severity",
        "src_ip",
        "dst_ip",
        "src_port",
        "dst_port",
        "protocol",
        "attributes",
        "classification",
    )
    if kind == "csv":
        writer.writerow(fields)
    else:
        output.write("[")
    count, size = 0, 0
    with read_connection(store.engine, seconds) as connection:
        for raw in connection.execute(statement).mappings():
            count += 1
            if count > MAX_EXPORT_EVENTS:
                raise ServiceError(
                    413, "export_limit", "Export limit is 10000 events; narrow filters"
                )
            row = public_event(dict(raw))
            before = output.tell()
            if kind == "csv":
                writer.writerow(
                    [
                        csv_cell(
                            json.dumps(row[key], ensure_ascii=False)
                            if isinstance(row[key], dict)
                            else row[key]
                        )
                        for key in fields
                    ]
                )
            else:
                if count > 1:
                    output.write(",")
                output.write(json.dumps(row, ensure_ascii=False, allow_nan=False))
            # StringIO size is characters; account UTF-8 bytes incrementally.
            output.seek(before)
            size += len(output.read().encode("utf-8"))
            output.seek(0, io.SEEK_END)
            if size > MAX_EXPORT_BYTES - 1024:
                raise ServiceError(413, "export_limit", "Export limit is 8 MiB; narrow filters")
    if kind == "json":
        output.write("]")
    return Response(
        output.getvalue(),
        media_type="text/csv" if kind == "csv" else "application/json",
        headers={
            "Content-Disposition": f'attachment; filename="attackscope-events.{kind}"',
            "Cache-Control": "no-store",
            "X-Content-Type-Options": "nosniff",
        },
    )
