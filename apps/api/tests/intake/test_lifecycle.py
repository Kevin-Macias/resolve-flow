import asyncio
import json
from uuid import UUID, uuid4

import pytest
from conftest import Environment
from fastapi import HTTPException
from httpx import ASGITransport, AsyncClient
from sqlalchemy import func, select

from api.db.models import IssueReport, User
from api.intake.models import IntakeOperation, IntakeRun
from api.intake.schemas import ClarificationRequest, CustomerRun
from api.main import create_app


def reply(view: CustomerRun, *, action: str = "answer") -> ClarificationRequest:
    assert view.pending is not None
    return ClarificationRequest.model_validate(
        {
            "operation_id": str(uuid4()),
            "expected_revision": view.revision,
            "pending_id": str(view.pending.pending_id),
            "action": action,
            "answers": ["The expected report was not listed."]
            if action == "answer"
            else [],
        }
    )


@pytest.mark.anyio
async def test_start_read_stream_resume_and_duplicates(
    environment: Environment,
) -> None:
    e = environment
    app = create_app()
    app.state.intake_runtime = e.runtime
    headers = {"Authorization": "Bearer customer-a"}
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test", headers=headers
    ) as client:
        created = await client.post(f"/issue-reports/{e.report_id}/intake-run", json={})
        assert created.status_code == 201, created.text
        view = CustomerRun.model_validate_json(created.text)
        assert view.status == "needs_clarification" and view.simulated
        assert view.revision == 2 and e.provider.calls == 1
        repeated = await client.post(
            f"/issue-reports/{e.report_id}/intake-run", json={}
        )
        assert repeated.status_code == 200
        assert repeated.json() == created.json()
        for path in (
            f"/intake-runs/{view.run_id}",
            f"/issue-reports/{e.report_id}/intake-run",
        ):
            response = await client.get(path)
            assert response.json() == created.json()
        stream = await client.get(
            f"/intake-runs/{view.run_id}/events",
            headers={"Last-Event-ID": view.snapshot.event_id},
        )
        assert stream.status_code == 200 and "waiting_input" in stream.text
        assert stream.text.index("event: snapshot") < stream.text.index(
            "event: stream_end"
        )
        assert e.provider.calls == 1
        body = reply(view).model_dump(mode="json")
        answered = await client.post(
            f"/intake-runs/{view.run_id}/clarification", json=body
        )
        assert answered.status_code == 200, answered.text
        complete = CustomerRun.model_validate_json(answered.text)
        assert (
            complete.status == "needs_confirmation"
            and complete.snapshot.progress == "stage_finished"
        )
        assert (
            complete.revision == 4
            and len(complete.turns) == 1
            and not complete.operation_pending
        )
        assert e.provider.calls == 2
        duplicate = await client.post(
            f"/intake-runs/{view.run_id}/clarification", json=body
        )
        assert duplicate.json() == answered.json()
        body["answers"] = ["Different answer"]
        assert (
            await client.post(f"/intake-runs/{view.run_id}/clarification", json=body)
        ).status_code == 409
        assert (
            await client.post(
                f"/intake-runs/{view.run_id}/recover",
                json={"expected_revision": complete.revision},
            )
        ).status_code == 409
        assert (
            await client.post(f"/issue-reports/{e.report_id}/intake-run", json={})
        ).json() == answered.json()
        assert e.provider.calls == 2
        public = answered.text
        for private in (
            "extraction_call",
            "diagnosis",
            "actor_id",
            "timeline",
            "fingerprint",
            "reported_facts",
            "reasons",
        ):
            assert private not in public


@pytest.mark.anyio
@pytest.mark.parametrize(
    ("token", "status"), [("customer-b", 404), ("support", 403), ("invalid", 401)]
)
async def test_denied_identities_never_invoke_provider(
    environment: Environment, token: str, status: int
) -> None:
    e = environment
    service = e.service(token)
    with pytest.raises(HTTPException) as caught:
        await service.start(e.report_id)
    assert caught.value.status_code == status and e.provider.calls == 0
    view, _ = await e.service().start(e.report_id)
    for call in (
        service.get(view.run_id),
        service.clarify(view.run_id, reply(view)),
        service.recover(view.run_id, view.revision),
    ):
        with pytest.raises(HTTPException) as caught:
            await call
        assert caught.value.status_code == status
    assert e.provider.calls == 1


@pytest.mark.anyio
async def test_same_account_teammate_can_answer_and_archival_revokes(
    environment: Environment,
) -> None:
    e = environment
    view, _ = await e.service().start(e.report_id)
    assert (await e.service("teammate").get(view.run_id)) == view
    complete = await e.service("teammate").clarify(
        view.run_id, reply(view, action="continue_incomplete")
    )
    assert (
        complete.incomplete
        and complete.status == "needs_confirmation"
        and e.provider.calls == 1
    )
    async with e.sessions() as session:
        report = await session.get(IssueReport, e.report_id)
        assert report is not None
        report.status = "deleted"
        await session.commit()
    with pytest.raises(HTTPException) as caught:
        await e.service().get(view.run_id)
    assert caught.value.status_code == 404


@pytest.mark.anyio
async def test_token_removal_and_membership_change_rechecked(
    environment: Environment, monkeypatch: pytest.MonkeyPatch
) -> None:
    e = environment
    view, _ = await e.service().start(e.report_id)
    source = e.service()
    await source.authorize(view.run_id)
    monkeypatch.setenv("DEMO_TOKEN_USER_IDS", "{}")
    with pytest.raises(HTTPException) as caught:
        await source.read(view.run_id)
    assert caught.value.status_code == 401
    monkeypatch.setenv("DEMO_TOKEN_USER_IDS", json.dumps(e.tokens))
    async with e.sessions() as session:
        user = await session.get(User, e.user_id)
        assert user is not None
        user.customer_account_id = e.other_account
        await session.commit()
    with pytest.raises(HTTPException) as caught:
        await source.read(view.run_id)
    assert caught.value.status_code == 404
    assert e.provider.calls == 1


@pytest.mark.anyio
@pytest.mark.parametrize(
    "change",
    [
        {"answers": []},
        {"answers": [" "]},
        {"answers": ["a" * 2001]},
        {"answers": ["a", "b"]},
        {"extra": "private"},
        {"pending_id": str(uuid4())},
        {"expected_revision": 1},
        {"action": "continue_incomplete", "answers": ["not allowed"]},
    ],
)
async def test_invalid_or_stale_http_reply_does_not_advance(
    environment: Environment, change: dict[str, object]
) -> None:
    e = environment
    view, _ = await e.service().start(e.report_id)
    body = {**reply(view).model_dump(mode="json"), **change}
    app = create_app()
    app.state.intake_runtime = e.runtime
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client:
        result = await client.post(
            f"/intake-runs/{view.run_id}/clarification",
            json=body,
            headers={"Authorization": "Bearer customer-a"},
        )
    assert result.status_code in (409, 422)
    assert await e.service().get(view.run_id) == view
    assert e.provider.calls == 1


@pytest.mark.anyio
async def test_concurrent_starts_and_replies_advance_once(
    environment: Environment,
) -> None:
    e = environment
    results = await asyncio.gather(
        *(e.service().start(e.report_id) for _ in range(4)), return_exceptions=True
    )
    for result in results:
        if isinstance(result, BaseException):
            assert isinstance(result, HTTPException) and result.status_code == 409
    view = await e.service().for_report(e.report_id)
    assert e.provider.calls == 1
    async with e.sessions() as session:
        assert await session.scalar(select(func.count()).select_from(IntakeRun)) == 1
    replies = [reply(view) for _ in range(3)]
    outcomes = await asyncio.gather(
        *(e.service().clarify(view.run_id, item) for item in replies),
        return_exceptions=True,
    )
    assert sum(isinstance(item, CustomerRun) for item in outcomes) == 1
    assert e.provider.calls == 2
    async with e.sessions() as session:
        assert (
            await session.scalar(select(func.count()).select_from(IntakeOperation)) == 2
        )


@pytest.mark.anyio
async def test_unknown_and_foreign_cursor_before_stream_headers(
    environment: Environment,
) -> None:
    e = environment
    view, _ = await e.service().start(e.report_id)
    app = create_app()
    app.state.intake_runtime = e.runtime
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client:
        for cursor in ("unknown", f"{uuid4()}:1", f"{view.run_id}:99"):
            result = await client.get(
                f"/intake-runs/{view.run_id}/events",
                headers={"Authorization": "Bearer customer-a", "Last-Event-ID": cursor},
            )
            assert result.status_code == 422
        missing = await client.get(
            f"/intake-runs/{UUID(int=0)}",
            headers={"Authorization": "Bearer customer-a"},
        )
        assert missing.status_code == 404
    assert e.provider.calls == 1
