"""SSE framing over an injected source, with no graph execution dependency."""

import asyncio
import json
import time
from collections.abc import AsyncIterator
from dataclasses import dataclass
from typing import Literal, Protocol
from uuid import UUID

from fastapi import HTTPException
from pydantic import BaseModel, ConfigDict, Field
from starlette.responses import StreamingResponse

Progress = Literal["processing", "waiting_input", "stage_finished", "stage_failed"]
EndReason = Literal["waiting_input", "stage_finished", "stage_failed"]
TERMINAL: dict[Progress, EndReason] = {
    "waiting_input": "waiting_input",
    "stage_finished": "stage_finished",
    "stage_failed": "stage_failed",
}
MAX_REVISION = 9_007_199_254_740_991  # JavaScript's largest exact integer.


class CustomerSnapshot(BaseModel):
    """Closed projection. Adapters must supply only authorized customer text."""

    model_config = ConfigDict(
        frozen=True,
        extra="forbid",
        strict=True,
        json_schema_serialization_defaults_required=True,
    )
    version: Literal[1] = 1
    run_id: UUID
    revision: int = Field(ge=1, le=MAX_REVISION)
    progress: Progress
    customer_update: str | None = Field(default=None, max_length=2000)

    @property
    def event_id(self) -> str:
        return f"{self.run_id}:{self.revision}"


class SnapshotSource(Protocol):
    """Every operation opens/closes its own short-lived storage resources.

    authorize revalidates identity, account, and active report/run binding.
    read returns a committed customer projection, never invokes the workflow.
    Denials raise HTTPException(401/403/404); failures must not include data.
    """

    async def authorize(self, run_id: UUID) -> None: ...

    async def read(self, run_id: UUID) -> CustomerSnapshot: ...


@dataclass(frozen=True)
class StreamConfig:
    poll_seconds: float = 1
    heartbeat_seconds: float = 15
    lifetime_seconds: float = 60
    source_timeout_seconds: float = 5

    def __post_init__(self) -> None:
        if not all(
            0 < value < float("inf")
            for value in (
                self.poll_seconds,
                self.heartbeat_seconds,
                self.lifetime_seconds,
                self.source_timeout_seconds,
            )
        ):
            raise ValueError("Stream limits must be finite and positive")


DEFAULT_CONFIG = StreamConfig()


def frame(event: str, data: dict[str, object], event_id: str | None = None) -> bytes:
    # Callers supply closed event names and application-generated IDs only.
    if event not in {"snapshot", "stream_end", "stream_error"}:
        raise ValueError("Unknown event")
    if event_id is not None and any(char in event_id for char in "\r\n\x00"):
        raise ValueError("Invalid event ID")
    prefix = f"id: {event_id}\n" if event_id is not None else ""
    payload = json.dumps(data, ensure_ascii=False, separators=(",", ":"))
    return f"{prefix}event: {event}\ndata: {payload}\n\n".encode()


def validate_cursor(cursor: str | None, snapshot: CustomerSnapshot) -> None:
    if cursor is None:
        return
    prefix = f"{snapshot.run_id}:"
    revision = cursor.removeprefix(prefix)
    if (
        not cursor.startswith(prefix)
        or not revision.isascii()
        or not revision.isdecimal()
        or revision.startswith("0")
        or len(revision) > 16
        or int(revision) > snapshot.revision
    ):
        raise HTTPException(422, "Invalid stream cursor")


async def customer_stream(
    source: SnapshotSource,
    run_id: UUID,
    cursor: str | None = None,
    config: StreamConfig = DEFAULT_CONFIG,
) -> StreamingResponse:
    """Preflight before headers; recheck access immediately before each send."""

    async def authorized_read() -> CustomerSnapshot:
        async with asyncio.timeout(config.source_timeout_seconds):
            await source.authorize(run_id)
            snapshot = await source.read(run_id)
            if snapshot.run_id != run_id:
                raise ValueError("Source returned a different run")
            return snapshot

    async def authorize_send() -> None:
        async with asyncio.timeout(config.source_timeout_seconds):
            await source.authorize(run_id)

    try:
        initial = await authorized_read()
        validate_cursor(cursor, initial)
        await authorize_send()
    except HTTPException:
        raise
    except Exception as error:
        raise HTTPException(503, "Service unavailable") from error

    async def events() -> AsyncIterator[bytes]:
        deadline = time.monotonic() + config.lifetime_seconds
        heartbeat_at = time.monotonic() + config.heartbeat_seconds
        current = initial
        previous: CustomerSnapshot | None = None
        try:
            while time.monotonic() < deadline:
                # Also recheck after the response has opened, before yielding data.
                await authorize_send()
                if previous is not None and (
                    current.revision < previous.revision
                    or (current.revision == previous.revision and current != previous)
                ):
                    raise ValueError("Source revision conflict")
                if current != previous:
                    yield frame(
                        "snapshot", current.model_dump(mode="json"), current.event_id
                    )
                    previous = current
                reason = TERMINAL.get(current.progress)
                if reason is not None:
                    await authorize_send()
                    yield frame("stream_end", {"version": 1, "reason": reason})
                    return
                if time.monotonic() >= heartbeat_at:
                    yield b": heartbeat\n\n"
                    heartbeat_at = time.monotonic() + config.heartbeat_seconds
                await asyncio.sleep(
                    min(config.poll_seconds, max(0, deadline - time.monotonic()))
                )
                if time.monotonic() >= deadline:
                    return  # Rollover is EOF, never business success.
                current = await authorized_read()
        except HTTPException as error:
            reason = (
                "access_lost" if error.status_code in {401, 403, 404} else "unavailable"
            )
            yield frame("stream_error", {"version": 1, "reason": reason})
        except Exception:
            yield frame("stream_error", {"version": 1, "reason": "unavailable"})
        # CancelledError propagates, releasing in-flight source operations.

    return StreamingResponse(
        events(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-store", "X-Accel-Buffering": "no"},
    )
