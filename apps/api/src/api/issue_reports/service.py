from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from api.db.models import IssueReport, Service, User
from api.issue_reports.schemas import IssueReportResponse, IssueReportStatus
from api.services.schemas import Service as ServiceSchema
from api.user.schemas import User as UserSchema


async def full_issue_report_response(
    report: IssueReport, session: AsyncSession
) -> IssueReportResponse:
    submitter = await session.get(User, report.submitted_by_user_id)
    if submitter is None:
        raise HTTPException(status_code=500, detail="Issue report data is inconsistent")

    service = (
        await session.get(Service, report.affected_service_id)
        if report.affected_service_id is not None
        else None
    )

    return IssueReportResponse(
        id=report.id,
        customer_account_id=report.customer_account_id,
        description=report.description,
        affected_service=(
            ServiceSchema(code=service.code, label=service.label) if service else None
        ),
        status=IssueReportStatus(report.status),
        submitted_by=UserSchema(
            id=submitter.id, name=submitter.name, last_name=submitter.last_name
        ),
        created_at=report.created_at,
        updated_at=report.updated_at,
    )


async def get_service_from_code(
    service_code: str | None, session: AsyncSession
) -> Service | None:
    if service_code is not None:
        service = await session.scalar(
            select(Service).where(Service.code == service_code)
        )
        if service is None:
            raise HTTPException(status_code=422, detail="Unknown service code")
        return service
