"""The simulated tool is reachable only through validated application execution."""

from uuid import UUID, uuid4

import pytest
from langgraph.types import Command  # pyright: ignore[reportMissingTypeStubs]
from pydantic import ValidationError

from api.identity.context import RequestContext
from api.workflow.actions import (
    ActionRisk,
    CreateTicketArguments,
    ProposedAction,
    RiskLevel,
    propose_create_ticket,
    revise_create_ticket,
)
from api.workflow.approval import ApprovalDecision, ApprovalReply, record_approval
from api.workflow.approval_graph import approval_config, build_approval_stage
from api.workflow.checkpoints import checkpoint_serializer
from api.workflow.execution import (
    SimulatedCreateTicketTool,
    ToolExecutionResult,
    execute_approved_action,
)
from api.workflow.state import ApprovalInput, ReportStatus


@pytest.fixture
def anyio_backend() -> str:
    return "asyncio"


def proposal() -> ProposedAction:
    return propose_create_ticket(
        CreateTicketArguments(
            issue_report_id=uuid4(),
            title="Pending payments",
            description="Synthetic private report",
            service_code=None,
            severity=None,
        ),
        explanation="Support investigation",
        expected_effect="Simulated ticket creation",
        risk=ActionRisk(level=RiskLevel.LOW, reason="Simulation"),
    )


def reply(action: ProposedAction, decision: str = "approve") -> dict[str, object]:
    return {
        "action_id": str(action.action_id),
        "version": action.version,
        "fingerprint": action.fingerprint(),
        "decision": decision,
    }


def approval(action: ProposedAction, decision: str = "approve") -> ApprovalDecision:
    return record_approval(
        ApprovalReply.model_validate(reply(action, decision)),
        action,
        RequestContext(uuid4(), "support", None),
    )


@pytest.mark.anyio
async def test_deterministic_fake_result_and_typed_execution_record() -> None:
    action = proposal()
    decision = approval(action)
    actor = RequestContext(uuid4(), "support", None)
    tool = SimulatedCreateTicketTool()
    first = await execute_approved_action(action, decision, actor, tool)
    second = await execute_approved_action(action, decision, actor, tool)
    assert first == second
    assert first.result.simulated is True
    assert first.result.status == "open"
    assert first.idempotency_key == action.idempotency_key
    assert first.fingerprint == action.fingerprint()
    assert first.executed_by_user_id == actor.user_id
    assert tool.calls == [(action.arguments, action.idempotency_key)] * 2
    revised = revise_create_ticket(
        action,
        action.arguments,
        explanation="Revised rationale",
        expected_effect=action.expected_effect,
        risk=action.risk,
    )
    third = await execute_approved_action(revised, approval(revised), actor, tool)
    assert third.result.support_ticket_id != first.result.support_ticket_id
    serde = checkpoint_serializer()
    restored: object = serde.loads_typed(serde.dumps_typed(first))
    assert isinstance(restored, ToolExecutionResult)
    assert restored == first


@pytest.mark.anyio
@pytest.mark.parametrize(
    "case", ["missing", "rejected", "revised", "changed_arguments", "customer"]
)
async def test_denied_execution_never_calls_tool(case: str) -> None:
    action = proposal()
    decision: ApprovalDecision | None = approval(action)
    actor = RequestContext(uuid4(), "support", None)
    tool = SimulatedCreateTicketTool()
    if case == "missing":
        decision = None
    elif case == "rejected":
        decision = approval(action, "reject")
    elif case == "revised":
        action = revise_create_ticket(
            action,
            action.arguments,
            explanation="Changed",
            expected_effect=action.expected_effect,
            risk=action.risk,
        )
    elif case == "changed_arguments":
        payload = action.model_dump(mode="json")
        payload["arguments"]["title"] = "Changed"
        action = ProposedAction.model_validate(payload)
    elif case == "customer":
        actor = RequestContext(uuid4(), "customer", uuid4())
    with pytest.raises(PermissionError):
        await execute_approved_action(action, decision, actor, tool)
    assert tool.calls == []


@pytest.mark.anyio
async def test_unvalidated_arguments_fail_before_adapter_call() -> None:
    action = proposal()
    decision = approval(action)
    tool = SimulatedCreateTicketTool()
    invalid = action.model_copy(
        update={"arguments": action.arguments.model_copy(update={"title": " "})}
    )
    with pytest.raises(ValidationError):
        await execute_approved_action(
            invalid, decision, RequestContext(uuid4(), "support", None), tool
        )
    assert tool.calls == []


@pytest.mark.anyio
@pytest.mark.parametrize("choice", ["approve", "reject"])
async def test_stage_runs_tool_only_after_approval(choice: str) -> None:
    action = proposal()
    actor = RequestContext(uuid4(), "support", None)
    calls: list[UUID] = []

    async def context(report_id: UUID) -> RequestContext:
        calls.append(report_id)
        return actor

    tool = SimulatedCreateTicketTool()
    stage = build_approval_stage(context, tool=tool)
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
    assert tool.calls == []
    state = await stage.ainvoke(Command(resume=reply(action, choice)), config)  
    if choice == "reject":
        assert tool.calls == []
        assert "tool_execution" not in state
        assert "support_ticket_id" not in state
        assert state["customer_update"].status is ReportStatus.ACTION_REJECTED
        assert len(calls) == 2
    else:
        assert len(tool.calls) == 1
        assert len(calls) == 3
        assert state["tool_execution"].result.simulated is True
        assert (
            state["support_ticket_id"]
            == state["tool_execution"].result.support_ticket_id
        )
        assert state["customer_update"].status is ReportStatus.SIMULATED_TICKET_CREATED
        assert "simulated" in state["customer_update"].message.lower()
        assert "private" not in state["customer_update"].message
    snapshot = await stage.aget_state(config)
    assert snapshot.next == ()


@pytest.mark.anyio
async def test_access_is_rechecked_between_approval_and_execution() -> None:
    action = proposal()
    checks = 0

    async def context(report_id: UUID) -> RequestContext:
        nonlocal checks
        checks += 1
        if checks == 3:
            raise PermissionError("Execution access revoked")
        return RequestContext(uuid4(), "support", None)

    tool = SimulatedCreateTicketTool()
    stage = build_approval_stage(context, tool=tool)
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
    with pytest.raises(PermissionError):
        await stage.ainvoke(Command(resume=reply(action)), config)  
    snapshot = await stage.aget_state(config)
    assert snapshot.values["approval"].permits(action)
    assert "tool_execution" not in snapshot.values
    assert "support_ticket_id" not in snapshot.values
    assert tool.calls == []
