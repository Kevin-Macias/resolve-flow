from decimal import Decimal, localcontext
from typing import Annotated, Literal
from uuid import UUID

from pydantic import Field, StrictBool
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from api.accounting.contracts import Attempt, Count
from api.accounting.models import ModelCallAttempt
from api.intake.models import IntakeRun
from api.support.evidence_models import EvidenceAnalysis
from api.support.reports import SupportReportStates
from api.workflow.actions import ImmutableContract


class Totals(ImmutableContract):
    attempts: Count
    retries: Count
    live_attempts: Count
    offline_attempts: Count
    unfinished_attempts: Count
    missing_live_usage: Count
    missing_live_cost: Count
    known_live_input_tokens: Count
    known_live_output_tokens: Count
    known_live_total_tokens: Count
    known_live_cost_usd: Annotated[Decimal, Field(ge=0)]
    known_live_provider_ms: Annotated[float, Field(ge=0, allow_inf_nan=False)]
    missing_live_latency: Count
    coverage_complete: StrictBool
    cost_complete: StrictBool


class ScopeTotals(ImmutableContract):
    scope_type: Literal["intake", "evidence"]
    scope_id: UUID
    totals: Totals


class History(ImmutableContract):
    version: Literal[1] = 1
    report_id: UUID
    totals: Totals
    scopes: tuple[ScopeTotals, ...]
    offset: Count
    next_offset: Count | None
    attempts: tuple[Attempt, ...]


def totals(records: list[Attempt], complete: bool) -> Totals:
    live = [item for item in records if item.provider_mode == "live"]
    usages = [item.usage for item in live if item.usage is not None]
    with localcontext() as ctx:
        ctx.prec = 60
        cost = sum(
            (item.cost.usd for item in live if item.cost is not None), Decimal(0)
        )
    return Totals(
        attempts=len(records),
        retries=sum(item.attempt > 1 for item in records),
        live_attempts=len(live),
        offline_attempts=len(records) - len(live),
        unfinished_attempts=sum(item.outcome == "started" for item in records),
        missing_live_usage=sum(item.usage is None for item in live),
        missing_live_cost=sum(item.cost is None for item in live),
        known_live_input_tokens=sum(item.input_tokens for item in usages),
        known_live_output_tokens=sum(item.output_tokens for item in usages),
        known_live_total_tokens=sum(item.total_tokens for item in usages),
        known_live_cost_usd=cost,
        known_live_provider_ms=sum(
            item.latency_ms for item in live if item.latency_ms is not None
        ),
        missing_live_latency=sum(item.latency_ms is None for item in live),
        coverage_complete=complete,
        cost_complete=complete
        and bool(live)
        and all(item.cost is not None for item in live),
    )


class AccountingReader:
    def __init__(self, sessions: async_sessionmaker[AsyncSession]):
        self.sessions = sessions
        self.reports = SupportReportStates(sessions)

    async def get(self, token: str, report_id: UUID, offset: int = 0) -> History:
        report = await self.reports.authorized_report(token, report_id)
        async with self.sessions() as session:
            runs = list(
                await session.scalars(
                    select(IntakeRun).where(IntakeRun.report_id == report_id)
                )
            )
            analyses = list(
                await session.scalars(
                    select(EvidenceAnalysis).where(
                        EvidenceAnalysis.report_id == report_id
                    )
                )
            )
            scopes = {("intake", item.id): item.accounting_version for item in runs}
            scopes.update(
                {("evidence", item.id): item.accounting_version for item in analyses}
            )
            rows = list(
                await session.scalars(
                    select(ModelCallAttempt)
                    .where(ModelCallAttempt.report_id == report_id)
                    .order_by(ModelCallAttempt.created_at, ModelCallAttempt.id)
                )
            )
        records: list[Attempt] = []
        for row in rows:
            record = Attempt.model_validate(row.record)
            if (
                row.customer_account_id != report.customer_account_id
                or (record.scope_type, record.scope_id) not in scopes
                or (
                    record.id,
                    record.call_id,
                    record.attempt,
                    record.scope_type,
                    record.scope_id,
                    record.operation_id,
                )
                != (
                    row.id,
                    row.call_id,
                    row.attempt,
                    row.scope_type,
                    row.scope_id,
                    row.operation_id,
                )
            ):
                raise ValueError("Invalid accounting binding")
            records.append(record)
        current = await self.reports.authorized_report(token, report_id)
        if current.customer_account_id != report.customer_account_id:
            raise ValueError("Report ownership changed")
        return History(
            report_id=report_id,
            totals=totals(records, all(version == 1 for version in scopes.values())),
            scopes=tuple(
                ScopeTotals(
                    scope_type="intake" if kind == "intake" else "evidence",
                    scope_id=identity,
                    totals=totals(
                        [
                            record
                            for record in records
                            if record.scope_type == kind and record.scope_id == identity
                        ],
                        version == 1,
                    ),
                )
                for (kind, identity), version in scopes.items()
            ),
            offset=offset,
            next_offset=offset + 50 if offset + 50 < len(records) else None,
            attempts=tuple(records[offset : offset + 50]),
        )
