from fastapi.testclient import TestClient
from helpers import event

from attackscope.api.apps import create_app
from attackscope.api.runtime import Runtime
from attackscope.core.config import Settings


def test_body_and_batch_limits(runtime: Runtime) -> None:
    limited = Runtime(runtime.store, Settings(max_body_bytes=1024, max_batch_events=2))
    with TestClient(create_app(runtime.store.engine, ingestion=True, runtime=limited)) as client:
        client.headers["Authorization"] = f"Bearer {runtime.test_tokens['http']}"
        assert client.post("/api/v1/ingest/events", json=[event()] * 3).status_code == 422
        assert (
            client.post(
                "/api/v1/ingest/events",
                content=b"x" * 1025,
                headers={"Content-Type": "application/json"},
            ).status_code
            == 413
        )

        def chunks():
            yield b"x" * 600
            yield b"x" * 600

        assert (
            client.post(
                "/api/v1/ingest/events",
                content=chunks(),
                headers={"Content-Type": "application/json"},
            ).status_code
            == 413
        )
        assert (
            client.post(
                "/api/v1/ingest/events",
                content=b"[]",
                headers={"Content-Type": "application/json", "Content-Encoding": "gzip"},
            ).status_code
            == 415
        )
        assert (
            client.post(
                "/api/v1/ingest/events", content=b"[]", headers={"Content-Type": "text/plain"}
            ).status_code
            == 415
        )


def test_rate_limit_recovers_and_is_scoped_to_source(runtime: Runtime) -> None:
    now = [0.0]
    limited = Runtime(
        runtime.store,
        Settings(source_burst=1, source_requests_per_second=1),
        monotonic=lambda: now[0],
    )
    with TestClient(create_app(runtime.store.engine, ingestion=True, runtime=limited)) as client:
        headers = {"Authorization": f"Bearer {runtime.test_tokens['http']}"}
        assert (
            client.post("/api/v1/ingest/events", json=[event()], headers=headers).status_code == 200
        )
        result = client.post("/api/v1/ingest/events", json=[event()], headers=headers)
        assert result.status_code == 429 and result.headers["Retry-After"] == "1"
        assert (
            client.post(
                "/api/v1/ingest/events",
                json=[event("ssh")],
                headers={"Authorization": f"Bearer {runtime.test_tokens['ssh']}"},
            ).status_code
            == 200
        )
        now[0] += 1
        assert (
            client.post("/api/v1/ingest/events", json=[event()], headers=headers).status_code == 200
        )


def test_concurrency_limits_release_permits(runtime: Runtime) -> None:
    with TestClient(create_app(runtime.store.engine, ingestion=True, runtime=runtime)) as client:
        headers = {"Authorization": f"Bearer {runtime.test_tokens['http']}"}
        source_id = runtime.test_tokens["http"].split(".")[0]
        with runtime.source_slot(source_id), runtime.source_slot(source_id):
            assert (
                client.post("/api/v1/ingest/events", json=[event()], headers=headers).status_code
                == 429
            )
        assert (
            client.post("/api/v1/ingest/events", json=[event()], headers=headers).status_code == 200
        )
        for _ in range(runtime.settings.max_api_concurrency):
            runtime.slots.acquire()
        try:
            assert client.get("/health/live").status_code == 503
        finally:
            for _ in range(runtime.settings.max_api_concurrency):
                runtime.slots.release()
        assert client.get("/health/live").status_code == 200


def test_body_timeout_is_bounded(runtime: Runtime) -> None:
    import asyncio

    limited = Runtime(runtime.store, Settings(body_timeout_seconds=0.01))
    app = create_app(runtime.store.engine, ingestion=True, runtime=limited)
    messages = []

    async def receive():
        await asyncio.sleep(1)
        return {"type": "http.request", "body": b"", "more_body": True}

    async def send(message):
        messages.append(message)

    scope = {
        "type": "http",
        "asgi": {"version": "3.0"},
        "http_version": "1.1",
        "scheme": "http",
        "method": "POST",
        "path": "/api/v1/ingest/events",
        "raw_path": b"/api/v1/ingest/events",
        "query_string": b"",
        "headers": [
            (b"content-type", b"application/json"),
            (b"authorization", f"Bearer {runtime.test_tokens['http']}".encode()),
        ],
        "server": ("localhost", 8001),
        "client": ("127.0.0.1", 12345),
    }
    asyncio.run(app(scope, receive, send))
    assert messages[0]["status"] == 408
    assert all(usage.active == 0 for usage in limited.usage.values())


def test_oversized_array_is_rejected_before_item_validation(runtime: Runtime) -> None:
    with TestClient(create_app(runtime.store.engine, ingestion=True, runtime=runtime)) as client:
        result = client.post(
            "/api/v1/ingest/events",
            json=[{}] * 501,
            headers={"Authorization": f"Bearer {runtime.test_tokens['http']}"},
        )
        assert result.status_code == 422
        assert result.json()["error"]["code"] == "batch_size"


def test_nonstandard_json_and_duplicate_keys_are_rejected(runtime: Runtime) -> None:
    with TestClient(create_app(runtime.store.engine, ingestion=True, runtime=runtime)) as client:
        for body in ('[{"source":"http","source":"ssh"}]', "[NaN]", "[Infinity]"):
            result = client.post(
                "/api/v1/ingest/events",
                content=body,
                headers={
                    "Authorization": f"Bearer {runtime.test_tokens['http']}",
                    "Content-Type": "application/json",
                },
            )
            assert result.status_code == 422
