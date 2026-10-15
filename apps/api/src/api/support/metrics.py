"""Project the latest saved extraction record without executing workflow work."""

from dataclasses import asdict
from typing import Annotated, Literal, Self
from uuid import UUID

from pydantic import Field, StrictBool, StrictInt, StrictStr, model_validator
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from api.extraction.service import ExtractionCallRecord
from api.intake.models import IntakeRun
from api.support.reports import SupportReportStates
from api.support.runs import MODE, saved_events
from api.workflow.actions import ImmutableContract
from api.workflow.checkpoints import (
    CHECKPOINT_SCHEMA,
    open_checkpointer,
    workflow_config,
)

Count = Annotated[StrictInt, Field(ge=0)]
Identifier = Annotated[StrictStr, Field(min_length=1)]


class TokenUsage(ImmutableContract):
    input_tokens: Count
    output_tokens: Count
    total_tokens: Count


class ExtractionMetrics(ImmutableContract):
    model: Identifier
    prompt_id: Identifier
    prompt_version: Identifier
    attempts: Annotated[StrictInt, Field(ge=1)]
    usage: TokenUsage | None
    latency_ms: None = None
    estimated_cost: None = None


class SupportMetrics(ImmutableContract):
    version: Literal[1] = 1
    scope: Literal["latest_intake_extraction"] = "latest_intake_extraction"
    report_id: UUID
    run_id: UUID | None
    provider_mode: Literal["offline", "live"] | None
    operation_pending: StrictBool
    metrics: ExtractionMetrics | None

    @model_validator(mode="after")
    def consistent_run(self) -> Self:
        if self.run_id is None:
            if self.provider_mode is not None or self.operation_pending or self.metrics:
                raise ValueError("Metrics require a run")
        elif self.provider_mode is None:
            raise ValueError("Run requires provider mode")
        return self


def saved_metrics(record: object) -> ExtractionMetrics:
    if not isinstance(record, ExtractionCallRecord):
        raise ValueError("Invalid extraction record")
    return ExtractionMetrics(
        model=record.model_settings.model,
        prompt_id=record.prompt_id,
        prompt_version=record.prompt_version,
        attempts=record.attempts,
        usage=TokenUsage.model_validate(asdict(record.usage)) if record.usage else None,
    )


class SupportMetricsReader:
    def __init__(
        self,
        sessions: async_sessionmaker[AsyncSession],
        database_url: str,
        checkpoint_schema: str = CHECKPOINT_SCHEMA,
    ):
        self.sessions = sessions
        self.database_url = database_url
        self.checkpoint_schema = checkpoint_schema
        self.reports = SupportReportStates(sessions)

    async def binding(
        self, token: str, report_id: UUID
    ) -> tuple[UUID, IntakeRun | None]:
        report = await self.reports.authorized_report(token, report_id)
        async with self.sessions() as session:
            run = await session.scalar(
                select(IntakeRun).where(IntakeRun.report_id == report_id)
            )
        if run is not None and run.customer_account_id != report.customer_account_id:
            raise ValueError("Invalid report/run binding")
        return report.customer_account_id, run

    async def get(self, token: str, report_id: UUID) -> SupportMetrics:
        account, run = await self.binding(token, report_id)
        metrics = None
        if run is not None:
            async with open_checkpointer(
                self.database_url, self.checkpoint_schema
            ) as saver:
                saved = await saver.aget_tuple(workflow_config(run.id))
            if saved is not None:
                values = saved.checkpoint["channel_values"]
                saved_events(values, run.id, report_id)
                if "extraction_call" in values:
                    metrics = saved_metrics(values["extraction_call"])
        current_account, current = await self.binding(token, report_id)
        if current_account != account or (
            (current.id, current.provider_mode) if current else None
        ) != ((run.id, run.provider_mode) if run else None):
            raise ValueError("Metrics binding changed during read")
        return SupportMetrics(
            report_id=report_id,
            run_id=current.id if current else None,
            provider_mode=MODE.validate_python(current.provider_mode)
            if current
            else None,
            operation_pending=current.pending_operation_id is not None
            if current
            else False,
            metrics=metrics,
        )
