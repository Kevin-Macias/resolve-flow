"""Pure ASGI correlation covers streaming and never consumes payloads."""

import asyncio
from time import monotonic
from uuid import uuid4

from starlette.types import ASGIApp, Message, Receive, Scope, Send

from api.observability import Correlation, Failure, Outcome, context, emit, failure


class RequestLoggingMiddleware:
    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return
        request_id = uuid4()
        scope.setdefault("state", {})["request_id"] = request_id
        token = context.set(Correlation(request_id=request_id))
        started = monotonic()
        status: int | None = None
        complete = False
        disconnected = False
        outcome: Outcome = "success"
        code: Failure | None = None
        method = scope.get("method", "OTHER")
        if method not in ("GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS", "HEAD"):
            method = "OTHER"

        async def observed_receive() -> Message:
            nonlocal disconnected
            message = await receive()
            if message["type"] == "http.disconnect":
                disconnected = True
            return message

        async def observed_send(message: Message) -> None:
            nonlocal status, complete
            if message["type"] == "http.response.start":
                status = message["status"]
                message = dict(message)
                message["headers"] = [
                    (k, v)
                    for k, v in message.get("headers", [])
                    if k.lower() != b"x-request-id"
                ] + [(b"x-request-id", str(request_id).encode("ascii"))]
            await send(message)
            if message["type"] == "http.response.body" and not message.get(
                "more_body", False
            ):
                complete = True

        emit("request.started", method=method)
        try:
            await self.app(scope, observed_receive, observed_send)
            if disconnected and not complete:
                outcome = "disconnected"
            elif status is not None and status >= 400:
                outcome = "rejected" if status < 500 else "error"
        except (asyncio.CancelledError, Exception) as error:
            outcome, code = failure(error)
            if status is None and outcome != "cancelled":
                status = 500
            raise
        finally:
            try:
                route = getattr(scope.get("route"), "path", None) or "<unmatched>"
                emit(
                    "request.completed",
                    method=method,
                    route=route,
                    status_code=status,
                    outcome=outcome,
                    failure_code=code,
                    duration_ms=(monotonic() - started) * 1000,
                )
            finally:
                context.reset(token)
