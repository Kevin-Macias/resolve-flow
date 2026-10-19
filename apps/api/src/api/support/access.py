"""Current simulated account grants for explicitly reviewed support operations."""

import os
from uuid import UUID

from fastapi import HTTPException
from pydantic import TypeAdapter, ValidationError
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from api.identity.dependencies import resolve_request_context
from api.identity.models import SupportAccountGrant
from api.identity.security import auth_mode

ACCOUNT_GRANTS = TypeAdapter(dict[UUID, list[UUID]])


async def allowed_accounts(token: str, session: AsyncSession) -> list[UUID]:
    context = await resolve_request_context(token, session)
    if context.user_type != "support":
        raise HTTPException(403, "Not permitted")
    # Malformed configuration must never broaden access.
    if auth_mode() == "password":
        return list(
            await session.scalars(
                select(SupportAccountGrant.customer_account_id).where(
                    SupportAccountGrant.user_id == context.user_id
                )
            )
        )
    try:
        return ACCOUNT_GRANTS.validate_json(
            os.getenv("DEMO_SUPPORT_ACCOUNT_IDS", "{}"), strict=True
        ).get(context.user_id, [])
    except ValidationError:
        raise HTTPException(503, "Access configuration unavailable") from None
