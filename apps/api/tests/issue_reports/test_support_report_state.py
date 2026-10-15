"""Support state reads use only report tables, without a workflow runtime."""

import json
from collections.abc import AsyncGenerator
from dataclasses import dataclass
from uuid import UUID, uuid4

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient
from pydantic import ValidationError
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker
from test_issue_reports_api import database as database

from api.db.models import IssueReport, User
from api.main import create_app
from api.support.reports import SupportReportState, SupportReportStates


@pytest.fixture
def anyio_backend() -> str:
    return "asyncio"


@dataclass
class StateAPI:
    client: AsyncClient
    app: FastAPI
    sessions: async_sessionmaker[AsyncSession]
    ids: dict[str, UUID]
    reader: SupportReportStates

    @property
    def path(self) -> str:
        return f"/support/issue-reports/{self.ids['report']}/state"


@pytest.fixture
async def state_api(
    database: tuple[async_sessionmaker[AsyncSession], dict[str, UUID]],
    monkeypatch: pytest.MonkeyPatch,
) -> AsyncGenerator[StateAPI]:
    sessions, ids = database
    async with sessions() as session:
        support = User(user_type="support", name="Support", last_name="Fixture")
        report = IssueReport(
            customer_account_id=ids["first_account"],
            submitted_by_user_id=ids["first_user"],
            description="Private report text",
            status="submitted",
        )
        foreign = IssueReport(
            customer_account_id=ids["second_account"],
            submitted_by_user_id=ids["second_user"],
            description="Foreign private report text",
            status="deleted",
        )
        session.add_all([support, report, foreign])
        await session.commit()
        ids.update(support=support.id, report=report.id, foreign=foreign.id)
    monkeypatch.setenv(
        "DEMO_TOKEN_USER_IDS",
        json.dumps(
            {"support": str(ids["support"]), "customer": str(ids["first_user"])}
        ),
    )
    monkeypatch.setenv(
        "DEMO_SUPPORT_ACCOUNT_IDS",
        json.dumps({str(ids["support"]): [str(ids["first_account"])]}),
    )
    reader = SupportReportStates(sessions)
    app = create_app()
    app.state.support_report_states = reader
    app.state.session_factory = sessions
    # No intake tables, checkpoint tables, runtime, or support timeline reader.
    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://test",
        headers={"Authorization": "Bearer support"},
    ) as client:
        yield StateAPI(client, app, sessions, ids, reader)


@pytest.mark.anyio
@pytest.mark.parametrize(
    "status", ["draft", "submitted", "in_review", "linked", "closed", "deleted"]
)
async def test_current_state_without_intake_and_no_writes(
    state_api: StateAPI, status: str
) -> None:
    e = state_api
    async with e.sessions() as session:
        report = await session.get(IssueReport, e.ids["report"])
        assert report is not None
        report.status = status
        await session.commit()
        await session.refresh(report)
        before = {
            column.name: getattr(report, column.name)
            for column in IssueReport.__table__.columns
        }
    expected = {
        "version": 1,
        "report_id": str(e.ids["report"]),
        "customer_account_id": str(e.ids["first_account"]),
        "status": status,
        "archived": status == "deleted",
    }
    for _ in range(2):
        response = await e.client.get(e.path)
        assert response.status_code == 200, response.text
        assert response.json() == expected
    async with e.sessions() as session:
        report = await session.get(IssueReport, e.ids["report"])
        assert report is not None
        after = {
            column.name: getattr(report, column.name)
            for column in IssueReport.__table__.columns
        }
        assert after == before
    customer = await e.client.get(
        f"/issue-reports/{e.ids['report']}",
        headers={"Authorization": "Bearer customer"},
    )
    assert customer.status_code == (404 if status == "deleted" else 200)
    customer_list = await e.client.get(
        "/issue-reports/", headers={"Authorization": "Bearer customer"}
    )
    assert customer_list.status_code == 200
    assert (str(e.ids["report"]) in [row["id"] for row in customer_list.json()]) == (
        status != "deleted"
    )


@pytest.mark.anyio
async def test_foreign_and_missing_reports_are_indistinguishable(
    state_api: StateAPI,
) -> None:
    e = state_api
    foreign = await e.client.get(f"/support/issue-reports/{e.ids['foreign']}/state")
    missing = await e.client.get(f"/support/issue-reports/{uuid4()}/state")
    assert foreign.status_code == missing.status_code == 404
    assert foreign.json() == missing.json()
    assert "private" not in foreign.text.lower()


@pytest.mark.anyio
@pytest.mark.parametrize(
    ("token", "grants", "expected"),
    [
        (None, "valid", 401),
        ("unknown", "valid", 401),
        ("customer", "valid", 403),
        ("support", None, 404),
        ("support", "{}", 404),
        ("support", '{"bad": "*"}', 503),
    ],
)
async def test_identity_and_account_denials(
    state_api: StateAPI,
    monkeypatch: pytest.MonkeyPatch,
    token: str | None,
    grants: str | None,
    expected: int,
) -> None:
    if grants is None:
        monkeypatch.delenv("DEMO_SUPPORT_ACCOUNT_IDS")
    elif grants != "valid":
        monkeypatch.setenv("DEMO_SUPPORT_ACCOUNT_IDS", grants)
    headers = {"Authorization": f"Bearer {token}"} if token else {"Authorization": ""}
    response = await state_api.client.get(state_api.path, headers=headers)
    assert response.status_code == expected
    assert "report_id" not in response.text


@pytest.mark.anyio
@pytest.mark.parametrize(
    "revoke", ["token", "role", "grants", "ownership", "granted_ownership", "archive"]
)
async def test_access_is_rechecked_before_return(
    state_api: StateAPI, monkeypatch: pytest.MonkeyPatch, revoke: str
) -> None:
    e = state_api
    original = e.reader.authorized_report
    reads = 0

    async def revoking_read(token: str, report_id: UUID) -> IssueReport:
        nonlocal reads
        report = await original(token, report_id)
        reads += 1
        if reads == 1:
            if revoke == "token":
                monkeypatch.setenv("DEMO_TOKEN_USER_IDS", "{}")
            elif revoke == "grants":
                monkeypatch.setenv("DEMO_SUPPORT_ACCOUNT_IDS", "{}")
            else:
                async with e.sessions() as session:
                    if revoke == "role":
                        user = await session.get(User, e.ids["support"])
                        assert user is not None
                        user.user_type = "customer"
                        user.customer_account_id = e.ids["first_account"]
                    else:
                        current = await session.get(IssueReport, report_id)
                        assert current is not None
                        if revoke == "archive":
                            current.status = "deleted"
                        else:
                            current.customer_account_id = e.ids["second_account"]
                            if revoke == "granted_ownership":
                                monkeypatch.setenv(
                                    "DEMO_SUPPORT_ACCOUNT_IDS",
                                    json.dumps(
                                        {
                                            str(e.ids["support"]): [
                                                str(e.ids["first_account"]),
                                                str(e.ids["second_account"]),
                                            ]
                                        }
                                    ),
                                )
                    await session.commit()
        return report

    monkeypatch.setattr(e.reader, "authorized_report", revoking_read)
    response = await e.client.get(e.path)
    if revoke == "archive":
        assert response.status_code == 200
        assert response.json()["status"] == "deleted"
        assert response.json()["archived"] is True
    else:
        assert (
            response.status_code
            == {
                "token": 401,
                "role": 403,
                "grants": 404,
                "ownership": 404,
                "granted_ownership": 503,
            }[revoke]
        )
        assert "report_id" not in response.text


@pytest.mark.anyio
async def test_invalid_path_and_unavailable_reader(
    state_api: StateAPI, monkeypatch: pytest.MonkeyPatch
) -> None:
    e = state_api
    assert (
        await e.client.get("/support/issue-reports/not-a-uuid/state")
    ).status_code == 422

    async def unavailable(token: str, report_id: UUID) -> SupportReportState:
        raise SQLAlchemyError("private database connection details")

    monkeypatch.setattr(e.reader, "get", unavailable)
    response = await e.client.get(e.path)
    assert response.status_code == 503
    assert response.json()["error"]["message"] == "Service unavailable"
    assert "private" not in response.text
    e.app.state.support_report_states = None
    assert (await e.client.get(e.path)).status_code == 503


@pytest.mark.anyio
async def test_invalid_projection_fails_closed(
    state_api: StateAPI, monkeypatch: pytest.MonkeyPatch
) -> None:
    e = state_api
    original = e.reader.authorized_report

    async def corrupt_read(token: str, report_id: UUID) -> IssueReport:
        report = await original(token, report_id)
        # Simulate a corrupt loaded value without bypassing database constraints.
        report.status = "invalid-private-value"
        return report

    monkeypatch.setattr(e.reader, "authorized_report", corrupt_read)
    response = await e.client.get(e.path)
    assert response.status_code == 503
    assert "invalid-private-value" not in response.text


def test_response_rejects_extra_fields_and_inconsistent_archival() -> None:
    value: dict[str, object] = {
        "report_id": str(uuid4()),
        "customer_account_id": str(uuid4()),
        "status": "deleted",
        "archived": True,
    }
    assert SupportReportState.model_validate(value).archived
    for changed in ({"archived": False}, {"archived": 1}, {"description": "private"}):
        with pytest.raises(ValidationError):
            SupportReportState.model_validate({**value, **changed})
