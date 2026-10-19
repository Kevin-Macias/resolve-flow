import os
from typing import Annotated
from uuid import UUID

from fastapi import Depends, HTTPException
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from pydantic import TypeAdapter, ValidationError
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from api.db.models import User
from api.db.session import get_session
from api.identity.context import RequestContext
from api.identity.models import AuthCredential, AuthSession
from api.identity.security import auth_mode, token_hash

bearer = HTTPBearer(auto_error=False)


async def get_request_context(
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(bearer)],
    session: Annotated[AsyncSession, Depends(get_session)],
) -> RequestContext:
    if credentials is None:
        raise HTTPException(status_code=401, detail="Identity Required")

    return await resolve_request_context(credentials.credentials, session)


async def resolve_request_context(token: str, session: AsyncSession) -> RequestContext:
    is_admin = False
    if auth_mode() == "demo":
        try:
            token_map = TypeAdapter(dict[str, UUID]).validate_json(
                os.getenv("DEMO_TOKEN_USER_IDS", "{}"), strict=True
            )
        except ValidationError:
            raise HTTPException(503, "Authentication unavailable") from None
        user_id = token_map.get(token)
        user = await session.get(User, user_id) if user_id else None
    else:
        row = (
            await session.execute(
                select(AuthSession, AuthCredential, User)
                .join(AuthCredential, AuthCredential.user_id == AuthSession.user_id)
                .join(User, User.id == AuthCredential.user_id)
                .where(
                    AuthSession.token_hash == token_hash("session", token),
                    AuthSession.revoked_at.is_(None),
                    AuthSession.expires_at > func.clock_timestamp(),
                    AuthCredential.disabled_at.is_(None),
                )
            )
        ).one_or_none()
        user = None
        if row is not None:
            saved, credential, current = row
            if (
                saved.user_type == current.user_type
                and saved.customer_account_id == current.customer_account_id
                and saved.is_admin == credential.is_admin
            ):
                user, is_admin = current, credential.is_admin
    if user is None:
        raise HTTPException(status_code=401, detail="Invalid identity")

    if user.user_type == "customer":
        if user.customer_account_id is None:
            raise HTTPException(status_code=403, detail="Invalid account membership")
        if is_admin:
            raise HTTPException(403, "Invalid administrator role")
        return RequestContext(user.id, "customer", user.customer_account_id)

    if user.user_type == "support":
        return RequestContext(user.id, "support", None, is_admin)

    raise HTTPException(status_code=403, detail="Unsupported user type")
