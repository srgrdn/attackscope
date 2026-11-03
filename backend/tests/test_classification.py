from typing import Any

import pytest
from fastapi.testclient import TestClient
from helpers import event
from sqlalchemy import func, select

from attackscope.api.runtime import Runtime
from attackscope.classification.engine import process_pending
from attackscope.storage.schema import events, findings, pending_events


def send(client: TestClient, runtime: Runtime, kind: str, batch: list[dict[str, Any]]) -> None:
    client.headers["Authorization"] = f"Bearer {runtime.test_tokens[kind]}"
    assert client.post("/api/v1/ingest/events", json=batch).status_code == 200


def test_threshold_replay_late_events_and_restart(client: TestClient, runtime: Runtime) -> None:
    send(client, runtime, "ssh", [event("ssh", f"ssh:{n}") for n in range(9)])
    process_pending(runtime.store, runtime.settings)
    with runtime.store.engine.connect() as connection:
        assert connection.scalar(select(func.count()).select_from(findings)) == 0
    item = event("ssh", "ssh:last", timestamp="2026-11-02T23:56:00Z")
    send(client, runtime, "ssh", [item])
    process_pending(runtime.store, runtime.settings)
    send(client, runtime, "ssh", [item])
    process_pending(runtime.store, runtime.settings)
    with runtime.store.engine.connect() as connection:
        row = connection.execute(select(findings)).mappings().one()
        assert row["event_count"] == 10
        assert len(row["evidence_ids"]) == 10
        assert row["reason"]["threshold"] == 10
        assert connection.scalar(select(func.count()).select_from(pending_events)) == 0
        assert (
            connection.scalar(
                select(func.count()).select_from(events).where(events.c.classification.is_not(None))
            )
            == 10
        )


def test_web_paths_port_probing_sensitive_and_benign404(
    client: TestClient, runtime: Runtime
) -> None:
    send(client, runtime, "http", [event(reference="benign", path="/missing", status=404)])
    process_pending(runtime.store, runtime.settings)
    with runtime.store.engine.connect() as connection:
        assert connection.scalar(select(func.count()).select_from(findings)) == 0
    send(
        client,
        runtime,
        "http",
        [event(reference=f"web:{n}", path=f"/path/{n}", status=404) for n in range(30)]
        + [event(reference="secret", path="/.env?token=dropped")],
    )
    send(
        client,
        runtime,
        "firewall",
        [event("firewall", f"port:{n}", dst_port=1000 + n) for n in range(10)],
    )
    while process_pending(runtime.store, runtime.settings):
        pass
    with runtime.store.engine.connect() as connection:
        ids = set(connection.execute(select(findings.c.rule_id)).scalars())
        assert ids == {"web_paths", "sensitive_path", "port_probing"}


def test_web_rate_evidence_cap_and_durable_work(client: TestClient, runtime: Runtime) -> None:
    send(client, runtime, "http", [event(reference=f"rate:{n}") for n in range(120)])
    from attackscope.storage.store import Store

    restarted = Store(runtime.store.engine, clock=runtime.store.clock)
    while process_pending(restarted, runtime.settings):
        pass
    with restarted.engine.connect() as connection:
        row = (
            connection.execute(select(findings).where(findings.c.rule_id == "web_rate"))
            .mappings()
            .one()
        )
        assert row["event_count"] == 120
        assert len(row["evidence_ids"]) == 100
        assert row["reason"]["evidence_truncated"]


def test_window_cache_skips_processed_delivery_but_rechecks_late_input(
    client: TestClient, runtime: Runtime
) -> None:
    from attackscope.classification.engine import WindowCache

    cache = WindowCache()
    send(client, runtime, "http", [event(reference=f"cached:{index}") for index in range(120)])
    assert process_pending(runtime.store, runtime.settings, 100, cache) == 100
    assert process_pending(runtime.store, runtime.settings, 100, cache) == 20
    send(client, runtime, "http", [event(reference="late-cache")])
    process_pending(runtime.store, runtime.settings, 100, cache)
    with runtime.store.engine.connect() as connection:
        assert (
            connection.execute(
                select(findings.c.event_count).where(findings.c.rule_id == "web_rate")
            ).scalar()
            == 121
        )


@pytest.mark.parametrize(
    "path",
    [
        "/.aws/config",
        "/.aws/credentials",
        "/.azure/credentials",
        "/.config/gcloud/application_default_credentials.json",
        "/.docker/config.json",
        "/.dockerenv",
        "/.config",
        "/.bzr/branch/format",
        "/admin/config.php",
        "/.env.local",
        "/.env.production",
        "/.env.development",
        "/.env.bak",
    ],
)
def test_expanded_sensitive_paths_have_versioned_evidence(
    client: TestClient, runtime: Runtime, path: str
) -> None:
    item = event(
        reference="sensitive-v2",
        path=path,
        status=307,
        user_agent="AttackScope recovery check spoofed",
    )
    send(client, runtime, "http", [item])
    process_pending(runtime.store, runtime.settings)
    # A forged operator marker must not bypass classification or deduplication.
    send(client, runtime, "http", [item])
    process_pending(runtime.store, runtime.settings)
    with runtime.store.engine.connect() as connection:
        row = connection.execute(select(findings)).mappings().one()
        saved = connection.execute(select(events)).mappings().one()
        assert row["rule_id"] == "sensitive_path" and row["rule_version"] == 2
        assert row["event_count"] == 1 and row["evidence_ids"] == [saved["id"]]
        assert row["reason"]["matched_paths"] == [path]
        assert row["reason"]["matched_paths_truncated"] is False
        assert saved["severity"] == "medium"


@pytest.mark.parametrize(
    "path",
    [
        "/.aws/credentials-help",
        "/docs/.aws/credentials",
        "/.docker/config.json.example",
        "/environment",
        "/config",
        "/.env.example",
        "/login",
        "/not-found",
    ],
)
def test_sensitive_paths_do_not_use_broad_substring_matching(
    client: TestClient, runtime: Runtime, path: str
) -> None:
    send(client, runtime, "http", [event(path=path, status=404)])
    process_pending(runtime.store, runtime.settings)
    with runtime.store.engine.connect() as connection:
        assert connection.scalar(select(func.count()).select_from(findings)) == 0


def test_sensitive_path_versions_preserve_existing_finding_history(
    client: TestClient, runtime: Runtime
) -> None:
    from attackscope.classification.engine import Rule, evaluate

    send(client, runtime, "http", [event(path="/.env")])
    with runtime.store.write() as connection:
        row = dict(connection.execute(select(events)).mappings().one())
        lower = row["timestamp"] // 300_000_000 * 300_000_000
        evaluate(
            connection, Rule("sensitive_path", "Sensitive path probing", "http", 300, 1), row, lower
        )
    process_pending(runtime.store, runtime.settings)
    with runtime.store.engine.connect() as connection:
        rows = connection.execute(select(findings)).mappings().all()
        assert {row["rule_version"] for row in rows} == {1, 2}
        assert len({row["id"] for row in rows}) == 2


def test_sensitive_path_reason_list_is_bounded(client: TestClient, runtime: Runtime) -> None:
    # Case variants are retained as observed evidence but bounded in the finding payload.
    from itertools import product

    paths = ["/.aws/" + "".join(chars) for chars in product(*[(c, c.upper()) for c in "config"])][
        :24
    ]
    send(
        client,
        runtime,
        "http",
        [event(reference=f"variant:{n}", path=path) for n, path in enumerate(paths)],
    )
    process_pending(runtime.store, runtime.settings)
    with runtime.store.engine.connect() as connection:
        row = connection.execute(select(findings)).mappings().one()
        assert row["event_count"] == 24
        assert len(row["reason"]["matched_paths"]) == 20
        assert row["reason"]["matched_paths_truncated"] is True
