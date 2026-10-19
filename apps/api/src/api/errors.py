from collections.abc import Mapping

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from starlette.exceptions import HTTPException as StarletteHTTPException

from api.observability import bind, emit

ERROR_CODES = {
    400: "bad_request",
    401: "unauthorized",
    403: "forbidden",
    404: "not_found",
    405: "method_not_allowed",
    408: "request_timeout",
    409: "conflict",
    413: "payload_too_large",
    422: "validation_error",
    429: "rate_limited",
    503: "service_unavailable",
    500: "internal_error",
}

ERROR_MESSAGES = {
    400: "Request could not be completed",
    401: "Unauthorized",
    403: "Forbidden",
    404: "Not found",
    405: "Method not allowed",
    408: "Request body timed out",
    409: "Conflict",
    413: "Request body exceeds 65536 bytes",
    422: "Request validation failed",
    429: "Too many requests",
    503: "Service unavailable",
    500: "Internal server error",
}


class ValidationDetail(BaseModel):
    location: list[str]
    code: str


class ApiError(BaseModel):
    code: str
    message: str
    details: list[ValidationDetail]


class ErrorResponse(BaseModel):
    error: ApiError


def error_response(
    status_code: int,
    message: str,
    details: list[dict[str, object]] | None = None,
    headers: Mapping[str, str] | None = None,
) -> JSONResponse:
    return JSONResponse(
        status_code=status_code,
        content={
            "error": {
                "code": ERROR_CODES.get(status_code, "http_error"),
                "message": message,
                "details": details if details is not None else [],
            }
        },
        headers=headers,
    )


def string_detail(value: object, default: str) -> str:
    return value if isinstance(value, str) else default


def install_error_handlers(app: FastAPI) -> None:
    async def handle_http_error(_request: Request, error: Exception) -> JSONResponse:
        assert isinstance(error, StarletteHTTPException)
        default = ERROR_MESSAGES.get(error.status_code, "Request failed")
        message = (
            string_detail(error.detail, default) if error.status_code < 500 else default
        )
        return error_response(error.status_code, message, headers=error.headers)

    async def handle_validation_error(
        _request: Request, error: Exception
    ) -> JSONResponse:
        assert isinstance(error, RequestValidationError)
        details: list[dict[str, object]] = [
            {
                "location": [str(part) for part in issue["loc"]],
                "code": issue["type"],
            }
            for issue in error.errors()
        ]
        return error_response(422, ERROR_MESSAGES[422], details)

    async def handle_unexpected_error(
        _request: Request, _error: Exception
    ) -> JSONResponse:
        request_id = getattr(_request.state, "request_id", None)
        with bind(request_id=request_id):
            emit("api.error", failure_code="unexpected", outcome="error")
        headers = {"X-Request-ID": str(request_id)} if request_id else None
        return error_response(500, ERROR_MESSAGES[500], headers=headers)

    app.add_exception_handler(StarletteHTTPException, handle_http_error)
    app.add_exception_handler(RequestValidationError, handle_validation_error)
    app.add_exception_handler(Exception, handle_unexpected_error)
