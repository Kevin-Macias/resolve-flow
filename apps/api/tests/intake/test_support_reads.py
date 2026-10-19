import json
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
from uuid import uuid4

import pytest
from conftest import Environment
from httpx import ASGITransport, AsyncClient
from sqlalchemy import select
from test_recovery import BeforeDispatch, Crash

from api.db.models import IssueReport, User
from api.intake.models import IntakeRun
from api.main import create_app
from api.support import runs
from api.support.runs import SupportRun, SupportRuns
from api.workflow.checkpoints import open_checkpointer, workflow_config


async def reader(e: Environment, monkeypatch: pytest.MonkeyPatch) -> SupportRuns:
    async with e.sessions() as session:
        report = await session.get(IssueReport, e.report_id)
        assert report is not None
        monkeypatch.setenv(
            "DEMO_SUPPORT_ACCOUNT_IDS",
            json.dumps({e.tokens["support"]: [str(report.customer_account_id)]}),
        )
    return SupportRuns(e.sessions, e.url, e.runtime.checkpoint_schema)


@pytest.mark.anyio
async def test_persisted_order_archival_restart_and_no_read_writes(
    environment: Environment, monkeypatch: pytest.MonkeyPatch
) -> None:
    e = environment
    view, _ = await e.service().start(e.report_id)
    source = await reader(e, monkeypatch)
    app = create_app()
    app.state.session_factory = e.sessions
    app.state.support_runs = source
    # No intake runtime or provider is installed on this app.
    async with open_checkpointer(e.url, e.runtime.checkpoint_schema) as saver:
        before = [item async for item in saver.alist(workflow_config(view.run_id))]
    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://test",
        headers={"Authorization": "Bearer support"},
    ) as client:
        path = f"/support/issue-reports/{e.report_id}/intake-run"
        response = await client.get(path)
        assert response.status_code == 200, response.text
        result = SupportRun.model_validate_json(response.text)
        assert (
            list(result.timeline) == before[0].checkpoint["channel_values"]["timeline"]
        )
        assert result.run_id == view.run_id and result.simulated
        assert result.timeline and all(
            event.stage == "intake" for event in result.timeline
        )
        assert [event.sequence for event in result.timeline] == list(
            range(1, len(result.timeline) + 1)
        )
        assert set(response.json()) == {
            "version",
            "run_id",
            "report_id",
            "provider_mode",
            "simulated",
            "operation_pending",
            "timeline",
        }
        assert (await client.get(path)).json() == response.json()
        # A fresh reader restores the same persisted view.
        app.state.support_runs = SupportRuns(
            e.sessions, e.url, e.runtime.checkpoint_schema
        )
        assert (await client.get(path)).json() == response.json()
        async with e.sessions() as session:
            report = await session.get(IssueReport, e.report_id)
            assert report is not None
            report.status = "deleted"
            await session.commit()
        assert (await client.get(path)).json() == response.json()
        app.state.intake_runtime = e.runtime
        customer = await client.get(
            f"/intake-runs/{view.run_id}",
            headers={"Authorization": "Bearer customer-a"},
        )
        assert customer.status_code == 404
    async with open_checkpointer(e.url, e.runtime.checkpoint_schema) as saver:
        after = [item async for item in saver.alist(workflow_config(view.run_id))]
    assert after == before
    assert e.provider.calls == 1
    async with e.sessions() as session:
        run = await session.get(IntakeRun, view.run_id)
        assert run is not None and run.revision == view.revision


@pytest.mark.anyio
@pytest.mark.parametrize(
    ("token", "grants", "status"),
    [
        (None, "valid", 401),
        ("invalid", "valid", 401),
        ("customer-a", "valid", 403),
        ("support", "missing", 404),
        ("support", "foreign", 404),
        ("support", "malformed", 503),
    ],
)
async def test_denials_do_not_read_checkpoints(
    environment: Environment,
    monkeypatch: pytest.MonkeyPatch,
    token: str | None,
    grants: str,
    status: int,
) -> None:
    e = environment
    await e.service().start(e.report_id)
    source = await reader(e, monkeypatch)
    if grants == "missing":
        monkeypatch.delenv("DEMO_SUPPORT_ACCOUNT_IDS")
    elif grants == "foreign":
        monkeypatch.setenv(
            "DEMO_SUPPORT_ACCOUNT_IDS",
            json.dumps({e.tokens["support"]: [str(e.other_account)]}),
        )
    elif grants == "malformed":
        monkeypatch.setenv("DEMO_SUPPORT_ACCOUNT_IDS", '{"bad": "*"}')

    def forbidden_read(*args: object, **kwargs: object) -> None:
        pytest.fail("Denied request attempted a checkpoint read")

    monkeypatch.setattr(runs, "open_checkpointer", forbidden_read)
    app = create_app()
    app.state.session_factory = e.sessions
    app.state.support_runs = source
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client:
        response = await client.get(
            f"/support/issue-reports/{e.report_id}/intake-run",
            headers={"Authorization": f"Bearer {token}"} if token else {},
        )
    assert response.status_code == status
    assert e.provider.calls == 1


@pytest.mark.anyio
async def test_missing_run_and_empty_accepted_run(
    environment: Environment, monkeypatch: pytest.MonkeyPatch
) -> None:
    e = environment
    app = create_app()
    app.state.session_factory = e.sessions
    app.state.support_runs = await reader(e, monkeypatch)
    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://test",
        headers={"Authorization": "Bearer support"},
    ) as client:
        path = f"/support/issue-reports/{e.report_id}/intake-run"
        missing = await client.get(path)
        assert missing.status_code == 404
        assert (
            await client.get(f"/support/issue-reports/{uuid4()}/intake-run")
        ).json() == missing.json()
        with pytest.raises(Crash):
            await BeforeDispatch(e.runtime, "customer-a").start(e.report_id)
        response = await client.get(path)
        assert response.status_code == 200
        assert response.json()["timeline"] == []
        assert response.json()["operation_pending"] is True
        assert (await client.get(path)).json() == response.json()
    assert e.provider.calls == 0


@pytest.mark.anyio
@pytest.mark.parametrize("revoke", ["grants", "token", "role", "binding"])
async def test_access_rechecked_after_checkpoint_read(
    environment: Environment, monkeypatch: pytest.MonkeyPatch, revoke: str
) -> None:
    e = environment
    await e.service().start(e.report_id)
    app = create_app()
    app.state.session_factory = e.sessions
    app.state.support_runs = await reader(e, monkeypatch)

    @asynccontextmanager
    async def revoking_read(url: str, schema: str) -> AsyncGenerator[object]:
        async with open_checkpointer(url, schema) as saver:
            yield saver
        if revoke == "grants":
            monkeypatch.setenv("DEMO_SUPPORT_ACCOUNT_IDS", "{}")
        elif revoke == "token":
            monkeypatch.setenv("DEMO_TOKEN_USER_IDS", "{}")
        else:
            async with e.sessions() as session:
                if revoke == "role":
                    user = await session.get(User, e.tokens["support"])
                    assert user is not None
                    user.user_type = "customer"
                    user.customer_account_id = e.other_account
                else:
                    run = await session.scalar(select(IntakeRun))
                    assert run is not None
                    run.customer_account_id = e.other_account
                await session.commit()

    monkeypatch.setattr(runs, "open_checkpointer", revoking_read)
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client:
        response = await client.get(
            f"/support/issue-reports/{e.report_id}/intake-run",
            headers={"Authorization": "Bearer support"},
        )
    assert (
        response.status_code
        == {"grants": 404, "token": 401, "role": 403, "binding": 404}[revoke]
    )
    assert "timeline" not in response.text and e.provider.calls == 1


def test_saved_order_preserves_clock_times_and_rejects_corrupt_history() -> None:
    from datetime import UTC, datetime

    from api.support.runs import saved_events
    from api.workflow.timeline import EventMetadata, EventType, ExecutionEvent

    run_id, report_id = uuid4(), uuid4()
    first = ExecutionEvent(
        event_id=uuid4(),
        workflow_run_id=run_id,
        stage="intake",
        sequence=1,
        occurred_at=datetime(2026, 10, 9, 12, tzinfo=UTC),
        event_type=EventType.WORKFLOW_STARTED,
        metadata=EventMetadata(),
    )
    second = first.model_copy(
        update={
            "event_id": uuid4(),
            "sequence": 2,
            "occurred_at": datetime(2026, 10, 9, 11, tzinfo=UTC),
            "event_type": EventType.EXTRACTION_SUCCEEDED,
        }
    )
    values: dict[str, object] = {
        "workflow_run_id": run_id,
        "issue_report_id": report_id,
        "timeline": [first, second],
    }
    assert saved_events(values, run_id, report_id) == [first, second]
    for bad in (
        {"workflow_run_id": uuid4()},
        {"issue_report_id": uuid4()},
        {"timeline": [second, first]},
        {"timeline": [first, first]},
        {"timeline": [first.model_copy(update={"workflow_run_id": uuid4()})]},
        {"timeline": [first.model_copy(update={"stage": "approval"})]},
        {"timeline": [{**first.model_dump(), "raw_prompt": "private"}]},
    ):
        with pytest.raises(ValueError):
            saved_events({**values, **bad}, run_id, report_id)


@pytest.mark.anyio
async def test_unavailable_checkpoints_and_invalid_path(
    environment: Environment, monkeypatch: pytest.MonkeyPatch
) -> None:
    e = environment
    await e.service().start(e.report_id)
    app = create_app()
    app.state.session_factory = e.sessions
    app.state.support_runs = await reader(e, monkeypatch)

    def unavailable(*args: object, **kwargs: object) -> None:
        raise RuntimeError("Private infrastructure details")

    monkeypatch.setattr(runs, "open_checkpointer", unavailable)
    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://test",
        headers={"Authorization": "Bearer support"},
    ) as client:
        failed = await client.get(f"/support/issue-reports/{e.report_id}/intake-run")
        assert failed.status_code == 503
        assert "Private" not in failed.text and "timeline" not in failed.text
        assert (
            await client.get("/support/issue-reports/not-a-uuid/intake-run")
        ).status_code == 422
        app.state.support_runs = None
        assert (
            await client.get(f"/support/issue-reports/{e.report_id}/intake-run")
        ).status_code == 503
    assert e.provider.calls == 1
