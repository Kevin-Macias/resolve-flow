"""Read saved intake events without constructing or executing a graph."""

from collections.abc import Mapping
from typing import Literal
from uuid import UUID

from fastapi import HTTPException
from pydantic import TypeAdapter
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from api.db.models import IssueReport
from api.intake.models import IntakeRun
from api.support.access import allowed_accounts
from api.workflow.actions import ImmutableContract
from api.workflow.checkpoints import (
    CHECKPOINT_SCHEMA,
    open_checkpointer,
    workflow_config,
)
from api.workflow.timeline import ExecutionEvent, append_events

MODE: TypeAdapter[Literal["offline", "live"]] = TypeAdapter(Literal["offline", "live"])


def saved_events(
    values: Mapping[str, object], run_id: UUID, report_id: UUID
) -> list[ExecutionEvent]:
    if (
        values.get("workflow_run_id") != run_id
        or values.get("issue_report_id") != report_id
    ):
        raise ValueError("Inconsistent checkpoint binding")
    events = TypeAdapter(list[ExecutionEvent]).validate_python(
        values.get("timeline", [])
    )
    # Validate the saved order; do not repair, sort, or deduplicate it.
    validated = append_events([], events)
    if len(validated) != len(events) or any(
        event.workflow_run_id != run_id or event.stage != "intake" for event in events
    ):
        raise ValueError("Inconsistent intake timeline")
    return events


class SupportRun(ImmutableContract):
    version: Literal[1] = 1
    run_id: UUID
    report_id: UUID
    provider_mode: Literal["offline", "live"]
    simulated: bool
    operation_pending: bool
    timeline: tuple[ExecutionEvent, ...]


class SupportRuns:
    def __init__(
        self,
        sessions: async_sessionmaker[AsyncSession],
        database_url: str,
        checkpoint_schema: str = CHECKPOINT_SCHEMA,
    ):
        self.sessions = sessions
        self.database_url = database_url
        self.checkpoint_schema = checkpoint_schema

    async def authorized_run(self, token: str, report_id: UUID) -> IntakeRun:
        async with self.sessions() as session:
            accounts = await allowed_accounts(token, session)
            run = await session.scalar(
                select(IntakeRun)
                .join(IssueReport, IssueReport.id == IntakeRun.report_id)
                .where(
                    IssueReport.id == report_id,
                    IssueReport.customer_account_id.in_(accounts),
                    IntakeRun.customer_account_id == IssueReport.customer_account_id,
                )
            )
            if run is None:
                raise HTTPException(404, "Run unavailable")
            return run

    async def get(self, token: str, report_id: UUID) -> SupportRun:
        run = await self.authorized_run(token, report_id)
        async with open_checkpointer(
            self.database_url, self.checkpoint_schema
        ) as saver:
            saved = await saver.aget_tuple(workflow_config(run.id))
        events: list[ExecutionEvent] = []
        if saved is not None:
            events = saved_events(saved.checkpoint["channel_values"], run.id, report_id)
        # Fresh credentials, role, account grants, and report binding before return.
        current = await self.authorized_run(token, report_id)
        if current.id != run.id or current.provider_mode != run.provider_mode:
            raise ValueError("Run binding changed during read")
        return SupportRun(
            run_id=run.id,
            report_id=report_id,
            provider_mode=MODE.validate_python(run.provider_mode),
            simulated=run.provider_mode == "offline",
            operation_pending=current.pending_operation_id is not None,
            timeline=tuple(events),
        )
