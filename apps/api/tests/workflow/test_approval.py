"""Approval decisions require current support identity and exact saved content."""

from typing import cast
from uuid import UUID, uuid4

import pytest
from langgraph.types import Command  # pyright: ignore[reportMissingTypeStubs]

from api.identity.context import RequestContext
from api.workflow.actions import (
    ActionRisk,
    CreateTicketArguments,
    ProposedAction,
    RiskLevel,
    propose_create_ticket,
    revise_create_ticket,
)
from api.workflow.approval import (
    ApprovalChoice,
    ApprovalDecision,
    ApprovalReply,
    record_approval,
)
from api.workflow.approval_graph import approval_config, build_approval_stage
from api.workflow.checkpoints import checkpoint_serializer
from api.workflow.state import ApprovalInput, ApprovalState, ReportStatus


@pytest.fixture
def anyio_backend() -> str:
    return "asyncio"


def proposal() -> ProposedAction:
    return propose_create_ticket(
        CreateTicketArguments(
            issue_report_id=uuid4(),
            title="Pending payments",
            description="Synthetic customer report",
            service_code=None,
            severity=None,
        ),
        explanation="Investigate customer report",
        expected_effect="Create an internal ticket",
        risk=ActionRisk(level=RiskLevel.LOW, reason="Simulated ticket only"),
    )


def reply(action: ProposedAction, decision: str = "approve") -> dict[str, object]:
    return {
        "action_id": str(action.action_id),
        "version": action.version,
        "fingerprint": action.fingerprint(),
        "decision": decision,
    }


@pytest.mark.anyio
@pytest.mark.parametrize("choice", ["approve", "reject"])
async def test_pause_then_record_exact_decision_with_server_identity(
    choice: str,
) -> None:
    action = proposal()
    actor = RequestContext(uuid4(), "support", None)
    calls: list[UUID] = []

    async def context(report_id: UUID) -> RequestContext:
        calls.append(report_id)
        return actor

    stage = build_approval_stage(context)
    config = approval_config(uuid4())
    state = await stage.ainvoke(  
        ApprovalInput(
            workflow_run_id=uuid4(),
            issue_report_id=action.arguments.issue_report_id,
            proposed_action=action,
        ),
        config,
    )
    assert "approval" not in state
    interrupt = state["__interrupt__"][0].value
    assert interrupt["proposal"] == action.model_dump(mode="json")
    assert interrupt["fingerprint"] == action.fingerprint()
    result = await stage.ainvoke(Command(resume=reply(action, choice)), config)  
    state = cast(ApprovalState, result)
    decision = state.get("approval")
    assert isinstance(decision, ApprovalDecision)
    assert decision.actor_id == actor.user_id
    assert decision.decided_at.utcoffset() is not None
    assert decision.decision is (
        ApprovalChoice.APPROVE if choice == "approve" else ApprovalChoice.REJECT
    )
    assert decision.permits(action) is (choice == "approve")
    update = state.get("customer_update")
    assert update is not None
    assert update.status is (
        ReportStatus.AWAITING_EXECUTION
        if choice == "approve"
        else ReportStatus.ACTION_REJECTED
    )
    assert "Synthetic" not in update.message
    snapshot = await stage.aget_state(config)
    assert snapshot.next == ()
    assert "support_ticket_id" not in snapshot.values
    assert calls == [action.arguments.issue_report_id] * 2
    serde = checkpoint_serializer()
    restored: object = serde.loads_typed(serde.dumps_typed(decision))
    assert isinstance(restored, ApprovalDecision)
    assert restored == decision
    assert restored.permits(action) is (choice == "approve")


@pytest.mark.anyio
@pytest.mark.parametrize(
    "invalid", ["id", "version", "hash", "bool", "actor", "time", "arguments"]
)
async def test_invalid_or_stale_reply_keeps_stage_paused(invalid: str) -> None:
    action = proposal()

    async def context(report_id: UUID) -> RequestContext:
        return RequestContext(uuid4(), "support", None)

    stage = build_approval_stage(context)
    run_id = uuid4()
    config = approval_config(run_id)
    await stage.ainvoke(  
        ApprovalInput(
            workflow_run_id=run_id,
            issue_report_id=action.arguments.issue_report_id,
            proposed_action=action,
        ),
        config,
    )
    payload = reply(action)
    if invalid == "id":
        payload["action_id"] = str(uuid4())
    elif invalid == "version":
        payload["version"] = action.version + 1
    elif invalid == "hash":
        payload["fingerprint"] = "0" * 64
    elif invalid == "actor":
        payload["actor_id"] = str(uuid4())
    elif invalid == "time":
        payload["decided_at"] = "2026-09-26T00:00:00Z"
    elif invalid == "arguments":
        payload["arguments"] = {"title": "Changed"}
    raw: object = True if invalid == "bool" else payload
    state = await stage.ainvoke(Command(resume=raw), config)  
    assert "approval" not in state
    assert state["__interrupt__"][0].value["error"] == "invalid_or_stale_approval"
    snapshot = await stage.aget_state(config)
    assert any(task.interrupts for task in snapshot.tasks)
    state = await stage.ainvoke(Command(resume=reply(action)), config)  
    assert state["approval"].permits(action)


@pytest.mark.anyio
async def test_customer_cannot_review_and_revoked_access_cannot_resume() -> None:
    action = proposal()
    actor = RequestContext(uuid4(), "customer", uuid4())
    allowed = True

    async def context(report_id: UUID) -> RequestContext:
        if not allowed:
            raise PermissionError("Report access revoked")
        return actor

    stage = build_approval_stage(context)
    config = approval_config(uuid4())
    inputs = ApprovalInput(
        workflow_run_id=uuid4(),
        issue_report_id=action.arguments.issue_report_id,
        proposed_action=action,
    )
    with pytest.raises(PermissionError):
        await stage.ainvoke(inputs, config)  
    actor = RequestContext(uuid4(), "support", None)
    config = approval_config(uuid4())
    await stage.ainvoke(inputs, config)  
    allowed = False
    with pytest.raises(PermissionError):
        await stage.ainvoke(Command(resume=reply(action)), config)  
    snapshot = await stage.aget_state(config)
    assert "approval" not in snapshot.values


@pytest.mark.anyio
async def test_changed_proposal_requires_approval_of_the_new_snapshot() -> None:
    action = proposal()

    async def context(report_id: UUID) -> RequestContext:
        return RequestContext(uuid4(), "support", None)

    stage = build_approval_stage(context)
    config = approval_config(uuid4())
    await stage.ainvoke(  
        ApprovalInput(
            workflow_run_id=uuid4(),
            issue_report_id=action.arguments.issue_report_id,
            proposed_action=action,
        ),
        config,
    )
    revised = revise_create_ticket(
        action,
        action.arguments,
        explanation="Revised rationale",
        expected_effect=action.expected_effect,
        risk=action.risk,
    )
    # Trusted application revision; this API is never exposed to client commands.
    await stage.aupdate_state(config, {"proposed_action": revised}, as_node="__start__")
    state = await stage.ainvoke(Command(resume=reply(action)), config)  
    assert "approval" not in state
    state = await stage.ainvoke(Command(resume=reply(revised)), config)  
    decision = state["approval"]
    assert decision.permits(revised)
    assert not decision.permits(action)


@pytest.mark.anyio
async def test_proposal_must_belong_to_the_run_report() -> None:
    async def context(report_id: UUID) -> RequestContext:
        return RequestContext(uuid4(), "support", None)

    stage = build_approval_stage(context)
    with pytest.raises(ValueError, match="belong"):
        await stage.ainvoke(  
            ApprovalInput(
                workflow_run_id=uuid4(),
                issue_report_id=uuid4(),
                proposed_action=proposal(),
            ),
            approval_config(uuid4()),
        )


def test_approval_never_permits_changed_arguments_even_with_same_id_and_version() -> (
    None
):
    action = proposal()
    decision = record_approval(
        ApprovalReply.model_validate(reply(action)),
        action,
        RequestContext(uuid4(), "support", None),
    )
    payload = action.model_dump(mode="json")
    payload["arguments"]["title"] = "Different ticket"
    changed = ProposedAction.model_validate(payload)
    assert changed.action_id == action.action_id
    assert changed.version == action.version
    assert not decision.permits(changed)


def test_recording_checks_role_and_current_snapshot_again() -> None:
    action = proposal()
    valid_reply = ApprovalReply.model_validate(reply(action))
    with pytest.raises(PermissionError):
        record_approval(
            valid_reply, action, RequestContext(uuid4(), "customer", uuid4())
        )
    payload = reply(action)
    payload["version"] = 2
    with pytest.raises(ValueError, match="current proposal"):
        record_approval(
            ApprovalReply.model_validate(payload),
            action,
            RequestContext(uuid4(), "support", None),
        )
