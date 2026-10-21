"""Invite-only enrollment, repeat login, and explicitly authorized administration."""

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Response
from fastapi.security import HTTPAuthorizationCredentials
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from api.db.session import get_session
from api.errors import ErrorResponse
from api.identity import service
from api.identity.context import RequestContext
from api.identity.dependencies import bearer, get_request_context
from api.identity.schemas import (
    InvitationCreated,
    InvitationRequest,
    LoginRequest,
    RedeemInvitation,
    SessionCreated,
    SessionView,
    SupportGrantsRequest,
)
from api.limits.http import limit_authenticated

router = APIRouter(
    tags=["authentication"],
    responses={
        code: {"model": ErrorResponse}
        for code in (400, 401, 403, 404, 409, 422, 429, 503)
    },
)
Session = Annotated[AsyncSession, Depends(get_session)]


async def require_admin(
    context: Annotated[RequestContext, Depends(get_request_context)],
    _limits: Annotated[None, Depends(limit_authenticated)],
) -> RequestContext:
    service.require_password_mode()
    if not context.is_admin or context.user_type != "support":
        raise HTTPException(403, "Administrator access required")
    return context


Admin = Annotated[RequestContext, Depends(require_admin)]


def no_cache(response: Response) -> None:
    response.headers["Cache-Control"] = "no-store"
    response.headers["Pragma"] = "no-cache"


@router.get("/auth/session", response_model=SessionView)
async def current_session(
    response: Response,
    session: Session,
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(bearer)],
    context: Annotated[RequestContext, Depends(get_request_context)],
    _limits: Annotated[None, Depends(limit_authenticated)],
) -> SessionView:
    service.require_password_mode()
    no_cache(response)
    assert credentials is not None
    return await service.session_view(session, credentials.credentials, context)


@router.post("/auth/login", response_model=SessionCreated)
async def login(
    body: LoginRequest, response: Response, session: Session
) -> SessionCreated:
    no_cache(response)
    return await service.login(session, body)


@router.post("/auth/invitations/redeem", response_model=SessionCreated, status_code=201)
async def redeem(
    body: RedeemInvitation, response: Response, session: Session
) -> SessionCreated:
    no_cache(response)
    try:
        return await service.redeem(session, body)
    except IntegrityError:
        await session.rollback()
        raise HTTPException(400, "Invitation unavailable") from None


@router.post("/auth/logout", status_code=204)
async def logout(
    session: Session,
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(bearer)],
) -> None:
    if credentials is None:
        raise HTTPException(401, "Identity required")
    await service.logout(session, credentials.credentials)


@router.post("/admin/invitations", response_model=InvitationCreated, status_code=201)
async def create_invitation(
    body: InvitationRequest, response: Response, session: Session, admin: Admin
) -> InvitationCreated:
    no_cache(response)
    return await service.create_invitation(session, admin, body)


@router.delete("/admin/invitations/{invitation_id}", status_code=204)
async def revoke_invitation(
    invitation_id: UUID, session: Session, admin: Admin
) -> None:
    await service.revoke_invitation(session, invitation_id)


@router.delete("/admin/users/{user_id}/access", status_code=204)
async def disable_user(user_id: UUID, session: Session, admin: Admin) -> None:
    await service.disable_user(session, user_id)


@router.put("/admin/users/{user_id}/support-accounts", status_code=204)
async def replace_support_grants(
    user_id: UUID, body: SupportGrantsRequest, session: Session, admin: Admin
) -> None:
    await service.replace_support_grants(session, user_id, body.account_ids)
