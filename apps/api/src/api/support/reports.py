"""Read current report state independently of intake and checkpoints."""

from typing import Literal, Self
from uuid import UUID

from fastapi import HTTPException
from pydantic import StrictBool, model_validator
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from api.db.models import IssueReport
from api.issue_reports.schemas import IssueReportStatus
from api.support.access import allowed_accounts
from api.workflow.actions import ImmutableContract


class SupportReportState(ImmutableContract):
    version: Literal[1] = 1
    report_id: UUID
    customer_account_id: UUID
    status: IssueReportStatus
    archived: StrictBool

    @model_validator(mode="after")
    def consistent_archive_state(self) -> Self:
        if self.archived != (self.status == IssueReportStatus.DELETED):
            raise ValueError("Inconsistent report archive state")
        return self


class SupportReportStates:
    def __init__(self, sessions: async_sessionmaker[AsyncSession]):
        self.sessions = sessions

    async def authorized_report(self, token: str, report_id: UUID) -> IssueReport:
        async with self.sessions() as session:
            accounts = await allowed_accounts(token, session)
            report = await session.scalar(
                select(IssueReport).where(
                    IssueReport.id == report_id,
                    IssueReport.customer_account_id.in_(accounts),
                )
            )
            if report is None:
                raise HTTPException(404, "Report unavailable")
            return report

    async def get(self, token: str, report_id: UUID) -> SupportReportState:
        report = await self.authorized_report(token, report_id)
        # Fresh session rechecks credentials, role, grants, and ownership.
        current = await self.authorized_report(token, report_id)
        if current.customer_account_id != report.customer_account_id:
            raise ValueError("Report ownership changed during read")
        return SupportReportState(
            report_id=current.id,
            customer_account_id=current.customer_account_id,
            status=IssueReportStatus(current.status),
            archived=current.status == IssueReportStatus.DELETED,
        )
