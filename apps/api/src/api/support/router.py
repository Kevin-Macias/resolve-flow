from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from fastapi.security import HTTPAuthorizationCredentials
from psycopg import Error as PostgresError
from sqlalchemy.exc import SQLAlchemyError

from api.accounting.reader import AccountingReader, History
from api.errors import ErrorResponse
from api.identity.dependencies import bearer
from api.support.evidence import SupportEvidenceService
from api.support.evidence_schemas import AnalysisRequest, SupportEvidence
from api.support.metrics import SupportMetrics, SupportMetricsReader
from api.support.reports import SupportReportState, SupportReportStates
from api.support.runs import SupportRun, SupportRuns

router = APIRouter(
    prefix="/support",
    tags=["support-runs"],
    responses={code: {"model": ErrorResponse} for code in (401, 403, 404, 422, 503)},
)


def evidence_service(request: Request) -> SupportEvidenceService:
    service: SupportEvidenceService | None = getattr(
        request.app.state, "support_evidence", None
    )
    if service is None:
        raise HTTPException(503, "Evidence unavailable")
    return service


@router.get(
    "/issue-reports/{report_id}/evidence-analysis", response_model=SupportEvidence
)
async def get_evidence(
    report_id: UUID,
    request: Request,
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(bearer)],
) -> SupportEvidence:
    if credentials is None:
        raise HTTPException(401, "Identity required")
    try:
        return await evidence_service(request).get(credentials.credentials, report_id)
    except HTTPException:
        raise
    except Exception:
        raise HTTPException(503, "Evidence unavailable") from None


@router.post(
    "/issue-reports/{report_id}/evidence-analyses",
    response_model=SupportEvidence,
    responses={409: {"model": ErrorResponse}},
)
async def create_evidence(
    report_id: UUID,
    body: AnalysisRequest,
    request: Request,
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(bearer)],
) -> SupportEvidence:
    if credentials is None:
        raise HTTPException(401, "Identity required")
    try:
        return await evidence_service(request).create(
            credentials.credentials, report_id, body.operation_id
        )
    except HTTPException:
        raise
    except Exception:
        raise HTTPException(503, "Evidence unavailable") from None


@router.get("/issue-reports/{report_id}/state", response_model=SupportReportState)
async def get_report_state(
    report_id: UUID,
    request: Request,
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(bearer)],
) -> SupportReportState:
    if credentials is None:
        raise HTTPException(401, "Identity required")
    reader: SupportReportStates | None = getattr(
        request.app.state, "support_report_states", None
    )
    if reader is None:
        raise HTTPException(503, "Report unavailable")
    try:
        return await reader.get(credentials.credentials, report_id)
    except (SQLAlchemyError, TimeoutError, ValueError, RuntimeError):
        raise HTTPException(503, "Report unavailable") from None


@router.get("/issue-reports/{report_id}/intake-run", response_model=SupportRun)
async def get_run(
    report_id: UUID,
    request: Request,
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(bearer)],
) -> SupportRun:
    if credentials is None:
        raise HTTPException(401, "Identity required")
    reader: SupportRuns | None = getattr(request.app.state, "support_runs", None)
    if reader is None:
        raise HTTPException(503, "Run unavailable")
    try:
        return await reader.get(credentials.credentials, report_id)
    except (SQLAlchemyError, PostgresError, TimeoutError, ValueError, RuntimeError):
        raise HTTPException(503, "Run unavailable") from None


@router.get(
    "/issue-reports/{report_id}/execution-metrics", response_model=SupportMetrics
)
async def get_metrics(
    report_id: UUID,
    request: Request,
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(bearer)],
) -> SupportMetrics:
    if credentials is None:
        raise HTTPException(401, "Identity required")
    reader: SupportMetricsReader | None = getattr(
        request.app.state, "support_metrics", None
    )
    if reader is None:
        raise HTTPException(503, "Metrics unavailable")
    try:
        return await reader.get(credentials.credentials, report_id)
    except HTTPException:
        raise
    except Exception:
        raise HTTPException(503, "Metrics unavailable") from None


@router.get("/issue-reports/{report_id}/model-accounting", response_model=History)
async def model_accounting(
    report_id: UUID,
    request: Request,
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(bearer)],
    offset: Annotated[int, Query(ge=0, le=9007199254740991)] = 0,
) -> History:
    if credentials is None:
        raise HTTPException(401, "Identity required")
    sessions = getattr(request.app.state, "session_factory", None)
    if sessions is None:
        raise HTTPException(503, "Accounting unavailable")
    try:
        return await AccountingReader(sessions).get(
            credentials.credentials, report_id, offset
        )
    except HTTPException:
        raise
    except Exception:
        raise HTTPException(503, "Accounting unavailable") from None
