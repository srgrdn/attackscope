import logging
from urllib.parse import urlsplit
from uuid import uuid4

from starlette.types import ASGIApp, Message, Receive, Scope, Send

from attackscope.api.runtime import Runtime
from attackscope.core.errors import ServiceError, error_response

logger = logging.getLogger("attackscope.requests")


class RequestGuard:
    def __init__(self, app: ASGIApp, runtime: Runtime, ingestion: bool) -> None:
        self.app = app
        self.runtime = runtime
        self.ingestion = ingestion

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return
        request_id = str(uuid4())
        scope.setdefault("state", {})["request_id"] = request_id

        started = False

        async def headers(message: Message) -> None:
            nonlocal started
            if message["type"] == "http.response.start":
                started = True
                outgoing = message.setdefault("headers", [])
                present = {key.lower() for key, _ in outgoing}
                for key, value in (
                    (b"x-request-id", request_id.encode()),
                    (b"cache-control", b"no-store"),
                    (b"x-content-type-options", b"nosniff"),
                ):
                    if key not in present:
                        outgoing.append((key, value))
            await send(message)

        async def reject(status: int, code: str, message: str) -> None:
            await error_response(ServiceError(status, code, message), request_id)(
                scope, receive, headers
            )

        if len(scope.get("query_string", b"")) > 8192:
            await reject(422, "query_size", "Query string is too large")
            return
        if not self.ingestion:
            for key, value in scope["headers"]:
                if key == b"origin":
                    try:
                        origin = urlsplit(value.decode("ascii"))
                        allowed = (
                            origin.scheme in ("http", "https")
                            and origin.hostname in ("localhost", "127.0.0.1", "::1")
                            and origin.username is None
                        )
                    except (ValueError, UnicodeError):
                        allowed = False
                    if not allowed:
                        await reject(403, "origin", "Origin is not permitted")
                        return
        if not self.runtime.slots.acquire(blocking=False):
            await reject(503, "api_busy", "Service is busy; retry later")
            return
        try:
            await self.app(scope, receive, headers)
        except Exception as error:
            logger.error("request_failed request_id=%s type=%s", request_id, type(error).__name__)
            if started:
                raise RuntimeError("Response stream aborted") from None
            await reject(500, "internal_error", "Request failed")
        finally:
            self.runtime.slots.release()
