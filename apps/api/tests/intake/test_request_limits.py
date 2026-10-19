"""HTTP limits stop model work while saved reads and fresh authorization remain."""

from uuid import UUID, uuid4

import pytest
from conftest import Environment
from httpx import ASGITransport, AsyncClient
from sqlalchemy import select

from api.db.models import IssueReport
from api.intake.models import IntakeRun
from api.limits.rate import RatePolicy
from api.main import create_app


@pytest.mark.anyio
@pytest.mark.parametrize("second_token", ["customer-a", "teammate", "rotated"])
async def test_model_operation_limit_binds_user_and_account_before_run_creation(
    environment: Environment, monkeypatch: pytest.MonkeyPatch, second_token: str
) -> None:
    import json

    e = environment
    monkeypatch.setenv(
        "DEMO_TOKEN_USER_IDS",
        json.dumps({**e.tokens, "rotated": e.tokens["customer-a"]}),
    )
    async with e.sessions() as session:
        original = await session.get(IssueReport, e.report_id)
        assert original is not None
        second = IssueReport(
            description="Another report",
            customer_account_id=original.customer_account_id,
            submitted_by_user_id=e.user_id,
            status="submitted",
        )
        session.add(second)
        await session.commit()
    app = create_app()
    app.state.session_factory = e.sessions
    app.state.intake_runtime = e.runtime
    app.state.rate_policy = RatePolicy(model_operations=1)
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client:
        first = await client.post(
            f"/issue-reports/{e.report_id}/intake-run",
            json={},
            headers={"Authorization": "Bearer customer-a"},
        )
        assert first.status_code == 201, first.text
        blocked = await client.post(
            f"/issue-reports/{second.id}/intake-run",
            json={},
            headers={"Authorization": f"Bearer {second_token}"},
        )
        assert blocked.status_code == 429 and blocked.headers["Retry-After"]
        assert (
            await client.get(
                f"/issue-reports/{e.report_id}/intake-run",
                headers={"Authorization": "Bearer customer-a"},
            )
        ).status_code == 200
    assert e.provider.calls == 1
    async with e.sessions() as session:
        assert (
            await session.scalar(
                select(IntakeRun).where(IntakeRun.report_id == second.id)
            )
            is None
        )


@pytest.mark.anyio
async def test_global_model_limit_spans_accounts(environment: Environment) -> None:
    e = environment
    async with e.sessions() as session:
        foreign = IssueReport(
            description="Other account",
            customer_account_id=e.other_account,
            submitted_by_user_id=UUID(e.tokens["customer-b"]),
            status="submitted",
        )
        session.add(foreign)
        await session.commit()
    app = create_app()
    app.state.session_factory = e.sessions
    app.state.intake_runtime = e.runtime
    app.state.rate_policy = RatePolicy(global_model_operations=1)
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client:
        assert (
            await client.post(
                f"/issue-reports/{e.report_id}/intake-run",
                json={},
                headers={"Authorization": "Bearer customer-a"},
            )
        ).status_code == 201
        blocked = await client.post(
            f"/issue-reports/{foreign.id}/intake-run",
            json={},
            headers={"Authorization": "Bearer customer-b"},
        )
        assert blocked.status_code == 429
    assert e.provider.calls == 1


@pytest.mark.anyio
async def test_read_and_mutation_limits_are_distinct_and_cannot_change_access(
    environment: Environment,
) -> None:
    e = environment
    app = create_app()
    app.state.session_factory = e.sessions
    app.state.intake_runtime = e.runtime
    app.state.rate_policy = RatePolicy(user=5, mutations=1)
    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://test",
        headers={"Authorization": "Bearer customer-a"},
    ) as client:
        # Even a failed application request consumes a reservation, but runs no model.
        first = await client.post(
            f"/intake-runs/{uuid4()}/recover", json={"expected_revision": 1}
        )
        assert first.status_code == 404
        blocked = await client.post(f"/issue-reports/{e.report_id}/intake-run", json={})
        assert blocked.status_code == 429
        assert (
            await client.get(f"/issue-reports/{e.report_id}/intake-run")
        ).status_code == 404
        assert (
            await client.get(
                f"/issue-reports/{e.report_id}/intake-run",
                headers={"Authorization": "Bearer unknown"},
            )
        ).status_code == 401
        for _ in range(3):
            assert (
                await client.get(f"/issue-reports/{e.report_id}/intake-run")
            ).status_code == 404
        assert (
            await client.get(f"/issue-reports/{e.report_id}/intake-run")
        ).status_code == 429
    assert e.provider.calls == 0
