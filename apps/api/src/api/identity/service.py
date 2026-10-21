"""Invite-only permanent accounts and database-backed credential/session lifecycle."""

import hashlib
from datetime import datetime, timedelta
from uuid import UUID

from fastapi import HTTPException
from sqlalchemy import case, delete, func, select, update
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from api.db.models import CustomerAccount, User
from api.identity.context import RequestContext
from api.identity.models import (
    AuthAttemptWindow,
    AuthCredential,
    AuthInvitation,
    AuthSession,
    SupportAccountGrant,
)
from api.identity.schemas import (
    AuthUser,
    InvitationCreated,
    InvitationRequest,
    LoginRequest,
    RedeemInvitation,
    SessionCreated,
    SessionView,
)
from api.identity.security import (
    DUMMY_HASH,
    auth_mode,
    hash_password,
    new_token,
    token_hash,
    verify_password,
)

INVITATION_LIFETIME = timedelta(hours=24)
SESSION_LIFETIME = timedelta(hours=8)
LOGIN_WINDOW = timedelta(minutes=10)
LOGIN_ATTEMPTS = 10


def require_password_mode() -> None:
    if auth_mode() != "password":
        raise HTTPException(503, "Account authentication is not enabled")


async def clock(session: AsyncSession) -> datetime:
    now = await session.scalar(select(func.clock_timestamp()))
    assert isinstance(now, datetime)
    return now


async def check_accounts(session: AsyncSession, accounts: list[UUID]) -> None:
    found = set(
        await session.scalars(
            select(CustomerAccount.id).where(CustomerAccount.id.in_(accounts))
        )
    )
    if found != set(accounts):
        raise HTTPException(422, "Customer account unavailable")


async def issue_session(
    session: AsyncSession, user: User, credential: AuthCredential
) -> SessionCreated:
    token = new_token("session")
    expires_at = await clock(session) + SESSION_LIFETIME
    session.add(
        AuthSession(
            user_id=user.id,
            token_hash=token_hash("session", token),
            user_type=user.user_type,
            customer_account_id=user.customer_account_id,
            is_admin=credential.is_admin,
            expires_at=expires_at,
        )
    )
    return SessionCreated(
        access_token=token,
        expires_at=expires_at,
        user=AuthUser.model_validate(
            {
                "id": user.id,
                "email": credential.email,
                "name": user.name,
                "last_name": user.last_name,
                "user_type": user.user_type,
                "customer_account_id": user.customer_account_id,
                "is_admin": credential.is_admin,
            }
        ),
    )


async def login(session: AsyncSession, body: LoginRequest) -> SessionCreated:
    require_password_mode()
    # Reserve each attempt durably before expensive verification. Unknown emails
    # use the same counter and dummy hash, without revealing account existence.
    now = await clock(session)
    key = hashlib.sha256(f"resolveflow:login:{body.email}".encode()).hexdigest()
    expired = AuthAttemptWindow.started_at <= now - LOGIN_WINDOW
    count = await session.scalar(
        insert(AuthAttemptWindow)
        .values(
            key_hash=key,
            started_at=now,
            attempts=1,
        )
        .on_conflict_do_update(
            index_elements=["key_hash"],
            set_={
                "started_at": case((expired, now), else_=AuthAttemptWindow.started_at),
                "attempts": case((expired, 1), else_=AuthAttemptWindow.attempts + 1),
            },
        )
        .returning(AuthAttemptWindow.attempts)
    )
    await session.commit()
    if count is None or count > LOGIN_ATTEMPTS:
        raise HTTPException(
            429, "Sign-in temporarily unavailable", headers={"Retry-After": "600"}
        )
    credential = await session.scalar(
        select(AuthCredential).where(AuthCredential.email == str(body.email))
    )
    valid = await verify_password(
        body.password.get_secret_value(),
        credential.password_hash if credential else DUMMY_HASH,
    )
    if credential is None or not valid or credential.disabled_at is not None:
        raise HTTPException(
            401, "Invalid credentials", headers={"WWW-Authenticate": "Bearer"}
        )
    # Verification runs in a worker thread. Re-read enablement and the password
    # hash so a concurrent disable/reset cannot issue a session using stale data.
    verified_hash = credential.password_hash
    await session.refresh(credential, with_for_update=True)
    user = await session.get(User, credential.user_id)
    if (
        credential.disabled_at is not None
        or credential.password_hash != verified_hash
        or user is None
    ):
        raise HTTPException(401, "Invalid credentials")
    result = await issue_session(session, user, credential)
    await session.commit()
    return result


async def create_invitation(
    session: AsyncSession, actor: RequestContext, body: InvitationRequest
) -> InvitationCreated:
    require_password_mode()
    if not actor.is_admin or actor.user_type != "support":
        raise HTTPException(403, "Administrator access required")
    await check_accounts(
        session,
        ([body.customer_account_id] if body.customer_account_id else [])
        + body.support_account_ids,
    )
    token = new_token("invitation")
    invitation = AuthInvitation(
        user_type=body.user_type,
        customer_account_id=body.customer_account_id,
        support_account_ids=[str(account) for account in body.support_account_ids],
        token_hash=token_hash("invitation", token),
        created_by=actor.user_id,
        expires_at=await clock(session) + INVITATION_LIFETIME,
    )
    session.add(invitation)
    await session.commit()
    return InvitationCreated(
        invitation_id=invitation.id, token=token, expires_at=invitation.expires_at
    )


async def redeem(session: AsyncSession, body: RedeemInvitation) -> SessionCreated:
    require_password_mode()
    invitation = await session.scalar(
        select(AuthInvitation)
        .where(
            AuthInvitation.token_hash
            == token_hash("invitation", body.token.get_secret_value())
        )
        .with_for_update()
    )
    now = await clock(session)
    if (
        invitation is None
        or invitation.consumed_at
        or invitation.revoked_at
        or invitation.expires_at <= now
    ):
        raise HTTPException(400, "Invitation unavailable")
    issuer = await session.get(
        AuthCredential, invitation.created_by, with_for_update=True
    )
    if issuer is None or not issuer.is_admin or issuer.disabled_at:
        raise HTTPException(400, "Invitation unavailable")
    if await session.scalar(
        select(AuthCredential.user_id).where(AuthCredential.email == str(body.email))
    ):
        raise HTTPException(409, "Email unavailable")
    accounts = [UUID(value) for value in invitation.support_account_ids]
    await check_accounts(session, accounts)
    user = User(
        user_type=invitation.user_type,
        customer_account_id=invitation.customer_account_id,
        name=body.name,
        last_name=body.last_name,
    )
    session.add(user)
    await session.flush()
    credential = AuthCredential(
        user_id=user.id,
        email=str(body.email),
        password_hash=await hash_password(body.password.get_secret_value()),
        is_admin=False,
    )
    session.add(credential)
    await session.flush()
    session.add_all(
        SupportAccountGrant(user_id=user.id, customer_account_id=account)
        for account in accounts
    )
    consumed_at = await clock(session)
    invitation.consumed_at = consumed_at
    if invitation.expires_at <= consumed_at:
        raise HTTPException(400, "Invitation unavailable")
    result = await issue_session(session, user, credential)
    try:
        await session.commit()
    except IntegrityError:
        await session.rollback()
        raise HTTPException(400, "Invitation unavailable") from None
    return result


async def logout(session: AsyncSession, token: str) -> None:
    require_password_mode()
    await session.execute(
        update(AuthSession)
        .where(
            AuthSession.token_hash == token_hash("session", token),
            AuthSession.revoked_at.is_(None),
        )
        .values(revoked_at=func.clock_timestamp())
    )
    await session.commit()


async def revoke_invitation(session: AsyncSession, invitation_id: UUID) -> None:
    invitation = await session.get(AuthInvitation, invitation_id)
    if invitation is None:
        raise HTTPException(404, "Invitation unavailable")
    if invitation.revoked_at is None:
        invitation.revoked_at = await clock(session)
    await session.commit()


async def disable_user(session: AsyncSession, user_id: UUID) -> None:
    credential = await session.get(AuthCredential, user_id, with_for_update=True)
    if credential is None:
        raise HTTPException(404, "User unavailable")
    if credential.is_admin:
        raise HTTPException(403, "Administrator accounts are managed locally")
    credential.disabled_at = credential.disabled_at or await clock(session)
    await session.execute(
        update(AuthSession)
        .where(AuthSession.user_id == user_id, AuthSession.revoked_at.is_(None))
        .values(revoked_at=func.clock_timestamp())
    )
    await session.commit()


async def replace_support_grants(
    session: AsyncSession, user_id: UUID, accounts: list[UUID]
) -> None:
    user = await session.get(User, user_id, with_for_update=True)
    if user is None:
        raise HTTPException(404, "User unavailable")
    if user.user_type != "support":
        raise HTTPException(403, "Support role required")
    await check_accounts(session, accounts)
    await session.execute(
        delete(SupportAccountGrant).where(SupportAccountGrant.user_id == user_id)
    )
    session.add_all(
        SupportAccountGrant(user_id=user_id, customer_account_id=account)
        for account in accounts
    )
    await session.commit()


async def session_view(
    session: AsyncSession, token: str, context: RequestContext
) -> SessionView:
    """Return metadata for the already authenticated session without its bearer."""
    row = (
        await session.execute(
            select(AuthSession, AuthCredential, User)
            .join(AuthCredential, AuthCredential.user_id == AuthSession.user_id)
            .join(User, User.id == AuthCredential.user_id)
            .where(
                AuthSession.token_hash == token_hash("session", token),
                AuthSession.user_id == context.user_id,
                AuthSession.revoked_at.is_(None),
                AuthSession.expires_at > func.clock_timestamp(),
                AuthCredential.disabled_at.is_(None),
                AuthSession.user_type == User.user_type,
                AuthSession.customer_account_id.is_not_distinct_from(
                    User.customer_account_id
                ),
                AuthSession.is_admin == AuthCredential.is_admin,
            )
        )
    ).one_or_none()
    if row is None:
        raise HTTPException(401, "Invalid identity")
    saved, credential, user = row
    return SessionView(
        expires_at=saved.expires_at,
        user=AuthUser(
            id=user.id,
            email=credential.email,
            name=user.name,
            last_name=user.last_name,
            user_type=context.user_type,
            customer_account_id=context.customer_account_id,
            is_admin=context.is_admin,
        ),
    )
