"""Real HTTP and PostgreSQL coverage of the approved support action lifecycle."""

import asyncio
import json
from collections.abc import AsyncGenerator
from uuid import UUID, uuid4

import pytest
from conftest import Environment
from fastapi import HTTPException
from httpx import ASGITransport, AsyncClient

from api.db.models import Base, IssueReport, User
from api.intake.schemas import ClarificationRequest
from api.main import create_app
from api.support.action_models import SupportActionRun
from api.support.action_schemas import ProposalRequest, SupportAction
from api.support.actions import SupportActions
from api.workflow.actions import CreateTicketArguments
from api.workflow.approval import ApprovalReply
from api.workflow.approval_graph import approval_config
from api.workflow.checkpoints import open_checkpointer
from api.workflow.execution import SimulatedCreateTicketTool, SimulatedTicketResult


@pytest.fixture
async def actions(
    environment: Environment, monkeypatch: pytest.MonkeyPatch
) -> AsyncGenerator[
    tuple[Environment, SupportActions, AsyncClient, SimulatedCreateTicketTool], None
]:
    e = environment
    async with e.sessions() as session:
        connection = await session.connection()
        for name in (
            "support_action_runs",
            "proposal_preparations",
            "execution_operations",
            "simulated_ticket_effects",
        ):
            await connection.run_sync(Base.metadata.tables[name].create)
        report = await session.get(IssueReport, e.report_id)
        assert report is not None
        monkeypatch.setenv(
            "DEMO_SUPPORT_ACCOUNT_IDS",
            json.dumps({e.tokens["support"]: [str(report.customer_account_id)]}),
        )
        await session.commit()
    view, _ = await e.service().start(e.report_id)
    assert view.pending is not None
    await e.service().clarify(
        view.run_id,
        ClarificationRequest(
            operation_id=uuid4(),
            expected_revision=view.revision,
            pending_id=view.pending.pending_id,
            action="answer",
            answers=("The report is missing from the same account's list.",),
        ),
    )
    service = SupportActions(e.sessions, e.url, e.runtime.checkpoint_schema)
    tool = SimulatedCreateTicketTool()
    monkeypatch.setattr(service, "tool", lambda: tool)
    app = create_app()
    app.state.session_factory = e.sessions
    app.state.support_actions = service
    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://test",
        headers={"Authorization": "Bearer support"},
    ) as client:
        yield e, service, client, tool


def draft(previous: SupportAction | None = None) -> ProposalRequest:
    return ProposalRequest(
        operation_id=uuid4(),
        expected_fingerprint=previous.fingerprint if previous else None,
        title="Investigate report visibility",
        description="Customer reports a missing issue report; cause is unverified.",
        service_code=None,
        severity=None,
        explanation="Support should review the reported visibility issue.",
    )


def reply(saved: SupportAction, choice: str = "approve") -> ApprovalReply:
    assert saved.proposal is not None
    return ApprovalReply.model_validate(
        dict(
            action_id=saved.proposal.action_id,
            version=saved.proposal.version,
            fingerprint=saved.fingerprint,
            decision=choice,
        )
    )


@pytest.mark.anyio
@pytest.mark.parametrize("choice", ["approve", "reject"])
async def test_create_decide_replay_restart_and_read_only(
    actions: tuple[Environment, SupportActions, AsyncClient, SimulatedCreateTicketTool],
    choice: str,
) -> None:
    e, service, client, tool = actions
    path = f"/support/issue-reports/{e.report_id}"
    assert (await client.get(f"{path}/action")).json()["can_prepare"]
    body = draft()
    response = await client.post(f"{path}/proposal", json=body.model_dump(mode="json"))
    assert response.status_code == 200, response.text
    saved = SupportAction.model_validate_json(response.text)
    assert saved.status == "awaiting_decision" and saved.proposal is not None
    assert saved.run_id is not None
    assert len(tool.calls) == 0
    assert (await service.prepare("support", e.report_id, body)) == saved
    decision = reply(saved, choice)
    response = await client.post(
        f"{path}/runs/{saved.run_id}/decision", json=decision.model_dump(mode="json")
    )
    assert response.status_code == 200, response.text
    result = SupportAction.model_validate_json(response.text)
    assert result.status == ("simulated_success" if choice == "approve" else "rejected")
    assert (
        result.decision is not None
        and str(result.decision.actor_id) == e.tokens["support"]
    )
    assert len(tool.calls) == (1 if choice == "approve" else 0)
    opposite = reply(saved, "reject" if choice == "approve" else "approve")
    assert (
        await service.decide("support", e.report_id, saved.run_id, opposite) == result
    )
    restarted = SupportActions(e.sessions, e.url, e.runtime.checkpoint_schema)
    assert await restarted.get("support", e.report_id) == result
    assert (await client.get(f"{path}/action")).json() == result.model_dump(mode="json")
    assert len(tool.calls) == (1 if choice == "approve" else 0)
    with pytest.raises(HTTPException) as error:
        await service.prepare("support", e.report_id, draft(result))
    assert error.value.status_code == 409


@pytest.mark.anyio
async def test_revision_invalidates_old_reply_and_uuid_reuse(
    actions: tuple[Environment, SupportActions, AsyncClient, SimulatedCreateTicketTool],
) -> None:
    e, service, _, tool = actions
    first = await service.prepare("support", e.report_id, draft())
    assert first.proposal is not None and first.run_id is not None
    body = draft(first).model_copy(update={"title": "Review additional context"})
    current = await service.prepare("support", e.report_id, body)
    assert current.proposal is not None
    assert current.proposal.action_id == first.proposal.action_id
    assert (
        current.proposal.version == 2
        and current.proposal.idempotency_key != first.proposal.idempotency_key
    )
    with pytest.raises(HTTPException) as error:
        await service.decide("support", e.report_id, first.run_id, reply(first))
    assert error.value.status_code == 409 and not tool.calls
    with pytest.raises(HTTPException) as error:
        await service.prepare(
            "support",
            e.report_id,
            body.model_copy(update={"title": "Different payload"}),
        )
    assert error.value.status_code == 409
    assert (
        await service.decide("support", e.report_id, first.run_id, reply(current))
    ).status == "simulated_success"


@pytest.mark.anyio
async def test_interrupted_preparation_replays_without_new_version(
    actions: tuple[Environment, SupportActions, AsyncClient, SimulatedCreateTicketTool],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    e, service, _, tool = actions
    original = service.initialize

    async def crash(token: str, report_id: UUID, row: SupportActionRun) -> None:
        raise asyncio.CancelledError()

    monkeypatch.setattr(service, "initialize", crash)
    body = draft()
    with pytest.raises(asyncio.CancelledError):
        await service.prepare("support", e.report_id, body)
    pending = await service.get("support", e.report_id)
    assert pending.status == "preparing" and pending.pending_preparation == body
    monkeypatch.setattr(service, "initialize", original)
    ready = await service.prepare("support", e.report_id, body)
    assert (
        ready.status == "awaiting_decision"
        and ready.proposal == pending.proposal
        and not tool.calls
    )


@pytest.mark.anyio
@pytest.mark.parametrize("change", ["role", "grants", "archive", "input"])
async def test_fresh_access_and_context_before_decision(
    actions: tuple[Environment, SupportActions, AsyncClient, SimulatedCreateTicketTool],
    monkeypatch: pytest.MonkeyPatch,
    change: str,
) -> None:
    e, service, client, tool = actions
    saved = await service.prepare("support", e.report_id, draft())
    if change == "grants":
        monkeypatch.setenv("DEMO_SUPPORT_ACCOUNT_IDS", "{}")
    else:
        async with e.sessions() as session:
            if change == "role":
                user = await session.get(User, UUID(e.tokens["support"]))
                assert user is not None
                user.user_type = "customer"
                user.customer_account_id = e.other_account
            else:
                report = await session.get(IssueReport, e.report_id)
                assert report is not None
                if change == "archive":
                    report.status = "deleted"
                else:
                    report.description += " Additional observation."
            await session.commit()
    response = await client.post(
        f"/support/issue-reports/{e.report_id}/runs/{saved.run_id}/decision",
        json=reply(saved).model_dump(mode="json"),
    )
    assert (
        response.status_code
        == {"role": 403, "grants": 404, "archive": 409, "input": 409}[change]
    )
    assert not tool.calls


@pytest.mark.anyio
async def test_tool_failure_is_saved_and_never_retried(
    actions: tuple[Environment, SupportActions, AsyncClient, SimulatedCreateTicketTool],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class FailingTool(SimulatedCreateTicketTool):
        async def create_ticket(
            self, arguments: CreateTicketArguments, idempotency_key: UUID
        ) -> SimulatedTicketResult:
            await super().create_ticket(arguments, idempotency_key)
            raise RuntimeError("private adapter details")

    e, service, _, _ = actions
    tool = FailingTool()
    monkeypatch.setattr(service, "tool", lambda: tool)
    saved = await service.prepare("support", e.report_id, draft())
    assert saved.run_id is not None
    outcome = await service.decide("support", e.report_id, saved.run_id, reply(saved))
    assert outcome.status == "execution_unknown" and outcome.decision is not None
    assert "private" not in outcome.model_dump_json()
    assert (
        await service.decide("support", e.report_id, saved.run_id, reply(saved))
    ) == outcome
    assert len(tool.calls) == 1


@pytest.mark.anyio
@pytest.mark.parametrize(
    "token,grants,expected",
    [
        (None, "valid", 401),
        ("unknown", "valid", 401),
        ("customer-a", "valid", 403),
        ("support", "{}", 404),
        ("support", '{"bad":"*"}', 503),
    ],
)
async def test_http_access_for_reads_preparation_and_decisions(
    actions: tuple[Environment, SupportActions, AsyncClient, SimulatedCreateTicketTool],
    monkeypatch: pytest.MonkeyPatch,
    token: str | None,
    grants: str,
    expected: int,
) -> None:
    e, service, client, tool = actions
    saved = await service.prepare("support", e.report_id, draft())
    if grants != "valid":
        monkeypatch.setenv("DEMO_SUPPORT_ACCOUNT_IDS", grants)
    headers = {"Authorization": f"Bearer {token}" if token else ""}
    path = f"/support/issue-reports/{e.report_id}"
    responses = [
        await client.get(f"{path}/action", headers=headers),
        await client.post(
            f"{path}/proposal",
            json=draft(saved).model_dump(mode="json"),
            headers=headers,
        ),
        await client.post(
            f"{path}/runs/{saved.run_id}/decision",
            json=reply(saved).model_dump(mode="json"),
            headers=headers,
        ),
        await client.post(
            f"{path}/runs/{saved.run_id}/recover-execution",
            json=reply(saved).model_dump(mode="json"),
            headers=headers,
        ),
    ]
    assert [response.status_code for response in responses] == [expected] * 4
    assert all("proposed_action" not in response.text for response in responses)
    assert not tool.calls


@pytest.mark.anyio
async def test_report_run_and_payload_bindings(
    actions: tuple[Environment, SupportActions, AsyncClient, SimulatedCreateTicketTool],
) -> None:
    e, service, client, tool = actions
    saved = await service.prepare("support", e.report_id, draft())
    path = f"/support/issue-reports/{e.report_id}"
    assert (
        await client.post(
            f"{path}/runs/{uuid4()}/decision", json=reply(saved).model_dump(mode="json")
        )
    ).status_code == 404
    assert (
        await client.get(f"/support/issue-reports/{uuid4()}/action")
    ).status_code == 404
    invalid = reply(saved).model_dump(mode="json") | {"actor_id": str(uuid4())}
    assert (
        await client.post(f"{path}/runs/{saved.run_id}/decision", json=invalid)
    ).status_code == 422
    assert not tool.calls


@pytest.mark.anyio
async def test_archive_after_decision_preserves_read_and_duplicate_outcome(
    actions: tuple[Environment, SupportActions, AsyncClient, SimulatedCreateTicketTool],
) -> None:
    e, service, _, tool = actions
    saved = await service.prepare("support", e.report_id, draft())
    assert saved.run_id is not None
    decided = await service.decide("support", e.report_id, saved.run_id, reply(saved))
    async with e.sessions() as session:
        report = await session.get(IssueReport, e.report_id)
        assert report is not None
        report.status = "deleted"
        await session.commit()
    read = await service.get("support", e.report_id)
    assert (
        read.archived
        and read.decision == decided.decision
        and read.execution == decided.execution
    )
    assert (
        await service.decide("support", e.report_id, saved.run_id, reply(saved))
    ).execution == decided.execution
    assert len(tool.calls) == 1


@pytest.mark.anyio
async def test_revocation_after_approval_prevents_execution_and_duplicate_retry(
    actions: tuple[Environment, SupportActions, AsyncClient, SimulatedCreateTicketTool],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    e, service, _, tool = actions
    saved = await service.prepare("support", e.report_id, draft())
    assert saved.run_id is not None
    original = service.context
    original_grants = __import__("os").environ["DEMO_SUPPORT_ACCOUNT_IDS"]

    async def revoke_after_receipt(
        token: str, report_id: UUID, row: SupportActionRun, *, fresh: bool
    ):
        async with open_checkpointer(e.url, e.runtime.checkpoint_schema) as saver:
            checkpoint = await saver.aget_tuple(approval_config(row.run_id))
        if (
            fresh
            and checkpoint is not None
            and checkpoint.checkpoint["channel_values"].get("approval") is not None
        ):
            monkeypatch.setenv("DEMO_SUPPORT_ACCOUNT_IDS", "{}")
        return await original(token, report_id, row, fresh=fresh)

    monkeypatch.setattr(service, "context", revoke_after_receipt)
    with pytest.raises(HTTPException) as error:
        await service.decide("support", e.report_id, saved.run_id, reply(saved))
    assert error.value.status_code == 404 and not tool.calls
    monkeypatch.setenv("DEMO_SUPPORT_ACCOUNT_IDS", original_grants)
    monkeypatch.setattr(service, "context", original)
    read = await service.get("support", e.report_id)
    assert read.status == "approved_unconfirmed" and read.decision is not None
    assert (
        await service.decide("support", e.report_id, saved.run_id, reply(saved))
    ).status == "approved_unconfirmed"
    assert not tool.calls


@pytest.mark.anyio
async def test_concurrent_reviewers_preserve_first_accepted_decision(
    actions: tuple[Environment, SupportActions, AsyncClient, SimulatedCreateTicketTool],
) -> None:
    e, service, _, tool = actions
    saved = await service.prepare("support", e.report_id, draft())
    assert saved.run_id is not None
    outcomes = await asyncio.gather(
        service.decide("support", e.report_id, saved.run_id, reply(saved)),
        service.decide("support", e.report_id, saved.run_id, reply(saved, "reject")),
        return_exceptions=True,
    )
    final = await service.get("support", e.report_id)
    assert final.status in ("rejected", "simulated_success")
    assert any(
        isinstance(outcome, SupportAction) and outcome.decision == final.decision
        for outcome in outcomes
    )
    assert len(tool.calls) == (1 if final.status == "simulated_success" else 0)


@pytest.mark.anyio
async def test_preparation_replay_after_checkpoint_before_publication(
    actions: tuple[Environment, SupportActions, AsyncClient, SimulatedCreateTicketTool],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    e, service, _, tool = actions
    initialize = service.initialize

    async def interrupt(token: str, report_id: UUID, row: SupportActionRun) -> None:
        await initialize(token, report_id, row)
        raise asyncio.CancelledError()

    monkeypatch.setattr(service, "initialize", interrupt)
    body = draft()
    with pytest.raises(asyncio.CancelledError):
        await service.prepare("support", e.report_id, body)
    pending = await service.get("support", e.report_id)
    assert pending.status == "preparing"
    monkeypatch.setattr(service, "initialize", initialize)
    saved = await service.prepare("support", e.report_id, body)
    assert (
        saved.proposal == pending.proposal
        and len(saved.timeline) == 1
        and not tool.calls
    )


@pytest.mark.anyio
async def test_changed_input_can_finish_preparation_but_requires_a_new_review_version(
    actions: tuple[Environment, SupportActions, AsyncClient, SimulatedCreateTicketTool],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    e, service, _, tool = actions
    initialize = service.initialize

    async def interrupted(token: str, report_id: UUID, row: SupportActionRun) -> None:
        raise asyncio.CancelledError()

    monkeypatch.setattr(service, "initialize", interrupted)
    body = draft()
    with pytest.raises(asyncio.CancelledError):
        await service.prepare("support", e.report_id, body)
    async with e.sessions() as session:
        report = await session.get(IssueReport, e.report_id)
        assert report is not None
        report.description += " New observation."
        await session.commit()
    monkeypatch.setattr(service, "initialize", initialize)
    stale = await service.prepare("support", e.report_id, body)
    assert (
        stale.input_stale
        and stale.status == "awaiting_decision"
        and stale.run_id is not None
    )
    with pytest.raises(HTTPException) as error:
        await service.decide("support", e.report_id, stale.run_id, reply(stale))
    assert error.value.status_code == 409 and not tool.calls
    current = await service.prepare("support", e.report_id, draft(stale))
    assert (
        not current.input_stale
        and current.proposal is not None
        and current.proposal.version == 2
    )


@pytest.mark.anyio
async def test_proposal_requires_completed_intake_and_active_report(
    actions: tuple[Environment, SupportActions, AsyncClient, SimulatedCreateTicketTool],
) -> None:
    e, service, _, tool = actions
    async with e.sessions() as session:
        original = await session.get(IssueReport, e.report_id)
        assert original is not None
        other = IssueReport(
            customer_account_id=original.customer_account_id,
            submitted_by_user_id=e.user_id,
            description="Another report",
            status="submitted",
        )
        session.add(other)
        await session.commit()
    absent = await service.get("support", other.id)
    assert absent.status == "absent" and not absent.can_prepare
    with pytest.raises(HTTPException) as error:
        await service.prepare("support", other.id, draft())
    assert error.value.status_code == 409
    await e.service().start(other.id)
    assert not (await service.get("support", other.id)).can_prepare
    with pytest.raises(HTTPException) as error:
        await service.prepare("support", other.id, draft())
    assert error.value.status_code == 409
    assert not tool.calls


@pytest.mark.anyio
async def test_invalid_saved_registry_fails_closed(
    actions: tuple[Environment, SupportActions, AsyncClient, SimulatedCreateTicketTool],
) -> None:
    e, service, client, tool = actions
    saved = await service.prepare("support", e.report_id, draft())
    async with e.sessions() as session:
        row = await session.get(SupportActionRun, saved.run_id)
        assert row is not None
        row.input_hash = "0" * 64
        await session.commit()
    path = f"/support/issue-reports/{e.report_id}"
    assert (await client.get(f"{path}/action")).status_code == 503
    assert (
        await client.post(
            f"{path}/runs/{saved.run_id}/decision",
            json=reply(saved).model_dump(mode="json"),
        )
    ).status_code == 503
    assert not tool.calls
