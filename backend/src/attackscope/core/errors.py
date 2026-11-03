from fastapi import Request
from fastapi.responses import JSONResponse


class ServiceError(Exception):
    def __init__(self, status: int, code: str, message: str) -> None:
        self.status = status
        self.code = code
        self.message = message
        super().__init__(code)


def error_response(error: ServiceError, request_id: str) -> JSONResponse:
    headers = {"Cache-Control": "no-store", "X-Request-ID": request_id}
    if error.status in (429, 503):
        headers["Retry-After"] = "1"
    if error.status == 401:
        headers["WWW-Authenticate"] = "Bearer"
    return JSONResponse(
        status_code=error.status,
        content={"error": {"code": error.code, "message": error.message, "request_id": request_id}},
        headers=headers,
    )


async def service_error_handler(request: Request, error: Exception) -> JSONResponse:
    assert isinstance(error, ServiceError)
    return error_response(error, request.state.request_id)
