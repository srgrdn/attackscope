import asyncio
import json
from ipaddress import ip_address
from typing import Annotated, Any, Literal
from uuid import UUID

from fastapi import APIRouter, Query, Request
from pydantic import ValidationError
from starlette.concurrency import run_in_threadpool
from starlette.requests import ClientDisconnect
from starlette.responses import Response

from attackscope.api.analytics import detail_statistics, ip_explorer
from attackscope.api.export import export_events
from attackscope.api.findings import list_findings
from attackscope.api.history import historical_statistics
from attackscope.api.queries import EventsQuery, get_event, list_events, list_hosts
from attackscope.api.runtime import Runtime
from attackscope.api.schemas import EventOut, EventsPage, HostsPage, IngestionResult
from attackscope.api.timeline import TimelineQuery, timeline
from attackscope.core.errors import ServiceError
from attackscope.core.time import to_us
from attackscope.normalization.events import batch_adapter, canonical_ip, normalize
from attackscope.normalization.journal import adapt_journal


def strict_object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("Duplicate JSON key")
        result[key] = value
    return result


def reject_constant(value: str) -> None:
    raise ValueError("Non-finite JSON constant")


def ingestion_router(runtime: Runtime) -> APIRouter:
    router = APIRouter(prefix="/api/v1")

    @router.post("/ingest/events", response_model=IngestionResult)
    async def ingest(request: Request) -> dict[str, int]:
        settings = runtime.settings
        if len(request.headers.getlist("authorization")) != 1:
            raise ServiceError(401, "unauthorized", "Valid source credentials required")
        identity = await run_in_threadpool(
            runtime.store.authenticate, request.headers["authorization"]
        )
        with runtime.source_slot(identity.id):
            if request.headers.get("content-encoding", "identity").lower() != "identity":
                raise ServiceError(415, "encoding", "Compressed ingestion is unsupported")
            if (
                request.headers.get("content-type", "").split(";", 1)[0].strip().lower()
                != "application/json"
            ):
                raise ServiceError(415, "content_type", "JSON body required")
            length = request.headers.get("content-length")
            if length is not None:
                if not length.isascii() or not length.isdecimal():
                    raise ServiceError(422, "content_length", "Invalid content length")
                if len(length) > 10 or int(length) > settings.max_body_bytes:
                    raise ServiceError(413, "body_size", "Event batch is too large")
            body = bytearray()
            try:
                async with asyncio.timeout(settings.body_timeout_seconds):
                    async for chunk in request.stream():
                        if len(body) + len(chunk) > settings.max_body_bytes:
                            raise ServiceError(413, "body_size", "Event batch is too large")
                        body.extend(chunk)
            except (TimeoutError, ClientDisconnect):
                raise ServiceError(408, "body_timeout", "Body incomplete or timed out") from None
            try:
                raw = json.loads(
                    body.decode("utf-8"),
                    object_pairs_hook=strict_object,
                    parse_constant=reject_constant,
                )
                if not isinstance(raw, list) or not 1 <= len(raw) <= settings.max_batch_events:
                    raise ServiceError(422, "batch_size", "Batch size outside accepted limits")
                batch = batch_adapter.validate_python([adapt_journal(item) for item in raw])
                now = to_us(runtime.store.clock())
                normalized = [
                    normalize(
                        item, identity.host_id, identity.kind, now, settings.detail_retention_days
                    )
                    for item in batch
                ]
            except (ValidationError, ValueError, RecursionError):
                raise ServiceError(422, "invalid_events", "Batch contains invalid events") from None
            return await run_in_threadpool(
                runtime.store.persist, identity, normalized, settings.dedup_retention_days
            )

    return router


def read_router(runtime: Runtime) -> APIRouter:
    router = APIRouter(prefix="/api/v1")
    settings = runtime.settings

    @router.get("/hosts", response_model=HostsPage)
    def hosts(
        limit: Annotated[int, Query(ge=1, le=500)] = 100, cursor: UUID | None = None
    ) -> dict[str, Any]:
        return list_hosts(runtime.store, limit, cursor, settings.query_timeout_seconds)

    @router.get("/history")
    def history(query: Annotated[EventsQuery, Query()]) -> dict[str, Any]:
        return historical_statistics(
            runtime.store, query, settings.aggregate_retention_days, settings.query_timeout_seconds
        )

    @router.get("/overview")
    def overview(query: Annotated[EventsQuery, Query()]) -> dict[str, Any]:
        return runtime.cached(
            "overview:" + query.model_dump_json(),
            lambda: detail_statistics(
                runtime.store, query, settings.detail_retention_days, settings.query_timeout_seconds
            ),
        )

    @router.get("/events/export.{kind}")
    def export(kind: Literal["csv", "json"], query: Annotated[EventsQuery, Query()]) -> Response:
        return export_events(
            runtime.store,
            query,
            kind,
            settings.detail_retention_days,
            settings.query_timeout_seconds,
        )

    @router.get("/ips/{address}")
    def ip_history(address: str, query: Annotated[EventsQuery, Query()]) -> dict[str, Any]:
        try:
            ip = canonical_ip(ip_address(address))
        except ValueError:
            raise ServiceError(422, "invalid_ip", "Invalid IP address") from None
        return ip_explorer(
            runtime.store,
            query.model_copy(update={"ip": ip}),
            settings.detail_retention_days,
            settings.query_timeout_seconds,
            settings.aggregate_retention_days,
        )

    @router.get("/findings")
    def findings(query: Annotated[EventsQuery, Query()]) -> dict[str, Any]:
        return list_findings(
            runtime.store, query, settings.detail_retention_days, settings.query_timeout_seconds
        )

    @router.get("/timeline")
    def event_timeline(query: Annotated[TimelineQuery, Query()]) -> dict[str, Any]:
        return timeline(
            runtime.store,
            query,
            settings.detail_retention_days,
            settings.query_timeout_seconds,
            query.target_buckets,
        )

    @router.get("/events", response_model=EventsPage)
    def events(query: Annotated[EventsQuery, Query()]) -> dict[str, Any]:
        return list_events(
            runtime.store, query, settings.detail_retention_days, settings.query_timeout_seconds
        )

    @router.get("/events/{event_id}", response_model=EventOut)
    def event(event_id: UUID) -> dict[str, Any]:
        return get_event(
            runtime.store, event_id, settings.detail_retention_days, settings.query_timeout_seconds
        )

    return router
