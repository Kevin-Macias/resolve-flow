from collections.abc import AsyncGenerator
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from fastapi.security import HTTPAuthorizationCredentials
from psycopg import Error as PostgresError
from sqlalchemy.exc import SQLAlchemyError
from starlette.responses import StreamingResponse

from api.accounting.recording import AccountingUnavailable
from api.errors import ErrorResponse
from api.identity.dependencies import bearer
from api.intake.runtime import IntakeRuntime
from api.intake.schemas import (
    ClarificationRequest,
    CustomerRun,
    EmptyStart,
    RecoveryRequest,
)
from api.intake.service import IntakeService
from api.streaming.transport import customer_stream

router = APIRouter(
    tags=["customer-intake"],
    responses={
        code: {"model": ErrorResponse} for code in (401, 403, 404, 409, 422, 500, 503)
    },
)


async def get_intake_service(
    request: Request,
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(bearer)],
) -> AsyncGenerator[IntakeService]:
    if credentials is None:
        raise HTTPException(401, "Identity required")
    runtime: IntakeRuntime | None = getattr(request.app.state, "intake_runtime", None)
    if runtime is None:
        raise HTTPException(503, "Intake unavailable")
    try:
        yield IntakeService(runtime, credentials.credentials)
    except (
        AccountingUnavailable,
        SQLAlchemyError,
        PostgresError,
        TimeoutError,
    ) as error:
        raise HTTPException(503, "Intake unavailable") from error


Service = Annotated[IntakeService, Depends(get_intake_service)]


@router.post(
    "/issue-reports/{report_id}/intake-run",
    response_model=CustomerRun,
    status_code=201,
    responses={200: {"model": CustomerRun}},
)
async def start(
    report_id: UUID, body: EmptyStart, response: Response, service: Service
) -> CustomerRun:
    view, created = await service.start(report_id)
    response.status_code = 201 if created else 200
    return view


@router.get("/issue-reports/{report_id}/intake-run", response_model=CustomerRun)
async def for_report(report_id: UUID, service: Service) -> CustomerRun:
    return await service.for_report(report_id)


@router.get("/intake-runs/{run_id}", response_model=CustomerRun)
async def get(run_id: UUID, service: Service) -> CustomerRun:
    return await service.get(run_id)


@router.post("/intake-runs/{run_id}/clarification", response_model=CustomerRun)
async def clarify(
    run_id: UUID, body: ClarificationRequest, service: Service
) -> CustomerRun:
    return await service.clarify(run_id, body)


@router.post("/intake-runs/{run_id}/recover", response_model=CustomerRun)
async def recover(run_id: UUID, body: RecoveryRequest, service: Service) -> CustomerRun:
    return await service.recover(run_id, body.expected_revision)


@router.get(
    "/intake-runs/{run_id}/events",
    response_class=StreamingResponse,
    responses={200: {"content": {"text/event-stream": {"schema": {"type": "string"}}}}},
)
async def events(run_id: UUID, request: Request, service: Service) -> StreamingResponse:
    return await customer_stream(service, run_id, request.headers.get("Last-Event-ID"))
