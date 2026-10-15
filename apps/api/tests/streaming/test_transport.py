import asyncio
from pathlib import Path
from uuid import UUID, uuid4

import pytest
from fastapi import FastAPI, HTTPException, Request
from httpx import ASGITransport, AsyncClient
from starlette.responses import StreamingResponse

from api.errors import install_error_handlers
from api.streaming.transport import (
    CustomerSnapshot,
    StreamConfig,
    customer_stream,
    frame,
    validate_cursor,
)

RUN = UUID("11111111-1111-1111-1111-111111111111")
LIMITS = StreamConfig(
    poll_seconds=0.001, heartbeat_seconds=0.002, lifetime_seconds=0.05
)


@pytest.fixture
def anyio_backend() -> str:
    return "asyncio"


class Source:
    def __init__(self, snapshots: list[CustomerSnapshot], deny_at: int = 0):
        self.snapshots = snapshots
        self.checks = 0
        self.reads = 0
        self.deny_at = deny_at
        self.account = "account-a"
        self.owner_account = "account-a"
        self.active_report = True

    async def authorize(self, run_id: UUID) -> None:
        assert run_id == RUN
        self.checks += 1
        if (
            self.account != self.owner_account
            or not self.active_report
            or (self.deny_at and self.checks >= self.deny_at)
        ):
            raise HTTPException(404, "Not found")

    async def read(self, run_id: UUID) -> CustomerSnapshot:
        assert run_id == RUN
        snapshot = self.snapshots[min(self.reads, len(self.snapshots) - 1)]
        self.reads += 1
        return snapshot


def snap(revision: int = 1, *, terminal: bool = False) -> CustomerSnapshot:
    return CustomerSnapshot(
        run_id=RUN,
        revision=revision,
        progress="waiting_input" if terminal else "processing",
        customer_update="Please clarify café\nlocation" if terminal else None,
    )


def app_for(source: Source) -> FastAPI:
    app = FastAPI()
    install_error_handlers(app)

    async def stream(request: Request) -> StreamingResponse:
        # Deterministic identity adapter; no production route is registered.
        if request.headers.get("Authorization") != "Bearer customer-a":
            raise HTTPException(401, "Identity required")
        return await customer_stream(
            source, RUN, request.headers.get("Last-Event-ID"), LIMITS
        )

    app.add_api_route("/test-stream", stream, methods=["GET"])
    return app


async def get(source: Source, cursor: str | None = None, token: str = "customer-a"):
    headers = {"Authorization": f"Bearer {token}"}
    if cursor is not None:
        headers["Last-Event-ID"] = cursor
    async with AsyncClient(
        transport=ASGITransport(app=app_for(source)), base_url="http://test"
    ) as client:
        return await client.get("/test-stream", headers=headers)


@pytest.mark.anyio
async def test_http_snapshots_order_dedup_and_final_frame() -> None:
    source = Source([snap(), snap(), snap(3, terminal=True)])
    response = await get(source)
    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/event-stream")
    assert response.headers["cache-control"] == "no-store"
    assert response.headers["x-accel-buffering"] == "no"
    assert response.text.count("event: snapshot") == 2
    assert response.text.index(f"id: {RUN}:1") < response.text.index(f"id: {RUN}:3")
    assert response.text.index(f"id: {RUN}:3") < response.text.index(
        "event: stream_end"
    )
    assert "café\\nlocation" in response.text
    assert source.checks >= source.reads * 2


@pytest.mark.anyio
async def test_reconnect_returns_latest_without_replaying_history() -> None:
    source = Source([snap(4, terminal=True)])
    response = await get(source, f"{RUN}:1")
    assert f"id: {RUN}:4" in response.text
    assert source.reads == 1
    duplicate = await get(source, f"{RUN}:4")
    assert duplicate.text == response.text


@pytest.mark.anyio
@pytest.mark.parametrize(
    "cursor",
    [
        "unknown",
        f"{uuid4()}:1",
        f"{RUN}:2",
        f"{RUN}:01",
        f"{RUN}:0",
        f"{RUN}:1\x00",
    ],
)
async def test_bad_cursor_fails_before_headers(cursor: str) -> None:
    response = await get(Source([snap()]), cursor)
    assert response.status_code == 422
    assert response.json()["error"]["code"] == "validation_error"
    assert "event: snapshot" not in response.text


@pytest.mark.anyio
async def test_missing_identity_and_denied_account_expose_no_snapshots() -> None:
    source = Source([snap(terminal=True)], deny_at=1)
    response = await get(source, token="other-account")
    assert response.status_code == 401
    assert source.reads == 0
    response = await get(source)
    assert response.status_code == 404
    assert source.reads == 0


@pytest.mark.anyio
@pytest.mark.parametrize("deny_at", [3, 5])
async def test_revocation_before_send_never_exposes_new_snapshot(deny_at: int) -> None:
    response = await get(Source([snap(), snap(2, terminal=True)], deny_at=deny_at))
    assert "access_lost" in response.text
    assert f"id: {RUN}:2" not in response.text
    if deny_at == 3:
        assert "event: snapshot" not in response.text
    assert "stream_end" not in response.text


@pytest.mark.anyio
@pytest.mark.parametrize(
    "next_snapshot",
    [snap(2).model_copy(update={"customer_update": "changed"}), snap(1)],
)
async def test_conflicting_or_decreasing_revision_sanitized(
    next_snapshot: CustomerSnapshot,
) -> None:
    response = await get(Source([snap(2), next_snapshot]))
    assert '"reason":"unavailable"' in response.text
    assert response.text.count("event: snapshot") == 1
    assert "stream_end" not in response.text


@pytest.mark.anyio
async def test_heartbeat_rollover_is_not_terminal() -> None:
    response = await get(Source([snap()]))
    assert ": heartbeat\n\n" in response.text
    assert response.text.count("event: snapshot") == 1
    assert "stream_end" not in response.text


@pytest.mark.anyio
async def test_stalled_source_times_out_before_open() -> None:
    class Stalled(Source):
        async def read(self, run_id: UUID) -> CustomerSnapshot:
            await asyncio.sleep(10)
            return snap()

    with pytest.raises(HTTPException) as caught:
        await customer_stream(
            Stalled([snap()]), RUN, config=StreamConfig(source_timeout_seconds=0.001)
        )
    assert caught.value.status_code == 503


def test_framing_and_limits() -> None:
    with pytest.raises(HTTPException):
        validate_cursor(f"{RUN}:١", snap())
    with pytest.raises(ValueError):
        frame("snapshot", {}, "bad\nid")
    with pytest.raises(ValueError):
        StreamConfig(lifetime_seconds=0)
    with pytest.raises(ValueError):
        StreamConfig(poll_seconds=float("nan"))


@pytest.mark.anyio
@pytest.mark.parametrize("archived", [False, True])
async def test_authorized_source_denies_wrong_account_or_archived_report(
    archived: bool,
) -> None:
    source = Source([snap(terminal=True)])
    if archived:
        source.active_report = False
    else:
        source.account = "account-b"
    response = await get(source)
    assert response.status_code == 404
    assert source.reads == 0
    assert "customer_update" not in response.text


@pytest.mark.anyio
async def test_cancelled_source_read_propagates_and_releases_resources() -> None:
    started = asyncio.Event()
    released = asyncio.Event()

    class Waiting(Source):
        async def read(self, run_id: UUID) -> CustomerSnapshot:
            if self.reads == 0:
                self.reads += 1
                return snap()
            started.set()
            try:
                await asyncio.Event().wait()
            finally:
                released.set()
            return snap()

    response = await customer_stream(Waiting([snap()]), RUN, config=LIMITS)
    iterator = aiter(response.body_iterator)
    await anext(iterator)

    async def read_next() -> None:
        await anext(iterator)

    task = asyncio.create_task(read_next())
    await asyncio.wait_for(started.wait(), 1)
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task
    assert released.is_set()


def test_python_frame_matches_shared_browser_fixture() -> None:
    fixture = (
        Path(__file__).resolve().parents[4]
        / "apps/web/src/features/workflow-stream/customer-snapshot.fixture.sse"
    )
    value = CustomerSnapshot(
        run_id=RUN,
        revision=7,
        progress="waiting_input",
        customer_update="café 🐈\nquestion",
    )
    expected = frame("snapshot", value.model_dump(mode="json"), value.event_id) + frame(
        "stream_end", {"version": 1, "reason": "waiting_input"}
    )
    assert fixture.read_bytes() == expected


@pytest.mark.anyio
@pytest.mark.parametrize(
    "progress", ["waiting_input", "stage_finished", "stage_failed"]
)
async def test_all_terminal_states_end_after_final_snapshot(progress: str) -> None:
    value = CustomerSnapshot.model_validate(
        {"run_id": RUN, "revision": 1, "progress": progress}
    )
    response = await get(Source([value]))
    assert response.text.index("event: snapshot") < response.text.index(
        "event: stream_end"
    )
    assert f'"reason":"{progress}"' in response.text


@pytest.mark.anyio
async def test_post_header_failure_is_sanitized() -> None:
    class Failing(Source):
        async def read(self, run_id: UUID) -> CustomerSnapshot:
            if self.reads:
                raise RuntimeError("private database credentials")
            self.reads += 1
            return snap()

    response = await get(Failing([snap()]))
    assert response.status_code == 200
    assert '"reason":"unavailable"' in response.text
    assert "private" not in response.text
    assert "stream_end" not in response.text
