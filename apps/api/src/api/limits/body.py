"""Read a bounded body before JSON parsing or any endpoint side effects."""

import asyncio

from starlette.types import ASGIApp, Message, Receive, Scope, Send

from api.errors import error_response

MAX_BODY_BYTES = 65_536
BODY_TIMEOUT_SECONDS = 10.0


class BodyLimitMiddleware:
    def __init__(
        self,
        app: ASGIApp,
        max_bytes: int = MAX_BODY_BYTES,
        timeout_seconds: float = BODY_TIMEOUT_SECONDS,
    ) -> None:
        self.app = app
        self.max_bytes = max_bytes
        self.timeout_seconds = timeout_seconds

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return
        lengths = [
            v for k, v in scope.get("headers", []) if k.lower() == b"content-length"
        ]
        if lengths and (
            len(lengths) != 1 or not lengths[0].isdigit() or len(lengths[0]) > 10
        ):
            await error_response(400, "Invalid Content-Length")(scope, receive, send)
            return
        if lengths and int(lengths[0]) > self.max_bytes:
            await error_response(413, "Request body exceeds 65536 bytes")(
                scope, receive, send
            )
            return
        body = bytearray()
        too_large = False
        try:
            async with asyncio.timeout(self.timeout_seconds):
                while True:
                    message = await receive()
                    if message["type"] == "http.disconnect":
                        return
                    chunk = message.get("body", b"")
                    if len(body) + len(chunk) > self.max_bytes:
                        too_large = True
                        break
                    body.extend(chunk)
                    if not message.get("more_body", False):
                        break
        except TimeoutError:
            await error_response(408, "Request body timed out")(scope, receive, send)
            return

        if too_large:
            await error_response(413, "Request body exceeds 65536 bytes")(
                scope, receive, send
            )
            return

        delivered = False

        async def replay() -> Message:
            nonlocal delivered
            if not delivered:
                delivered = True
                return {"type": "http.request", "body": bytes(body), "more_body": False}
            return await receive()

        await self.app(scope, replay, send)
