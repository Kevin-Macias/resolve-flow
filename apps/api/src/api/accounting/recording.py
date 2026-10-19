import asyncio
import hashlib
import os
from collections.abc import Awaitable, Callable, Generator
from contextlib import contextmanager
from contextvars import ContextVar
from dataclasses import dataclass
from datetime import UTC, datetime
from time import monotonic
from typing import Literal
from uuid import UUID, uuid4

from openai import APITimeoutError
from pydantic import BaseModel, ValidationError
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from api.accounting.contracts import Attempt, Mode, Outcome, Pricing, Usage, estimate
from api.accounting.errors import AccountingUnavailable
from api.accounting.models import ModelCallAttempt
from api.extraction.provider import (
    LLMProvider,
    ProviderError,
    ProviderFailureKind,
    ProviderResult,
)
from api.observability import context as log_context
from api.observability import trace


@dataclass(frozen=True)
class Scope:
    report_id: UUID
    account_id: UUID
    scope_type: Literal["intake", "evidence"]
    scope_id: UUID
    operation_id: UUID
    mode: Mode


class Recorder:
    def __init__(self, sessions: async_sessionmaker[AsyncSession], scope: Scope):
        self.sessions = sessions
        self.scope = scope
        raw = os.getenv("MODEL_PRICING")
        try:
            self.pricing = (
                Pricing.model_validate_json(raw)
                if raw and scope.mode == "live"
                else None
            )
        except ValidationError:
            raise AccountingUnavailable("Pricing configuration unavailable") from None

    async def start(
        self,
        component: Literal["extraction", "analysis", "embedding"],
        model: str,
        prompt_id: str | None,
        prompt_version: str | None,
        attempt: int,
        *,
        independent: bool = False,
    ) -> Attempt:
        context = log_context.get()
        try:
            record = Attempt(
                id=uuid4(),
                call_id=uuid4() if independent else context.call_id or uuid4(),
                parent_call_id=context.call_id if independent else None,
                request_id=context.request_id,
                scope_type=self.scope.scope_type,
                scope_id=self.scope.scope_id,
                operation_id=self.scope.operation_id,
                component=component,
                provider_mode=self.scope.mode,
                configured_model=model,
                prompt_id=prompt_id,
                prompt_version=prompt_version,
                attempt=attempt,
                started_at=datetime.now(UTC),
                pricing=self.pricing,
            )
            data = record.model_dump(mode="json")
            data["pricing"] = (
                self.pricing.model_dump(mode="json") if self.pricing else None
            )
            async with asyncio.timeout(5), self.sessions() as session:
                if self.pricing is not None:
                    key = int.from_bytes(
                        hashlib.sha256(
                            f"resolveflow:pricing:{self.pricing.version}".encode()
                        ).digest()[:8],
                        "big",
                        signed=True,
                    )
                    await session.execute(
                        text("SELECT pg_advisory_xact_lock(:key)"), {"key": key}
                    )
                    previous = await session.scalar(
                        select(ModelCallAttempt)
                        .where(
                            ModelCallAttempt.record["pricing"]["version"].astext
                            == self.pricing.version
                        )
                        .limit(1)
                    )
                    if previous is not None and previous.record.get(
                        "pricing"
                    ) != self.pricing.model_dump(mode="json"):
                        raise ValueError("A changed pricing card needs a new version")
                session.add(
                    ModelCallAttempt(
                        id=record.id,
                        report_id=self.scope.report_id,
                        customer_account_id=self.scope.account_id,
                        scope_type=self.scope.scope_type,
                        scope_id=self.scope.scope_id,
                        operation_id=self.scope.operation_id,
                        call_id=record.call_id,
                        attempt=record.attempt,
                        record=data,
                    )
                )
                await session.commit()
            return record
        except Exception:
            raise AccountingUnavailable(
                "Accounting start unavailable; provider was not dispatched"
            ) from None

    async def finish(
        self,
        record: Attempt,
        outcome: Outcome,
        duration: float,
        result: ProviderResult | None,
    ) -> None:
        usage = None
        invalid = False
        if result is not None and result.usage is not None:
            try:
                usage = Usage(
                    input_tokens=result.usage.input_tokens,
                    output_tokens=result.usage.output_tokens,
                    total_tokens=result.usage.total_tokens,
                    cached_input_tokens=result.cached_input_tokens,
                )
            except ValidationError:
                invalid = True
        model = (
            result.resolved_model
            if result and result.resolved_model
            else record.configured_model
        )
        cost, reason = estimate(self.pricing, model, usage, self.scope.mode)
        values = record.model_dump()
        values["pricing"] = self.pricing
        values.update(
            outcome=outcome,
            finished_at=datetime.now(UTC),
            latency_ms=duration,
            usage=usage,
            resolved_model=result.resolved_model if result else None,
            cost=cost,
            cost_status="invalid_usage" if invalid else reason,
        )
        try:
            completed = Attempt.model_validate(values)
            async with asyncio.timeout(5), self.sessions() as session:
                saved = await session.scalar(
                    select(ModelCallAttempt)
                    .where(ModelCallAttempt.id == record.id)
                    .with_for_update()
                )
                if (
                    saved is None
                    or saved.report_id != self.scope.report_id
                    or saved.call_id != record.call_id
                ):
                    raise ValueError("Accounting binding changed")
                if saved.record["outcome"] != "started":
                    raise ValueError("Attempt already completed")
                data = completed.model_dump(mode="json")
                data["pricing"] = (
                    self.pricing.model_dump(mode="json") if self.pricing else None
                )
                saved.record = data
                await session.commit()
        except Exception:
            raise AccountingUnavailable(
                "Accounting completion could not be confirmed"
            ) from None

    async def call(
        self,
        invoke: Callable[[], Awaitable[ProviderResult]],
        component: Literal["extraction", "analysis", "embedding"],
        model: str,
        prompt_id: str | None,
        prompt_version: str | None,
        attempt: int = 1,
        *,
        independent: bool = False,
    ) -> ProviderResult:
        record = await self.start(
            component,
            model,
            prompt_id,
            prompt_version,
            attempt,
            independent=independent,
        )
        started = monotonic()
        try:
            if independent:
                with trace(
                    "provider",
                    component=component,
                    call_id=record.call_id,
                    attempt=attempt,
                    error_code="provider",
                ):
                    result = await invoke()
            else:
                result = await invoke()
        except BaseException as error:
            outcome: Outcome = (
                "cancelled"
                if isinstance(error, asyncio.CancelledError)
                else "timeout"
                if isinstance(error, (TimeoutError, APITimeoutError))
                or (
                    isinstance(error, ProviderError)
                    and error.kind == ProviderFailureKind.TIMEOUT
                )
                else "provider_error"
            )
            reported = None
            if isinstance(error, ProviderError) and error.usage is not None:
                reported = ProviderResult(
                    usage=error.usage,
                    resolved_model=error.resolved_model,
                    cached_input_tokens=error.cached_input_tokens,
                )
            try:
                await self.finish(
                    record, outcome, (monotonic() - started) * 1000, reported
                )
            except (AccountingUnavailable, asyncio.CancelledError):
                if not isinstance(error, asyncio.CancelledError):
                    raise
            raise
        await self.finish(
            record,
            "refused" if result.refusal is not None else "response_received",
            (monotonic() - started) * 1000,
            result,
        )
        return result


active: ContextVar[Recorder | None] = ContextVar("model_accounting", default=None)


@contextmanager
def recording(
    sessions: async_sessionmaker[AsyncSession], scope: Scope
) -> Generator[None]:
    token = active.set(Recorder(sessions, scope))
    try:
        yield
    finally:
        active.reset(token)


async def generate(
    provider: LLMProvider,
    instructions: str,
    text: str,
    schema: type[BaseModel],
    *,
    component: Literal["extraction", "analysis"],
    prompt_id: str,
    prompt_version: str,
    attempt: int = 1,
    timeout_seconds: float | None = None,
) -> ProviderResult:
    recorder = active.get()

    async def invoke() -> ProviderResult:
        async with asyncio.timeout(timeout_seconds):
            return await provider.generate(instructions, text, schema)

    if recorder is None:
        return await invoke()
    return await recorder.call(
        invoke, component, provider.settings.model, prompt_id, prompt_version, attempt
    )
