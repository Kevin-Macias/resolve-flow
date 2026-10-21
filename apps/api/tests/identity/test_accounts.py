"""Real bearer resolution and PostgreSQL invitation/session lifecycle tests."""

import asyncio
import os
from collections.abc import AsyncGenerator
from dataclasses import dataclass
from datetime import timedelta
from uuid import UUID, uuid4

import pytest
from httpx import ASGITransport, AsyncClient
from psycopg import AsyncConnection, sql
from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from api.db.models import Base, CustomerAccount, User
from api.identity.admin import bootstrap_admin, reset_password
from api.identity.models import AuthCredential, AuthInvitation, AuthSession
from api.identity.schemas import SessionCreated
from api.identity.service import LOGIN_ATTEMPTS
from api.main import create_app
from api.support.reports import SupportReportStates
from api.workflow.checkpoints import postgres_connection_url

PASSWORD = "Correct horse battery staple."


@dataclass
class Accounts:
    client: AsyncClient
    sessions: async_sessionmaker[AsyncSession]
    admin: dict[str, str]
    admin_id: UUID
    account: UUID
    foreign: UUID


@pytest.fixture
def anyio_backend() -> str:
    return "asyncio"


@pytest.fixture
async def accounts(monkeypatch: pytest.MonkeyPatch) -> AsyncGenerator[Accounts]:
    raw = os.getenv("TEST_DATABASE_URL")
    if not raw:
        pytest.skip("Set TEST_DATABASE_URL for account lifecycle tests")
    monkeypatch.setenv("AUTH_MODE", "password")
    url = postgres_connection_url(raw)
    schema = f"rf_auth_{uuid4().hex}"
    async with await AsyncConnection.connect(url, autocommit=True) as conn:
        await conn.execute("CREATE EXTENSION IF NOT EXISTS vector WITH SCHEMA public")
        await conn.execute(sql.SQL("CREATE SCHEMA {}").format(sql.Identifier(schema)))
    engine = create_async_engine(
        url.replace("postgresql://", "postgresql+psycopg://"),
        connect_args={"options": f"-csearch_path={schema},public"},
    )
    sessions = async_sessionmaker(engine, expire_on_commit=False)
    try:
        async with engine.begin() as conn:
            await conn.run_sync(
                lambda sync: Base.metadata.create_all(sync, checkfirst=False)
            )
        async with sessions() as session:
            a, b = CustomerAccount(name="A"), CustomerAccount(name="B")
            session.add_all([a, b])
            admin = await bootstrap_admin(
                session, "admin@example.com", "Local", "Admin", PASSWORD
            )
        app = create_app()
        app.state.session_factory = sessions
        app.state.support_report_states = SupportReportStates(sessions)
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as client:
            response = await client.post(
                "/auth/login", json={"email": "ADMIN@example.com", "password": PASSWORD}
            )
            assert response.status_code == 200, response.text
            yield Accounts(
                client,
                sessions,
                {"Authorization": f"Bearer {response.json()['access_token']}"},
                admin.id,
                a.id,
                b.id,
            )
    finally:
        await engine.dispose()
        async with await AsyncConnection.connect(url, autocommit=True) as conn:
            await conn.execute(
                sql.SQL("DROP SCHEMA {} CASCADE").format(sql.Identifier(schema))
            )


async def invite(e: Accounts, *, support: bool = False) -> dict[str, object]:
    response = await e.client.post(
        "/admin/invitations",
        headers=e.admin,
        json={
            "user_type": "support" if support else "customer",
            "customer_account_id": None if support else str(e.account),
            "support_account_ids": [str(e.account)] if support else [],
        },
    )
    assert response.status_code == 201, response.text
    assert response.headers["Cache-Control"] == "no-store"
    return response.json()


def enrollment(token: object, email: str = "customer@example.com") -> dict[str, object]:
    return {
        "token": token,
        "email": email,
        "name": "Invited",
        "last_name": "Person",
        "password": PASSWORD,
    }


async def enroll(
    e: Accounts, email: str = "customer@example.com", *, support: bool = False
) -> tuple[dict[str, str], SessionCreated]:
    invitation = await invite(e, support=support)
    response = await e.client.post(
        "/auth/invitations/redeem", json=enrollment(invitation["token"], email)
    )
    assert response.status_code == 201, response.text
    assert response.headers["Cache-Control"] == "no-store"
    return {
        "Authorization": f"Bearer {response.json()['access_token']}"
    }, SessionCreated.model_validate(response.json())


@pytest.mark.anyio
async def test_enrollment_login_logout_and_existing_account_scope(
    accounts: Accounts,
) -> None:
    e = accounts
    headers, original = await enroll(e)
    assert original.user.is_admin is False
    response = await e.client.post(
        "/issue-reports/", headers=headers, json={"description": "Private observation"}
    )
    assert response.status_code == 201, response.text
    report = response.json()
    assert report["customer_account_id"] == str(e.account)
    assert (await e.client.post("/auth/logout", headers=headers)).status_code == 204
    assert (await e.client.get("/issue-reports/", headers=headers)).status_code == 401
    signed_in = await e.client.post(
        "/auth/login", json={"email": "CUSTOMER@EXAMPLE.COM", "password": PASSWORD}
    )
    assert (
        signed_in.status_code == 200
        and signed_in.json()["access_token"] != original.access_token
    )
    fresh = {"Authorization": f"Bearer {signed_in.json()['access_token']}"}
    assert (
        await e.client.get(f"/issue-reports/{report['id']}", headers=fresh)
    ).status_code == 200
    # Permanent account, new session, same tenant and report.
    assert signed_in.json()["user"] == original.user.model_dump(mode="json")


@pytest.mark.anyio
async def test_database_keeps_only_hashes_and_invitation_cannot_authenticate(
    accounts: Accounts,
) -> None:
    e = accounts
    invitation = await invite(e)
    token = str(invitation["token"])
    assert (
        await e.client.get(
            "/issue-reports/", headers={"Authorization": f"Bearer {token}"}
        )
    ).status_code == 401
    response = await e.client.post("/auth/invitations/redeem", json=enrollment(token))
    assert response.status_code == 201
    async with e.sessions() as session:
        saved = await session.get(
            AuthInvitation, UUID(str(invitation["invitation_id"]))
        )
        credential = await session.scalar(
            select(AuthCredential).where(AuthCredential.email == "customer@example.com")
        )
        sessions = list(await session.scalars(select(AuthSession)))
        assert (
            saved is not None
            and saved.consumed_at is not None
            and token not in saved.token_hash
        )
        assert credential is not None and credential.password_hash.startswith(
            "$argon2id$"
        )
        assert PASSWORD not in credential.password_hash
        assert all(
            row.token_hash != response.json()["access_token"] for row in sessions
        )


@pytest.mark.anyio
async def test_recipient_chooses_email_and_duplicate_does_not_consume_token(
    accounts: Accounts,
) -> None:
    e = accounts
    invitation = await invite(e)
    duplicate = await e.client.post(
        "/auth/invitations/redeem",
        json=enrollment(invitation["token"], "ADMIN@EXAMPLE.COM"),
    )
    assert duplicate.status_code == 409
    async with e.sessions() as session:
        saved = await session.get(
            AuthInvitation, UUID(str(invitation["invitation_id"]))
        )
        assert saved is not None and saved.consumed_at is None
        assert await session.scalar(select(func.count()).select_from(User)) == 1
    response = await e.client.post(
        "/auth/invitations/redeem",
        json=enrollment(invitation["token"], "Chosen@EXAMPLE.COM"),
    )
    assert response.status_code == 201, response.text
    assert response.json()["user"]["email"] == "chosen@example.com"
    assert response.json()["user"]["customer_account_id"] == str(e.account)
    assert response.json()["user"]["user_type"] == "customer"
    assert response.json()["user"]["is_admin"] is False
    assert (
        await e.client.post(
            "/auth/login", json={"email": "chosen@example.com", "password": PASSWORD}
        )
    ).status_code == 200


@pytest.mark.anyio
@pytest.mark.parametrize("email", [None, "not-an-email"])
async def test_redemption_requires_valid_recipient_email(
    accounts: Accounts, email: str | None
) -> None:
    e = accounts
    invitation = await invite(e)
    body = enrollment(invitation["token"])
    if email is None:
        body.pop("email")
    else:
        body["email"] = email
    assert (
        await e.client.post("/auth/invitations/redeem", json=body)
    ).status_code == 422


@pytest.mark.anyio
async def test_concurrent_redemption_creates_one_permanent_account(
    accounts: Accounts,
) -> None:
    e = accounts
    invitation = await invite(e)
    responses = await asyncio.gather(
        *(
            e.client.post(
                "/auth/invitations/redeem", json=enrollment(invitation["token"])
            )
            for _ in range(2)
        )
    )
    assert sorted(response.status_code for response in responses) == [201, 400]
    assert (
        await e.client.post(
            "/auth/invitations/redeem", json=enrollment(invitation["token"])
        )
    ).status_code == 400
    async with e.sessions() as session:
        assert (
            await session.scalar(select(func.count()).select_from(AuthCredential)) == 2
        )


@pytest.mark.anyio
@pytest.mark.parametrize("state", ["expired", "revoked", "invalid"])
async def test_unusable_invitations_have_same_error_without_creating_users(
    accounts: Accounts, state: str
) -> None:
    e = accounts
    invitation = await invite(e)
    if state == "expired":
        async with e.sessions() as session:
            await session.execute(
                update(AuthInvitation).values(
                    expires_at=func.now() - timedelta(seconds=1)
                )
            )
            await session.commit()
    elif state == "revoked":
        assert (
            await e.client.delete(
                f"/admin/invitations/{invitation['invitation_id']}", headers=e.admin
            )
        ).status_code == 204
    else:
        invitation["token"] = "not-a-valid-invitation"
    response = await e.client.post(
        "/auth/invitations/redeem", json=enrollment(invitation["token"])
    )
    assert response.status_code == 400
    assert response.json()["error"]["message"] == "Invitation unavailable"
    async with e.sessions() as session:
        assert await session.scalar(select(func.count()).select_from(User)) == 1


@pytest.mark.anyio
async def test_admin_management_does_not_grant_report_access(
    accounts: Accounts,
) -> None:
    e = accounts
    customer, _ = await enroll(e)
    created = await e.client.post(
        "/issue-reports/", headers=customer, json={"description": "Tenant A only"}
    )
    report_id = created.json()["id"]
    path = f"/support/issue-reports/{report_id}/state"
    assert (await e.client.get(path, headers=e.admin)).status_code == 404
    assert (await e.client.get("/issue-reports/", headers=e.admin)).status_code == 403
    support, profile = await enroll(e, "support@example.com", support=True)
    assert (await e.client.get(path, headers=support)).status_code == 200
    assert (await e.client.get("/issue-reports/", headers=support)).status_code == 403
    assert (
        await e.client.post(
            "/admin/invitations",
            headers=support,
            json={
                "user_type": "customer",
                "customer_account_id": str(e.account),
            },
        )
    ).status_code == 403
    support_id = profile.user.id
    assert (
        await e.client.put(
            f"/admin/users/{support_id}/support-accounts",
            headers=e.admin,
            json={"account_ids": []},
        )
    ).status_code == 204
    assert (await e.client.get(path, headers=support)).status_code == 404


@pytest.mark.anyio
async def test_disable_revokes_sessions_and_blocks_repeat_login(
    accounts: Accounts,
) -> None:
    e = accounts
    headers, profile = await enroll(e)
    user_id = profile.user.id
    assert (
        await e.client.delete(f"/admin/users/{user_id}/access", headers=e.admin)
    ).status_code == 204
    assert (await e.client.get("/issue-reports/", headers=headers)).status_code == 401
    response = await e.client.post(
        "/auth/login", json={"email": "customer@example.com", "password": PASSWORD}
    )
    assert (
        response.status_code == 401
        and response.json()["error"]["message"] == "Invalid credentials"
    )
    assert (
        await e.client.delete(f"/admin/users/{e.admin_id}/access", headers=e.admin)
    ).status_code == 403


@pytest.mark.anyio
async def test_expiry_password_reset_and_membership_changes_invalidate_sessions(
    accounts: Accounts,
) -> None:
    e = accounts
    headers, profile = await enroll(e)
    user_id = profile.user.id
    async with e.sessions() as session:
        await session.execute(
            update(AuthSession)
            .where(AuthSession.user_id == user_id)
            .values(expires_at=func.now() - timedelta(seconds=1))
        )
        await session.commit()
    assert (await e.client.get("/issue-reports/", headers=headers)).status_code == 401
    login = await e.client.post(
        "/auth/login", json={"email": "customer@example.com", "password": PASSWORD}
    )
    headers = {"Authorization": f"Bearer {login.json()['access_token']}"}
    async with e.sessions() as session:
        await reset_password(session, "customer@example.com", PASSWORD + " changed")
    assert (await e.client.get("/issue-reports/", headers=headers)).status_code == 401
    assert (
        await e.client.post(
            "/auth/login", json={"email": "customer@example.com", "password": PASSWORD}
        )
    ).status_code == 401
    changed = await e.client.post(
        "/auth/login",
        json={"email": "customer@example.com", "password": PASSWORD + " changed"},
    )
    headers = {"Authorization": f"Bearer {changed.json()['access_token']}"}
    async with e.sessions() as session:
        await session.execute(
            update(User).where(User.id == user_id).values(customer_account_id=e.foreign)
        )
        await session.commit()
    assert (await e.client.get("/issue-reports/", headers=headers)).status_code == 401


@pytest.mark.anyio
async def test_password_mode_never_falls_back_to_demo_tokens(
    accounts: Accounts, monkeypatch: pytest.MonkeyPatch
) -> None:
    import json

    e = accounts
    monkeypatch.setenv(
        "DEMO_TOKEN_USER_IDS", json.dumps({"old-token": str(e.admin_id)})
    )
    assert (
        await e.client.get(
            "/issue-reports/", headers={"Authorization": "Bearer old-token"}
        )
    ).status_code == 401
    monkeypatch.setenv("AUTH_MODE", "broken")
    assert (await e.client.get("/issue-reports/", headers=e.admin)).status_code == 503
    assert (await e.client.get("/health")).status_code == 200


@pytest.mark.anyio
async def test_login_failures_are_generic_and_throttled(accounts: Accounts) -> None:
    e = accounts
    for _ in range(LOGIN_ATTEMPTS):
        response = await e.client.post(
            "/auth/login", json={"email": "missing@example.com", "password": PASSWORD}
        )
        assert response.status_code == 401
        assert response.json()["error"]["message"] == "Invalid credentials"
        assert PASSWORD not in response.text
    limited = await e.client.post(
        "/auth/login", json={"email": "MISSING@example.com", "password": PASSWORD}
    )
    assert limited.status_code == 429 and limited.headers["Retry-After"] == "600"


@pytest.mark.anyio
async def test_role_and_admin_injection_is_rejected(accounts: Accounts) -> None:
    e = accounts
    body = {
        "user_type": "customer",
        "customer_account_id": str(e.account),
    }
    assert (await e.client.post("/admin/invitations", json=body)).status_code == 401
    assert (
        await e.client.post(
            "/admin/invitations", headers=e.admin, json={**body, "is_admin": True}
        )
    ).status_code == 422
    assert (
        await e.client.post(
            "/admin/invitations", headers=e.admin, json={**body, "user_type": "admin"}
        )
    ).status_code == 422
    assert (
        await e.client.post(
            "/admin/invitations",
            headers=e.admin,
            json={**body, "support_account_ids": [str(e.foreign)]},
        )
    ).status_code == 422
    invitation = await invite(e)
    assert (
        await e.client.post(
            "/auth/invitations/redeem",
            json={
                **enrollment(invitation["token"]),
                "customer_account_id": str(e.foreign),
            },
        )
    ).status_code == 422


@pytest.mark.anyio
async def test_demo_config_is_strict_and_never_creates_admin(
    accounts: Accounts, monkeypatch: pytest.MonkeyPatch
) -> None:
    e = accounts
    monkeypatch.setenv("AUTH_MODE", "demo")
    for setting in ("{", "[]", '{"token":123}'):
        monkeypatch.setenv("DEMO_TOKEN_USER_IDS", setting)
        assert (
            await e.client.get(
                "/issue-reports/", headers={"Authorization": "Bearer token"}
            )
        ).status_code == 503


@pytest.mark.anyio
async def test_session_metadata_restores_identity_without_returning_token(
    accounts: Accounts,
) -> None:
    response = await accounts.client.get("/auth/session", headers=accounts.admin)
    assert response.status_code == 200
    assert response.headers["Cache-Control"] == "no-store"
    assert set(response.json()) == {"expires_at", "user"}
    assert response.json()["user"]["id"] == str(accounts.admin_id)
    assert response.json()["user"]["is_admin"] is True
    assert (await accounts.client.get("/auth/session")).status_code == 401
    assert (
        await accounts.client.post("/auth/logout", headers=accounts.admin)
    ).status_code == 204
    assert (
        await accounts.client.get("/auth/session", headers=accounts.admin)
    ).status_code == 401


@pytest.mark.anyio
async def test_session_metadata_rejects_expired_or_disabled_identity(
    accounts: Accounts,
) -> None:
    async with accounts.sessions() as session:
        await session.execute(
            update(AuthSession)
            .where(AuthSession.user_id == accounts.admin_id)
            .values(expires_at=func.clock_timestamp() - timedelta(seconds=1))
        )
        await session.commit()
    assert (
        await accounts.client.get("/auth/session", headers=accounts.admin)
    ).status_code == 401
    signed_in = await accounts.client.post(
        "/auth/login", json={"email": "admin@example.com", "password": PASSWORD}
    )
    headers = {"Authorization": f"Bearer {signed_in.json()['access_token']}"}
    async with accounts.sessions() as session:
        await session.execute(
            update(AuthCredential)
            .where(AuthCredential.user_id == accounts.admin_id)
            .values(disabled_at=func.clock_timestamp())
        )
        await session.commit()
    assert (
        await accounts.client.get("/auth/session", headers=headers)
    ).status_code == 401
