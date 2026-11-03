"""Durable bounded work, fixed UTC windows and reproducible evidence."""

from collections import OrderedDict
from dataclasses import dataclass
from typing import Any
from uuid import NAMESPACE_URL, uuid5

from sqlalchemy import Connection, Select, delete, func, select, update
from sqlalchemy.dialects.sqlite import insert

from attackscope.core.config import Settings
from attackscope.storage.database import statement_deadline
from attackscope.storage.schema import events, findings, pending_events
from attackscope.storage.store import Store

SENSITIVE_PATHS = (
    "/.env",
    "/.git/config",
    "/wp-admin",
    "/wp-login.php",
    "/phpmyadmin",
    "/server-status",
    "/actuator/env",
    "/config.json",
    "/.env.local",
    "/.env.production",
    "/.env.development",
    "/.env.bak",
    "/.aws/config",
    "/.aws/credentials",
    "/.azure/credentials",
    "/.config/gcloud/application_default_credentials.json",
    "/.docker/config.json",
    "/.dockerenv",
    "/.config",
    "/.bzr/branch/format",
    "/admin/config.php",
)


@dataclass(frozen=True)
class Rule:
    id: str
    name: str
    source: str
    seconds: int
    threshold: int
    metric: str = "count"
    version: int = 1


def rules(settings: Settings) -> list[Rule]:
    return [
        Rule(
            "ssh_bruteforce",
            "SSH brute-force",
            "ssh",
            settings.ssh_window_seconds,
            settings.ssh_failure_threshold,
        ),
        Rule(
            "web_rate",
            "Web scanning: request frequency",
            "http",
            settings.web_rate_window_seconds,
            settings.web_request_threshold,
        ),
        Rule(
            "web_paths",
            "Web scanning: distinct paths",
            "http",
            settings.web_paths_window_seconds,
            settings.web_path_threshold,
            "paths",
        ),
        Rule("sensitive_path", "Sensitive path probing", "http", 300, 1, version=2),
        Rule(
            "port_probing",
            "Observed port probing",
            "firewall",
            settings.port_window_seconds,
            settings.port_threshold,
            "ports",
        ),
    ]


def rule_query(rule: Rule, row: dict[str, Any], lower: int) -> Select[Any]:
    statement = select(events).where(
        events.c.host_id == row["host_id"],
        events.c.src_ip == row["src_ip"],
        events.c.source == rule.source,
        events.c.timestamp >= lower,
        events.c.timestamp < lower + rule.seconds * 1_000_000,
    )
    if rule.id == "ssh_bruteforce":
        statement = statement.where(events.c.ssh_outcome.in_(("failure", "invalid_user")))
    if rule.id == "sensitive_path":
        statement = statement.where(func.lower(events.c.http_path).in_(SENSITIVE_PATHS))
    if rule.id == "port_probing":
        statement = statement.where(events.c.dst_port.is_not(None))
    return statement


def evaluate(connection: Connection, rule: Rule, row: dict[str, Any], lower: int) -> None:
    statement = rule_query(rule, row, lower)
    condition = statement.whereclause
    assert condition is not None
    metric = func.count()
    if rule.metric == "paths":
        metric = func.count(func.distinct(events.c.http_path))
    elif rule.metric == "ports":
        metric = func.count(func.distinct(events.c.dst_port))
    count, value, last = connection.execute(
        select(func.count(), metric, func.max(events.c.timestamp)).where(condition)
    ).one()
    if value < rule.threshold:
        return
    evidence = list(
        connection.execute(
            select(events.c.id)
            .where(condition)
            .order_by(events.c.timestamp, events.c.id)
            .limit(100)
        ).scalars()
    )
    identity = (
        f"attackscope:v{rule.version}:{rule.id}:{row['host_id']}:{row['src_ip']}:"
        f"{lower}:{rule.seconds}:{rule.threshold}"
    )
    finding_id = str(uuid5(NAMESPACE_URL, identity))
    values = dict(
        id=finding_id,
        rule_id=rule.id,
        rule_name=rule.name,
        rule_version=rule.version,
        host_id=row["host_id"],
        src_ip=row["src_ip"],
        source=rule.source,
        category=row["category"],
        severity="medium",
        timestamp=last,
        window_start=lower,
        window_end=lower + rule.seconds * 1_000_000,
        event_count=count,
        evidence_ids=evidence,
        reason={
            "description": (
                "Observed activity meets the configured threshold; "
                "success or intent is not established."
            ),
            "metric": rule.metric,
            "observed": value,
            "threshold": rule.threshold,
            "window_seconds": rule.seconds,
            "window_kind": "fixed_utc",
            "evidence_truncated": count > 100,
        },
    )
    if rule.id == "sensitive_path":
        paths = list(
            connection.execute(
                select(events.c.http_path)
                .where(condition)
                .distinct()
                .order_by(events.c.http_path)
                .limit(21)
            ).scalars()
        )
        values["reason"]["matched_paths"] = paths[:20]
        values["reason"]["matched_paths_truncated"] = len(paths) > 20
    connection.execute(
        insert(findings)
        .values(**values)
        .on_conflict_do_update(
            index_elements=[findings.c.id],
            set_={key: value for key, value in values.items() if key != "id"},
        )
    )
    connection.execute(
        update(events)
        .where(condition)
        .values(classification={"finding_id": finding_id, "rule_id": rule.id}, severity="medium")
    )


WindowKey = tuple[str, int, str, str, int, int, int]
WindowCache = OrderedDict[WindowKey, int]


def process_pending(
    store: Store, settings: Settings, limit: int = 100, cache: WindowCache | None = None
) -> int:
    evaluated: dict[WindowKey, int] = {}
    with (
        store.write() as connection,
        statement_deadline(connection, settings.query_timeout_seconds),
    ):
        rows = [
            dict(row)
            for row in connection.execute(
                select(events)
                .join(pending_events, events.c.id == pending_events.c.event_id)
                .order_by(pending_events.c.created_at, events.c.id)
                .limit(limit)
            ).mappings()
        ]
        watermark = connection.scalar(select(func.max(events.c.received_at))) or 0
        visited: set[WindowKey] = set()
        for row in rows:
            if row["src_ip"] is None:
                continue
            for rule in rules(settings):
                if row["source"] != rule.source:
                    continue
                if (
                    rule.id == "sensitive_path"
                    and (row["http_path"] or "").lower() not in SENSITIVE_PATHS
                ):
                    continue
                if rule.id == "ssh_bruteforce" and row["ssh_outcome"] not in (
                    "failure",
                    "invalid_user",
                ):
                    continue
                width = rule.seconds * 1_000_000
                lower = row["timestamp"] // width * width
                key = (
                    rule.id,
                    rule.version,
                    row["host_id"],
                    row["src_ip"],
                    lower,
                    rule.seconds,
                    rule.threshold,
                )
                if cache is not None and cache.get(key, -1) >= row["received_at"]:
                    continue
                if key not in visited:
                    evaluate(connection, rule, row, lower)
                    visited.add(key)
                    evaluated[key] = watermark
        if rows:
            connection.execute(
                delete(pending_events).where(
                    pending_events.c.event_id.in_([row["id"] for row in rows])
                )
            )
    if cache is not None:
        cache.update(evaluated)
        for key in evaluated:
            cache.move_to_end(key)
        while len(cache) > 4096:
            cache.popitem(last=False)
    return len(rows)
