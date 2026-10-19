"""Authenticate transport, then call the guarded support approval service."""

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.security import HTTPAuthorizationCredentials

from api.errors import ErrorResponse
from api.identity.dependencies import bearer
from api.support.action_schemas import ProposalRequest, SupportAction
from api.support.actions import SupportActions
from api.workflow.approval import ApprovalReply

router = APIRouter(
    prefix="/support",
    tags=["support-actions"],
    responses={
        code: {"model": ErrorResponse} for code in (401, 403, 404, 409, 422, 503)
    },
)


def service(
    request: Request, credentials: HTTPAuthorizationCredentials | None
) -> tuple[SupportActions, str]:
    if credentials is None:
        raise HTTPException(401, "Identity required")
    actions: SupportActions | None = getattr(request.app.state, "support_actions", None)
    if actions is None:
        raise HTTPException(503, "Action unavailable")
    return actions, credentials.credentials


@router.get("/issue-reports/{report_id}/action", response_model=SupportAction)
async def read_action(
    report_id: UUID,
    request: Request,
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(bearer)],
) -> SupportAction:
    actions, token = service(request, credentials)
    try:
        return await actions.get(token, report_id)
    except HTTPException:
        raise
    except Exception:
        raise HTTPException(503, "Action unavailable") from None


@router.post("/issue-reports/{report_id}/proposal", response_model=SupportAction)
async def prepare_action(
    report_id: UUID,
    body: ProposalRequest,
    request: Request,
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(bearer)],
) -> SupportAction:
    actions, token = service(request, credentials)
    try:
        return await actions.prepare(token, report_id, body)
    except HTTPException:
        raise
    except Exception:
        raise HTTPException(503, "Action unavailable") from None


@router.post(
    "/issue-reports/{report_id}/runs/{run_id}/decision", response_model=SupportAction
)
async def decide_action(
    report_id: UUID,
    run_id: UUID,
    body: ApprovalReply,
    request: Request,
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(bearer)],
) -> SupportAction:
    actions, token = service(request, credentials)
    try:
        return await actions.decide(token, report_id, run_id, body)
    except HTTPException:
        raise
    except Exception:
        raise HTTPException(503, "Action unavailable") from None


@router.post(
    "/issue-reports/{report_id}/runs/{run_id}/recover-execution",
    response_model=SupportAction,
)
async def recover_execution(
    report_id: UUID,
    run_id: UUID,
    body: ApprovalReply,
    request: Request,
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(bearer)],
) -> SupportAction:
    actions, token = service(request, credentials)
    try:
        return await actions.recover(token, report_id, run_id, body)
    except HTTPException:
        raise
    except PermissionError:
        raise HTTPException(409, "No approved execution to recover") from None
    except Exception:
        raise HTTPException(503, "Execution recovery unavailable") from None
