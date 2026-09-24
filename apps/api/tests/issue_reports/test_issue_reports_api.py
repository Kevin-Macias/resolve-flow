"""Issue-report endpoint checks against tables in a rolled-back schema."""

import json
import os
from collections.abc import AsyncGenerator
from datetime import datetime
from uuid import UUID, uuid4

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient
from sqlalchemy import text
from sqlalchemy.engine import make_url
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from api.db.models import Base, CustomerAccount, IssueReport, Service, User
from api.db.session import get_session
from api.identity.context import RequestContext
from api.identity.dependencies import get_request_context
from api.main import create_app


@pytest.fixture
def anyio_backend() -> str:
    return "asyncio"


@pytest.fixture
async def database() -> AsyncGenerator[
    tuple[async_sessionmaker[AsyncSession], dict[str, UUID]], None
]:
    database_url = os.getenv("TEST_DATABASE_URL")
    if not database_url:
        pytest.skip("Set TEST_DATABASE_URL to run PostgreSQL endpoint tests")

    engine = create_async_engine(
        make_url(database_url).set(drivername="postgresql+psycopg")
    )
    try:
        async with engine.connect() as connection:
            transaction = await connection.begin()
            try:
                # All DDL and endpoint writes live inside this outer transaction.
                schema = f"rf_test_{uuid4().hex}"
                await connection.execute(text(f'CREATE SCHEMA "{schema}"'))
                await connection.execute(
                    text(f'SET LOCAL search_path TO "{schema}", public')
                )
                await connection.run_sync(Base.metadata.create_all)
                sessions = async_sessionmaker(
                    connection,
                    expire_on_commit=False,
                    join_transaction_mode="create_savepoint",
                )

                first_account = CustomerAccount(name="First account")
                second_account = CustomerAccount(name="Second account")
                async with sessions() as session:
                    session.add_all([first_account, second_account])
                    await session.flush()
                    first_user = User(
                        customer_account_id=first_account.id,
                        user_type="customer",
                        name="Ada",
                        last_name="Lovelace",
                    )
                    second_user = User(
                        customer_account_id=second_account.id,
                        user_type="customer",
                        name="Grace",
                        last_name="Hopper",
                    )
                    service = Service(code="payments", label="Payments")
                    session.add_all([first_user, second_user, service])
                    await session.commit()

                identities = {
                    "first_account": first_account.id,
                    "second_account": second_account.id,
                    "first_user": first_user.id,
                    "second_user": second_user.id,
                    "service": service.id,
                }
                yield sessions, identities
            finally:
                await transaction.rollback()
        async with engine.connect() as connection:
            schema_exists = await connection.scalar(
                text("SELECT 1 FROM pg_namespace WHERE nspname = :schema"),
                {"schema": schema},
            )
            assert schema_exists is None, "Temporary test schema survived rollback"
    finally:
        await engine.dispose()


@pytest.fixture
async def api(
    database: tuple[async_sessionmaker[AsyncSession], dict[str, UUID]],
) -> AsyncGenerator[
    tuple[AsyncClient, list[RequestContext], dict[str, UUID], FastAPI], None
]:
    sessions, identities = database
    current_context = [
        RequestContext(
            identities["first_user"], "customer", identities["first_account"]
        )
    ]
    app = create_app()

    async def override_session() -> AsyncGenerator[AsyncSession]:
        async with sessions() as session:
            yield session

    def override_context() -> RequestContext:
        return current_context[0]

    app.dependency_overrides[get_session] = override_session
    app.dependency_overrides[get_request_context] = override_context

    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client:
        yield client, current_context, identities, app


@pytest.mark.anyio
async def test_session_rollback_discards_flush_but_commit_is_visible_to_next_session(
    database: tuple[async_sessionmaker[AsyncSession], dict[str, UUID]],
) -> None:
    sessions, ids = database
    async with sessions() as session:
        uncommitted = IssueReport(
            customer_account_id=ids["first_account"],
            submitted_by_user_id=ids["first_user"],
            description="Rolled back report",
            status="submitted",
        )
        session.add(uncommitted)
        await session.flush()
        uncommitted_id = uncommitted.id
        await session.rollback()

    async with sessions() as session:
        assert await session.get(IssueReport, uncommitted_id) is None

        committed = IssueReport(
            customer_account_id=ids["first_account"],
            submitted_by_user_id=ids["first_user"],
            description="Committed report",
            status="submitted",
        )
        session.add(committed)
        await session.commit()
        committed_id = committed.id

    async with sessions() as session:
        saved = await session.get(IssueReport, committed_id)
        assert saved is not None
        assert saved.description == "Committed report"
        assert await session.get(IssueReport, uncommitted_id) is None


@pytest.mark.anyio
async def test_create_read_and_list_issue_report(
    api: tuple[AsyncClient, list[RequestContext], dict[str, UUID], FastAPI],
) -> None:
    client, _, ids, _ = api

    created = await client.post(
        "/issue-reports/",
        json={
            "description": "  Payment remains pending  ",
            "affected_service_code": "payments",
        },
    )

    assert created.status_code == 201
    body = created.json()
    assert UUID(body["id"])
    assert body["customer_account_id"] == str(ids["first_account"])
    assert body["description"] == "Payment remains pending"
    assert body["status"] == "submitted"
    assert body["submitted_by"] == {
        "id": str(ids["first_user"]),
        "name": "Ada",
        "last_name": "Lovelace",
    }
    assert body["affected_service"] == {"code": "payments", "label": "Payments"}
    assert datetime.fromisoformat(body["created_at"])
    assert datetime.fromisoformat(body["updated_at"])
    assert (await client.get(f"/issue-reports/{body['id']}")).json() == body
    listed = await client.get("/issue-reports/")
    assert listed.status_code == 200
    assert listed.json() == [body]


@pytest.mark.anyio
async def test_reports_are_scoped_to_the_customer_account(
    api: tuple[AsyncClient, list[RequestContext], dict[str, UUID], FastAPI],
) -> None:
    client, current_context, ids, _ = api
    created = await client.post(
        "/issue-reports/", json={"description": "Export failed"}
    )
    assert created.status_code == 201
    report_id = created.json()["id"]

    current_context[0] = RequestContext(
        ids["second_user"], "customer", ids["second_account"]
    )
    assert (await client.get(f"/issue-reports/{report_id}")).status_code == 404
    listed = await client.get("/issue-reports/")
    assert listed.status_code == 200
    assert listed.json() == []
    other_report = await client.post("/issue-reports/", json={"description": "Other"})
    assert other_report.status_code == 201
    assert other_report.json()["customer_account_id"] == str(ids["second_account"])
    assert other_report.json()["affected_service"] is None
    missing = await client.get(f"/issue-reports/{uuid4()}")
    assert missing.status_code == 404
    assert missing.json() == {
        "error": {
            "code": "not_found",
            "message": "Issue report not found",
            "details": [],
        }
    }


@pytest.mark.anyio
async def test_invalid_input_and_unknown_service_do_not_create_reports(
    api: tuple[AsyncClient, list[RequestContext], dict[str, UUID], FastAPI],
) -> None:
    client, _, _, _ = api
    for payload in (
        {"description": "   "},
        {"description": "Valid", "customer_account_id": str(uuid4())},
        {"description": "Valid", "affected_service_code": "missing"},
    ):
        response = await client.post("/issue-reports/", json=payload)
        assert response.status_code == 422
        assert response.json()["error"]["code"] == "validation_error"

    assert (await client.get("/issue-reports/")).json() == []


@pytest.mark.anyio
async def test_support_context_cannot_use_customer_endpoints(
    api: tuple[AsyncClient, list[RequestContext], dict[str, UUID], FastAPI],
) -> None:
    client, current_context, ids, _ = api
    current_context[0] = RequestContext(ids["first_user"], "support", None)

    assert (await client.get("/issue-reports/")).status_code == 403
    assert (await client.get(f"/issue-reports/{uuid4()}")).status_code == 403
    assert (
        await client.post("/issue-reports/", json={"description": "Cannot create"})
    ).status_code == 403


@pytest.mark.anyio
async def test_demo_token_selects_the_customer_account(
    api: tuple[AsyncClient, list[RequestContext], dict[str, UUID], FastAPI],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    client, _, ids, app = api
    app.dependency_overrides.pop(get_request_context)
    monkeypatch.setenv(
        "DEMO_TOKEN_USER_IDS",
        json.dumps(
            {
                "first-token": str(ids["first_user"]),
                "second-token": str(ids["second_user"]),
            }
        ),
    )

    assert (await client.get("/issue-reports/")).status_code == 401
    assert (
        await client.get(
            "/issue-reports/", headers={"Authorization": "Bearer bad-token"}
        )
    ).status_code == 401

    created = await client.post(
        "/issue-reports/",
        json={"description": "Account one issue"},
        headers={"Authorization": "Bearer first-token"},
    )
    assert created.status_code == 201
    assert created.json()["customer_account_id"] == str(ids["first_account"])
    assert (
        await client.get(
            f"/issue-reports/{created.json()['id']}",
            headers={"Authorization": "Bearer second-token"},
        )
    ).status_code == 404


@pytest.mark.anyio
async def test_patch_service_distinguishes_omitted_set_and_clear(
    api: tuple[AsyncClient, list[RequestContext], dict[str, UUID], FastAPI],
) -> None:
    client, _, _, _ = api
    created = await client.post(
        "/issue-reports/", json={"description": "Export failed"}
    )
    report_url = f"/issue-reports/{created.json()['id']}"

    set_service = await client.patch(
        report_url, json={"affected_service_code": "payments"}
    )
    assert set_service.status_code == 200
    assert set_service.json()["affected_service"] == {
        "code": "payments",
        "label": "Payments",
    }

    omitted = await client.patch(report_url, json={})
    assert omitted.status_code == 200
    assert omitted.json()["affected_service"] == set_service.json()["affected_service"]

    cleared = await client.patch(report_url, json={"affected_service_code": None})
    assert cleared.status_code == 200
    assert cleared.json()["affected_service"] is None

    unknown = await client.patch(report_url, json={"affected_service_code": "missing"})
    assert unknown.status_code == 422
    assert (await client.get(report_url)).json()["affected_service"] is None


@pytest.mark.anyio
async def test_patch_and_delete_are_scoped_to_the_customer_account(
    api: tuple[AsyncClient, list[RequestContext], dict[str, UUID], FastAPI],
) -> None:
    client, current_context, ids, _ = api
    created = await client.post(
        "/issue-reports/", json={"description": "Export failed"}
    )
    report_url = f"/issue-reports/{created.json()['id']}"

    current_context[0] = RequestContext(
        ids["second_user"], "customer", ids["second_account"]
    )
    assert (await client.patch(report_url, json={})).status_code == 404
    assert (await client.delete(report_url)).status_code == 404
    assert (await client.patch(f"/issue-reports/{uuid4()}", json={})).status_code == 404
    assert (await client.delete(f"/issue-reports/{uuid4()}")).status_code == 404

    current_context[0] = RequestContext(
        ids["first_user"], "customer", ids["first_account"]
    )
    assert (await client.get(report_url)).status_code == 200


@pytest.mark.anyio
async def test_delete_archives_report_from_customer_reads(
    api: tuple[AsyncClient, list[RequestContext], dict[str, UUID], FastAPI],
    database: tuple[async_sessionmaker[AsyncSession], dict[str, UUID]],
) -> None:
    client, _, _, _ = api
    sessions, _ = database
    created = await client.post(
        "/issue-reports/", json={"description": "Export failed"}
    )
    report_url = f"/issue-reports/{created.json()['id']}"

    deleted = await client.delete(report_url)
    assert deleted.status_code == 204
    async with sessions() as session:
        persisted = await session.get(IssueReport, UUID(created.json()["id"]))
        assert persisted is not None
        assert persisted.status == "deleted"
    assert (await client.get(report_url)).status_code == 404
    assert (await client.get("/issue-reports/")).json() == []
    assert (
        await client.patch(report_url, json={"affected_service_code": "payments"})
    ).status_code == 404
    assert (await client.delete(report_url)).status_code == 404


@pytest.mark.anyio
@pytest.mark.parametrize("requested_status", ["draft", "closed", "deleted", "linked"])
async def test_customer_cannot_change_status_through_patch(
    api: tuple[AsyncClient, list[RequestContext], dict[str, UUID], FastAPI],
    requested_status: str,
) -> None:
    client, _, _, _ = api
    created = await client.post(
        "/issue-reports/", json={"description": "Export failed"}
    )
    report_url = f"/issue-reports/{created.json()['id']}"

    attempted = await client.patch(report_url, json={"status": requested_status})
    assert attempted.status_code == 422
    assert (await client.get(report_url)).json()["status"] == "submitted"


@pytest.mark.anyio
async def test_support_context_cannot_patch_or_delete_customer_report(
    api: tuple[AsyncClient, list[RequestContext], dict[str, UUID], FastAPI],
) -> None:
    client, current_context, ids, _ = api
    created = await client.post(
        "/issue-reports/", json={"description": "Export failed"}
    )
    report_url = f"/issue-reports/{created.json()['id']}"
    current_context[0] = RequestContext(ids["first_user"], "support", None)

    assert (await client.patch(report_url, json={})).status_code == 403
    assert (await client.delete(report_url)).status_code == 403
