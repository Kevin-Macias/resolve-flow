import json
import os
from typing import Annotated
from uuid import UUID

from fastapi import Depends, HTTPException
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.ext.asyncio import AsyncSession

from api.db.models import User
from api.db.session import get_session
from api.identity.context import RequestContext

bearer = HTTPBearer(auto_error=False)


async def get_request_context(
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(bearer)],
    session: Annotated[AsyncSession, Depends(get_session)],
) -> RequestContext:
    if credentials is None:
        raise HTTPException(status_code=401, detail="Identity Required")

    token_map: dict[str, str] = json.loads(os.getenv("DEMO_TOKEN_USER_IDS", "{}"))
    raw_user_id = token_map.get(credentials.credentials)
    if raw_user_id is None:
        raise HTTPException(status_code=401, detail="Invalid identity")

    try:
        user_id = UUID(raw_user_id)
    except ValueError as error:
        raise HTTPException(status_code=401, detail="Invalid identity") from error

    user = await session.get(User, user_id)
    if user is None:
        raise HTTPException(status_code=401, detail="Invalid identity")

    if user.user_type == "customer":
        if user.customer_account_id is None:
            raise HTTPException(status_code=403, detail="Invalid account membership")
        return RequestContext(user.id, "customer", user.customer_account_id)

    if user.user_type == "support":
        return RequestContext(user_id, "support", None)

    raise HTTPException(status_code=403, detail="Unsupported user type")
