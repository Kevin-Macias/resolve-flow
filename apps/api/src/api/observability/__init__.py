"""Metadata-only operational events; importing this module never configures output."""

import asyncio
import logging
from collections.abc import Generator
from contextlib import contextmanager
from contextvars import ContextVar
from dataclasses import dataclass
from datetime import UTC, datetime
from time import monotonic
from typing import Literal, cast
from uuid import UUID

from fastapi import HTTPException
from pydantic import BaseModel, ConfigDict, Field

from api.accounting.errors import AccountingUnavailable

type Component = Literal[
    "intake", "approval", "execution", "evidence", "extraction", "analysis", "embedding"
]
type Outcome = Literal[
    "success",
    "error",
    "timeout",
    "cancelled",
    "disconnected",
    "rejected",
    "reused",
    "unknown",
]
type Failure = Literal[
    "unexpected",
    "denied",
    "conflict",
    "unavailable",
    "timeout",
    "cancelled",
    "provider",
    "invalid_output",
    "refusal",
    "tool_unknown",
    "accounting_unavailable",
]
type Stage = Literal["run", "model", "provider", "tool", "execution"]
type EventName = Literal[
    "request.started",
    "request.completed",
    "run.started",
    "run.completed",
    "model.started",
    "model.completed",
    "provider.started",
    "provider.completed",
    "tool.started",
    "tool.completed",
    "execution.started",
    "execution.completed",
    "execution.receipt_reused",
    "execution.intent_ready",
    "execution.destination_committed",
    "execution.result_committed",
    "database.initialize.started",
    "database.initialize.completed",
    "api.error",
    "runtime.message",
    "runtime.error",
]


class Correlation(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid", strict=True)
    request_id: UUID | None = None
    run_id: UUID | None = None
    operation_id: UUID | None = None
    execution_id: UUID | None = None
    call_id: UUID | None = None


class Event(Correlation):
    timestamp: datetime
    level: Literal["INFO", "WARNING", "ERROR"]
    event: EventName
    component: Component | None = None
    outcome: Outcome | None = None
    failure_code: Failure | None = None
    method: (
        Literal["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS", "HEAD", "OTHER"]
        | None
    ) = None
    route: str | None = Field(default=None, max_length=256)
    status_code: int | None = Field(default=None, ge=100, le=599)
    attempt: int | None = Field(default=None, ge=1)
    duration_ms: float | None = Field(default=None, ge=0, allow_inf_nan=False)


context: ContextVar[Correlation] = ContextVar("log_correlation", default=Correlation())  # noqa: B039 - frozen model, no mutable fields
logger = logging.getLogger("resolveflow.events")
logger.addHandler(logging.NullHandler())
logger.propagate = False


@contextmanager
def bind(**identifiers: UUID | None) -> Generator[None]:
    values = context.get().model_dump()
    values.update(identifiers)
    token = context.set(Correlation.model_validate(values))
    try:
        yield
    finally:
        context.reset(token)


def attach(**identifiers: UUID | None) -> None:
    """Remember authorized IDs for this HTTP request; offline calls stay unbound."""
    current = context.get()
    if current.request_id is not None:
        values = current.model_dump()
        values.update(identifiers)
        context.set(Correlation.model_validate(values))


def emit(event: EventName, **fields: object) -> None:
    # A closed schema prevents accidental serialization of payloads/exceptions.
    level = (
        "WARNING"
        if fields.get("failure_code") in ("cancelled", "denied", "conflict")
        else "ERROR"
        if fields.get("failure_code")
        or fields.get("outcome") in ("error", "timeout", "unknown")
        else "INFO"
    )
    record = Event.model_validate(
        {
            **context.get().model_dump(),
            **fields,
            "timestamp": datetime.now(UTC),
            "level": level,
            "event": event,
        }
    )
    logger.log(
        {"ERROR": logging.ERROR, "WARNING": logging.WARNING, "INFO": logging.INFO}[
            record.level
        ],
        "",
        extra={"safe_event": record},
    )


@dataclass
class Span:
    outcome: Outcome = "success"
    failure_code: Failure | None = None


def failure(error: BaseException) -> tuple[Outcome, Failure]:
    if isinstance(error, AccountingUnavailable):
        return "error", "accounting_unavailable"
    if isinstance(error, asyncio.CancelledError):
        return "cancelled", "cancelled"
    if isinstance(error, TimeoutError):
        return "timeout", "timeout"
    if isinstance(error, HTTPException):
        if error.status_code in (401, 403, 404):
            return "rejected", "denied"
        if error.status_code == 409:
            return "rejected", "conflict"
        if error.status_code == 503:
            return "error", "unavailable"
    return "error", "unexpected"


@contextmanager
def trace(
    stage: Stage,
    *,
    component: Component,
    attempt: int | None = None,
    error_code: Failure | None = None,
    **identifiers: UUID | None,
) -> Generator[Span]:
    with bind(**identifiers):
        started = monotonic()
        span = Span()
        start_event = cast(EventName, f"{stage}.started")
        end_event = cast(EventName, f"{stage}.completed")
        emit(start_event, component=component, attempt=attempt)
        try:
            yield span
        except BaseException as error:
            if span.failure_code is None or isinstance(error, asyncio.CancelledError):
                span.outcome, span.failure_code = failure(error)
                if (
                    error_code is not None
                    and span.outcome == "error"
                    and span.failure_code != "accounting_unavailable"
                ):
                    span.failure_code = error_code
                    if error_code == "tool_unknown":
                        span.outcome = "unknown"
            raise
        finally:
            emit(
                end_event,
                component=component,
                attempt=attempt,
                outcome=span.outcome,
                failure_code=span.failure_code,
                duration_ms=(monotonic() - started) * 1000,
            )
