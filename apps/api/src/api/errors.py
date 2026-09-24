import logging
from collections.abc import Mapping

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from starlette.exceptions import HTTPException as StarletteHTTPException

logger = logging.getLogger(__name__)

ERROR_CODES = {
    401: "unauthorized",
    403: "forbidden",
    404: "not_found",
    405: "method_not_allowed",
    409: "conflict",
    422: "validation_error",
    503: "service_unavailable",
    500: "internal_error",
}

ERROR_MESSAGES = {
    401: "Unauthorized",
    403: "Forbidden",
    404: "Not found",
    405: "Method not allowed",
    409: "Conflict",
    422: "Request validation failed",
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
        logger.error("Unhandled API error (%s)", type(_error).__name__)
        return error_response(500, ERROR_MESSAGES[500])

    app.add_exception_handler(StarletteHTTPException, handle_http_error)
    app.add_exception_handler(RequestValidationError, handle_validation_error)
    app.add_exception_handler(Exception, handle_unexpected_error)
