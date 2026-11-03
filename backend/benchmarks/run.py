"""Reproducible isolated storage/query benchmark; never opens the working volume."""

import argparse
import json
import platform
import resource
import statistics
import tempfile
import time
from datetime import timedelta
from pathlib import Path
from uuid import uuid4

from sqlalchemy import func, select

from attackscope.api.analytics import detail_statistics
from attackscope.api.queries import EventsQuery, list_events
from attackscope.api.timeline import timeline
from attackscope.classification.engine import process_pending
from attackscope.core.config import Settings
from attackscope.core.time import to_us, utc_now
from attackscope.normalization.events import batch_adapter, normalize
from attackscope.storage.database import create_database
from attackscope.storage.migrations import upgrade_database
from attackscope.storage.schema import events
from attackscope.storage.store import Store

parser = argparse.ArgumentParser()
parser.add_argument("--events", type=int, default=10000)
args = parser.parse_args()
assert 1 <= args.events <= 1000000
with tempfile.TemporaryDirectory(prefix="attackscope-benchmark-") as directory:
    path = Path(directory) / "bench.db"
    engine = create_database(path)
    upgrade_database(engine)
    now = utc_now().replace(microsecond=0)
    store = Store(engine, clock=lambda: now)
    host = store.create_host("synthetic-benchmark")
    sid = str(uuid4())
    token = f"{sid}." + "A" * 43
    store.create_source(host, "http", sid, token)
    identity = store.authenticate(f"Bearer {token}")
    start = time.perf_counter()
    for offset in range(0, args.events, 500):
        raw = [
            {
                "transport_version": 1,
                "source": "http",
                "source_reference": f"bench:{index}",
                "payload": {
                    "timestamp": (now - timedelta(seconds=1 + index % 86400)).isoformat(),
                    "remote_addr": f"192.0.2.{index % 200 + 1}",
                    "request_method": "GET",
                    "path": f"/synthetic/{index % 40}",
                    "status": 200,
                    "dst_port": 443,
                },
            }
            for index in range(offset, min(offset + 500, args.events))
        ]
        batch = [
            normalize(item, host, "http", to_us(now), 30)
            for item in batch_adapter.validate_python(raw)
        ]
        store.persist(identity, batch, 30)
    ingest = time.perf_counter() - start
    query = EventsQuery.model_validate(
        {"from": (now - timedelta(days=1)).isoformat(), "to": now.isoformat()}
    )
    timings = {}
    for name, call in [
        ("events", lambda: list_events(store, query, 30, 5)),
        ("timeline", lambda: timeline(store, query, 30, 5)),
        ("overview", lambda: detail_statistics(store, query, 30, 5)),
    ]:
        values = []
        for _ in range(10):
            start = time.perf_counter()
            result = call()
            values.append((time.perf_counter() - start) * 1000)
        timings[name] = {
            "p50_ms": round(statistics.median(values), 2),
            "p95_ms": round(sorted(values)[-1], 2),
        }
    start = time.perf_counter()
    processed = process_pending(store, Settings())
    classification = time.perf_counter() - start
    with engine.connect() as connection:
        assert connection.scalar(select(func.count()).select_from(events)) == args.events
        plans = [
            list(row)
            for row in connection.exec_driver_sql(
                (
                    "EXPLAIN QUERY PLAN SELECT id FROM events WHERE src_ip=? "
                    "AND timestamp>=? AND timestamp<? ORDER BY timestamp,id LIMIT 100"
                ),
                ("192.0.2.1", to_us(now - timedelta(days=1)), to_us(now)),
            )
        ]
    print(
        json.dumps(
            {
                "events": args.events,
                "python": platform.python_version(),
                "platform": platform.platform(),
                "cpus_visible": __import__("os").cpu_count(),
                "ingest_seconds": round(ingest, 3),
                "events_per_second": round(args.events / ingest),
                "query": timings,
                "classification_batch": {"events": processed, "seconds": round(classification, 3)},
                "peak_process_rss_mib": round(
                    resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / 1024, 2
                ),
                "db_bytes": path.stat().st_size,
                "wal_bytes": Path(str(path) + "-wal").stat().st_size,
                "ip_query_plan": plans,
            },
            ensure_ascii=False,
        ),
        flush=True,
    )
    engine.dispose()
