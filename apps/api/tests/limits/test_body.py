"""Oversized or stalled bodies never reach endpoint work, including chunked input."""

import asyncio

import pytest
from starlette.types import Message, Receive, Scope, Send

from api.limits.body import BodyLimitMiddleware


@pytest.fixture
def anyio_backend() -> str:
    return "asyncio"


@pytest.mark.anyio
@pytest.mark.parametrize(
    ("headers", "chunks", "status"),
    [
        ([(b"content-length", b"9")], [b""], 413),
        ([], [b"1234", b"56789"], 413),
        ([(b"content-length", b"1")], [b"123456789"], 413),
        ([(b"content-length", b"bad")], [b"x"], 400),
        ([(b"content-length", b"1"), (b"content-length", b"1")], [b"x"], 400),
        ([], [b"1234", b"5678"], 200),
    ],
)
async def test_input_is_bounded_before_dispatch(
    headers: list[tuple[bytes, bytes]], chunks: list[bytes], status: int
) -> None:
    calls: list[bytes] = []
    sent: list[Message] = []
    scope: Scope = {"type": "http", "headers": headers}
    messages: list[Message] = [
        {"type": "http.request", "body": chunk, "more_body": i < len(chunks) - 1}
        for i, chunk in enumerate(chunks)
    ]

    async def receive() -> Message:
        return messages.pop(0)

    async def send(message: Message) -> None:
        sent.append(message)

    async def endpoint(scope: Scope, receive: Receive, send: Send) -> None:
        calls.append((await receive())["body"])
        await send({"type": "http.response.start", "status": 200, "headers": []})
        await send({"type": "http.response.body", "body": b"ok"})

    await BodyLimitMiddleware(endpoint, max_bytes=8)(scope, receive, send)
    assert sent[0]["status"] == status
    assert calls == ([b"12345678"] if status == 200 else [])


@pytest.mark.anyio
@pytest.mark.parametrize("disconnect", [False, True])
async def test_stalled_or_disconnected_body_never_dispatches(disconnect: bool) -> None:
    sent: list[Message] = []

    async def endpoint(scope: Scope, receive: Receive, send: Send) -> None:
        pytest.fail("Endpoint dispatched before a complete body")

    async def receive() -> Message:
        if disconnect:
            return {"type": "http.disconnect"}
        await asyncio.sleep(1)
        return {"type": "http.request", "body": b""}

    async def send(message: Message) -> None:
        sent.append(message)

    await BodyLimitMiddleware(endpoint, timeout_seconds=0.01)(
        {"type": "http", "headers": []}, receive, send
    )
    assert (sent[0]["status"] if sent else None) == (None if disconnect else 408)


@pytest.mark.anyio
async def test_app_rejection_keeps_cors_request_id_and_safe_error() -> None:
    from httpx import ASGITransport, AsyncClient

    from api.main import create_app

    async with AsyncClient(
        transport=ASGITransport(app=create_app()), base_url="http://test"
    ) as client:
        response = await client.post(
            "/issue-reports/",
            content=b"secret" * 12000,
            headers={"Origin": "http://localhost:3000"},
        )
    assert response.status_code == 413
    assert response.headers["access-control-allow-origin"] == "http://localhost:3000"
    assert response.headers["x-request-id"]
    assert response.json()["error"]["code"] == "payload_too_large"
    assert "secret" not in response.text
