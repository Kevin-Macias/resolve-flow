from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from api.db.models import IssueReport
from api.db.session import get_session
from api.identity.context import RequestContext
from api.identity.dependencies import get_request_context
from api.issue_reports.schemas import (
    IssueReportCreate,
    IssueReportResponse,
    IssueReportStatus,
    IssueReportUpdate,
)
from api.issue_reports.service import full_issue_report_response, get_service_from_code

router = APIRouter(prefix="/issue-reports", tags=["issue-reports"])

Context = Annotated[RequestContext, Depends(get_request_context)]
Session = Annotated[AsyncSession, Depends(get_session)]


@router.get("/", response_model=list[IssueReportResponse])
async def get_issue_reports_list(
    context: Context, session: Session
) -> list[IssueReportResponse]:
    if context.user_type != "customer" or context.customer_account_id is None:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN, detail="Not permitted"
        )

    reports = (
        await session.scalars(
            select(IssueReport).where(
                IssueReport.customer_account_id == context.customer_account_id,
                IssueReport.status != IssueReportStatus.DELETED,
            )
        )
    ).all()

    return [await full_issue_report_response(report, session) for report in reports]


@router.get("/{report_id}", response_model=IssueReportResponse)
async def get_issue_report(
    report_id: UUID, context: Context, session: Session
) -> IssueReportResponse:
    if context.user_type != "customer" or context.customer_account_id is None:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN, detail="Not permitted"
        )

    report = await session.scalar(
        select(IssueReport).where(
            IssueReport.id == report_id,
            IssueReport.customer_account_id == context.customer_account_id,
            IssueReport.status != IssueReportStatus.DELETED,
        )
    )

    if report is None:
        raise HTTPException(status_code=404, detail="Issue report not found")

    return await full_issue_report_response(report, session)


@router.post(
    "/", response_model=IssueReportResponse, status_code=status.HTTP_201_CREATED
)
async def create_issue_report(
    create_report_dto: IssueReportCreate, context: Context, session: Session
) -> IssueReportResponse:
    if context.user_type != "customer" or context.customer_account_id is None:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN, detail="Not permitted"
        )

    service = await get_service_from_code(
        create_report_dto.affected_service_code, session
    )

    report = IssueReport(
        description=create_report_dto.description,
        affected_service_id=service.id if service else None,
        customer_account_id=context.customer_account_id,
        submitted_by_user_id=context.user_id,
        status=IssueReportStatus.SUBMITTED,
    )

    session.add(report)
    await session.commit()
    await session.refresh(report)
    return await full_issue_report_response(report, session)


@router.patch(
    "/{report_id}", response_model=IssueReportResponse, status_code=status.HTTP_200_OK
)
async def update_report(
    report_id: UUID,
    update_report_dto: IssueReportUpdate,
    context: Context,
    session: Session,
):
    if context.user_type != "customer" or context.customer_account_id is None:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN, detail="Not permitted"
        )

    report = await session.scalar(
        select(IssueReport).where(
            IssueReport.id == report_id,
            IssueReport.customer_account_id == context.customer_account_id,
            IssueReport.status != IssueReportStatus.DELETED,
        )
    )

    if report is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND)

    if "affected_service_code" in update_report_dto.model_fields_set:
        if update_report_dto.affected_service_code is None:
            report.affected_service_id = None
        else:
            service = await get_service_from_code(
                update_report_dto.affected_service_code, session
            )

            if service is not None:
                report.affected_service_id = service.id

    await session.commit()
    await session.refresh(report)
    return await full_issue_report_response(report, session)


@router.delete("/{report_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_report(report_id: UUID, context: Context, session: Session) -> None:
    if context.user_type != "customer" or context.customer_account_id is None:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN, detail="Not permitted"
        )

    report = await session.scalar(
        select(IssueReport).where(
            IssueReport.id == report_id,
            IssueReport.customer_account_id == context.customer_account_id,
            IssueReport.status != IssueReportStatus.DELETED,
        )
    )

    if report is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND)

    report.status = IssueReportStatus.DELETED

    await session.commit()
    await session.refresh(report)
