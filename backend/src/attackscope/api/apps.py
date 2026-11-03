from typing import Literal

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from sqlalchemy import Engine
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.exc import TimeoutError as PoolTimeout
from starlette.exceptions import HTTPException

from attackscope.api.middleware import RequestGuard
from attackscope.api.routes import ingestion_router, read_router
from attackscope.api.runtime import Runtime
from attackscope.core.config import Settings
from attackscope.core.errors import ServiceError, error_response, service_error_handler
from attackscope.storage.migrations import schema_is_current
from attackscope.storage.store import Store


class Health(BaseModel):
    status: Literal["ok", "ready"]


def create_app(
    engine: Engine, *, ingestion: bool = False, runtime: Runtime | None = None
) -> FastAPI:
    app = FastAPI(
        title="AttackScope ingestion" if ingestion else "AttackScope read API",
        version="0.1.0",
        docs_url=None if ingestion else "/docs",
        redoc_url=None,
        openapi_url=None if ingestion else "/openapi.json",
    )

    @app.get("/health/live", response_model=Health)
    def live() -> Health:
        return Health(status="ok")

    @app.get("/health/ready", response_model=Health, responses={503: {"description": "Not ready"}})
    def ready() -> Health | JSONResponse:
        try:
            with engine.connect() as connection:
                current = schema_is_current(connection)
                wal = connection.exec_driver_sql("PRAGMA journal_mode").scalar() == "wal"
                foreign_keys = connection.exec_driver_sql("PRAGMA foreign_keys").scalar() == 1
                if current and wal and foreign_keys:
                    return Health(status="ready")
        except (SQLAlchemyError, OSError, RuntimeError):
            pass
        return JSONResponse(status_code=503, content={"error": {"code": "not_ready"}})

    runtime = runtime or Runtime(Store(engine), Settings())
    app.state.runtime = runtime
    app.add_middleware(RequestGuard, runtime=runtime, ingestion=ingestion)
    app.add_exception_handler(ServiceError, service_error_handler)

    async def invalid_request(request: Request, _: Exception) -> JSONResponse:
        return error_response(
            ServiceError(422, "invalid_request", "Invalid request parameters"),
            request.state.request_id,
        )

    async def unavailable(request: Request, _: Exception) -> JSONResponse:
        return error_response(
            ServiceError(503, "storage_unavailable", "Storage unavailable; retry later"),
            request.state.request_id,
        )

    async def http_error(request: Request, error: Exception) -> JSONResponse:
        assert isinstance(error, HTTPException)
        return error_response(
            ServiceError(error.status_code, "http_error", "Request not available"),
            request.state.request_id,
        )

    app.add_exception_handler(RequestValidationError, invalid_request)
    app.add_exception_handler(SQLAlchemyError, unavailable)
    app.add_exception_handler(PoolTimeout, unavailable)
    app.add_exception_handler(HTTPException, http_error)
    app.include_router(ingestion_router(runtime) if ingestion else read_router(runtime))
    return app
