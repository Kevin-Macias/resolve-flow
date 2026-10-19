"""Trusted local account bootstrap and password recovery, never public signup."""

from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from api.db.models import User
from api.identity.models import AuthCredential, AuthSession
from api.identity.security import hash_password


async def bootstrap_admin(
    session: AsyncSession, email: str, name: str, last_name: str, password: str
) -> User:
    if await session.scalar(
        select(AuthCredential.user_id).where(AuthCredential.email == email)
    ):
        raise ValueError("An account already exists; use local password recovery")
    user = User(
        user_type="support", customer_account_id=None, name=name, last_name=last_name
    )
    session.add(user)
    await session.flush()
    session.add(
        AuthCredential(
            user_id=user.id,
            email=email,
            password_hash=await hash_password(password),
            is_admin=True,
        )
    )
    await session.commit()
    return user


async def reset_password(session: AsyncSession, email: str, password: str) -> None:
    credential = await session.scalar(
        select(AuthCredential).where(AuthCredential.email == email).with_for_update()
    )
    if credential is None:
        raise ValueError("Account unavailable")
    credential.password_hash = await hash_password(password)
    await session.execute(
        update(AuthSession)
        .where(
            AuthSession.user_id == credential.user_id, AuthSession.revoked_at.is_(None)
        )
        .values(revoked_at=func.clock_timestamp())
    )
    await session.commit()
