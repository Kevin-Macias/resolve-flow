"""First decision wins across duplicate, concurrent, resumed, and failed calls."""

import asyncio
from uuid import UUID, uuid4

import pytest
from langgraph.checkpoint.memory import (
    InMemorySaver,  # pyright: ignore[reportMissingTypeStubs]
)

from api.identity.context import RequestContext
from api.workflow.actions import (
    ActionRisk,
    CreateTicketArguments,
    ProposedAction,
    RiskLevel,
    propose_create_ticket,
)
from api.workflow.approval import ApprovalChoice
from api.workflow.approval_graph import approval_config, build_approval_stage
from api.workflow.approval_runner import ApprovalRunner, MemoryRunLocks
from api.workflow.checkpoints import checkpoint_serializer
from api.workflow.execution import SimulatedCreateTicketTool, SimulatedTicketResult
from api.workflow.state import ApprovalInput, ReportStatus
from api.workflow.timeline import EventType


@pytest.fixture
def anyio_backend() -> str:
    return "asyncio"


def action() -> ProposedAction:
    return propose_create_ticket(
        CreateTicketArguments(
            issue_report_id=uuid4(),
            title="Synthetic",
            description="Synthetic report",
            service_code=None,
            severity=None,
        ),
        explanation="Support review",
        expected_effect="Simulation",
        risk=ActionRisk(level=RiskLevel.LOW, reason="Simulation"),
    )


def reply(proposal: ProposedAction, choice: str = "approve") -> dict[str, object]:
    return {
        "action_id": str(proposal.action_id),
        "version": proposal.version,
        "fingerprint": proposal.fingerprint(),
        "decision": choice,
    }


class FailingTool(SimulatedCreateTicketTool):
    def __init__(self, after_call: bool) -> None:
        super().__init__()
        self.after_call = after_call
        self.attempts = 0

    async def create_ticket(
        self, arguments: CreateTicketArguments, idempotency_key: UUID
    ) -> SimulatedTicketResult:
        self.attempts += 1
        if self.after_call:
            await super().create_ticket(arguments, idempotency_key)
        raise RuntimeError("Private adapter details must not escape")


@pytest.mark.anyio
@pytest.mark.parametrize("first", ["approve", "reject"])
async def test_duplicate_and_conflicting_decisions_return_first_outcome(
    first: str,
) -> None:
    proposal, run_id = action(), uuid4()
    allowed = True

    async def context(_: UUID) -> RequestContext:
        if not allowed:
            raise PermissionError("Revoked")
        return RequestContext(uuid4(), "support", None)

    tool = SimulatedCreateTicketTool()
    saver = InMemorySaver(serde=checkpoint_serializer())
    stage = build_approval_stage(context, checkpointer=saver, tool=tool)
    locks = MemoryRunLocks()
    runner = ApprovalRunner(stage, context, locks)
    await stage.ainvoke(  
        ApprovalInput(
            workflow_run_id=run_id,
            issue_report_id=proposal.arguments.issue_report_id,
            proposed_action=proposal,
        ),
        approval_config(run_id),
    )  
    saved = await runner.submit(run_id, reply(proposal, first))
    assert await runner.submit(run_id, reply(proposal, first)) == saved
    opposite = "reject" if first == "approve" else "approve"
    assert await runner.submit(run_id, reply(proposal, opposite)) == saved
    # Rebuild the graph/runner over restored checkpoints and actually submit.
    restored = ApprovalRunner(
        build_approval_stage(context, checkpointer=saver, tool=tool), context, locks
    )
    assert await restored.submit(run_id, reply(proposal)) == saved
    assert len(tool.calls) == (1 if first == "approve" else 0)
    assert "approval" in saved
    assert saved["approval"].decision == ApprovalChoice(first)
    assert [event.event_type for event in saved["timeline"]] == (
        [
            EventType.APPROVAL_REQUESTED,
            EventType.ACTION_APPROVED,
            EventType.TOOL_SUCCEEDED,
        ]
        if first == "approve"
        else [EventType.APPROVAL_REQUESTED, EventType.ACTION_REJECTED]
    )
    allowed = False
    with pytest.raises(PermissionError):
        await restored.submit(run_id, reply(proposal))


@pytest.mark.anyio
@pytest.mark.parametrize("second", ["approve", "reject"])
async def test_concurrent_submissions_cannot_execute_twice(second: str) -> None:
    proposal, run_id = action(), uuid4()
    entered, release = asyncio.Event(), asyncio.Event()

    class BlockingTool(SimulatedCreateTicketTool):
        async def create_ticket(
            self, arguments: CreateTicketArguments, idempotency_key: UUID
        ) -> SimulatedTicketResult:
            entered.set()
            await release.wait()
            return await super().create_ticket(arguments, idempotency_key)

    async def context(_: UUID) -> RequestContext:
        return RequestContext(uuid4(), "support", None)

    tool = BlockingTool()
    stage = build_approval_stage(context, tool=tool)
    locks = MemoryRunLocks()
    runner = ApprovalRunner(stage, context, locks)
    other = ApprovalRunner(stage, context, locks)
    await stage.ainvoke(  
        ApprovalInput(
            workflow_run_id=run_id,
            issue_report_id=proposal.arguments.issue_report_id,
            proposed_action=proposal,
        ),
        approval_config(run_id),
    )  
    first = asyncio.create_task(runner.submit(run_id, reply(proposal)))
    await asyncio.wait_for(entered.wait(), timeout=5)
    concurrent = asyncio.create_task(other.submit(run_id, reply(proposal, second)))
    await asyncio.sleep(0)
    assert not concurrent.done()
    release.set()
    results = await asyncio.gather(first, concurrent)
    assert results[0] == results[1]
    assert len(tool.calls) == 1


@pytest.mark.anyio
@pytest.mark.parametrize("after_call", [False, True])
async def test_tool_failure_is_saved_sanitized_and_never_automatically_retried(
    after_call: bool,
) -> None:
    proposal, run_id = action(), uuid4()

    async def context(_: UUID) -> RequestContext:
        return RequestContext(uuid4(), "support", None)

    tool = FailingTool(after_call)
    saver = InMemorySaver(serde=checkpoint_serializer())
    stage = build_approval_stage(context, checkpointer=saver, tool=tool)
    locks = MemoryRunLocks()
    runner = ApprovalRunner(stage, context, locks)
    await stage.ainvoke(  
        ApprovalInput(
            workflow_run_id=run_id,
            issue_report_id=proposal.arguments.issue_report_id,
            proposed_action=proposal,
        ),
        approval_config(run_id),
    )  
    saved = await runner.submit(run_id, reply(proposal))
    assert "tool_failure" in saved
    assert "customer_update" in saved
    assert saved["tool_failure"].outcome == "unknown"
    assert saved["tool_failure"].idempotency_key == proposal.idempotency_key
    assert saved["customer_update"].status == ReportStatus.TOOL_EXECUTION_FAILED
    assert "Private" not in repr(saved)
    assert "tool_execution" not in saved
    assert "support_ticket_id" not in saved
    restored = ApprovalRunner(
        build_approval_stage(context, checkpointer=saver, tool=tool), context, locks
    )
    assert await restored.submit(run_id, reply(proposal)) == saved
    assert [event.event_type for event in saved["timeline"]] == [
        EventType.APPROVAL_REQUESTED,
        EventType.ACTION_APPROVED,
        EventType.TOOL_FAILED,
    ]
    assert saved["timeline"][-1].metadata.outcome == "unknown"
    assert tool.attempts == 1
    assert len(tool.calls) == int(after_call)


@pytest.mark.anyio
@pytest.mark.parametrize("field", ["action_id", "version", "fingerprint"])
async def test_stale_submission_never_advances_or_calls_tool(field: str) -> None:
    proposal, run_id = action(), uuid4()

    async def context(_: UUID) -> RequestContext:
        return RequestContext(uuid4(), "support", None)

    tool = SimulatedCreateTicketTool()
    stage = build_approval_stage(context, tool=tool)
    runner = ApprovalRunner(stage, context, MemoryRunLocks())
    await stage.ainvoke(  
        ApprovalInput(
            workflow_run_id=run_id,
            issue_report_id=proposal.arguments.issue_report_id,
            proposed_action=proposal,
        ),
        approval_config(run_id),
    )  
    invalid = reply(proposal)
    invalid[field] = {"action_id": str(uuid4()), "version": 2, "fingerprint": "0" * 64}[
        field
    ]
    with pytest.raises(ValueError, match="stale"):
        await runner.submit(run_id, invalid)
    snapshot = await stage.aget_state(approval_config(run_id))
    assert "approval" not in snapshot.values
    assert len(snapshot.values["timeline"]) == 1
    assert any(task.interrupts for task in snapshot.tasks)
    assert tool.calls == []


@pytest.mark.anyio
async def test_changed_arguments_with_same_id_and_version_reject_old_reply() -> None:
    proposal, run_id = action(), uuid4()

    async def context(_: UUID) -> RequestContext:
        return RequestContext(uuid4(), "support", None)

    tool = SimulatedCreateTicketTool()
    stage = build_approval_stage(context, tool=tool)
    runner = ApprovalRunner(stage, context, MemoryRunLocks())
    await stage.ainvoke(  
        ApprovalInput(
            workflow_run_id=run_id,
            issue_report_id=proposal.arguments.issue_report_id,
            proposed_action=proposal,
        ),
        approval_config(run_id),
    )
    payload = proposal.model_dump(mode="json")
    payload["arguments"]["title"] = "Changed title"
    changed = ProposedAction.model_validate(payload)
    await stage.aupdate_state(
        approval_config(run_id), {"proposed_action": changed}, as_node="__start__"
    )
    with pytest.raises(ValueError, match="stale"):
        await runner.submit(run_id, reply(proposal))
    assert tool.calls == []
    # Updating trusted state schedules review again; establish its fresh pause
    # before accepting a decision against the new snapshot.
    with pytest.raises(ValueError, match="not awaiting"):
        await runner.submit(run_id, reply(changed))
    await stage.ainvoke(None, approval_config(run_id))  
    saved = await runner.submit(run_id, reply(changed))
    assert "tool_execution" in saved
    assert saved["tool_execution"].fingerprint == changed.fingerprint()
    assert tool.calls == [(changed.arguments, changed.idempotency_key)]


@pytest.mark.anyio
async def test_saved_approval_with_interrupted_execution_does_not_trigger_retry() -> (
    None
):
    proposal, run_id = action(), uuid4()
    checks = 0

    async def context(_: UUID) -> RequestContext:
        nonlocal checks
        checks += 1
        # Start, runner access, review resume, then execution access.
        if checks == 4:
            raise PermissionError("Execution access revoked")
        return RequestContext(uuid4(), "support", None)

    tool = SimulatedCreateTicketTool()
    stage = build_approval_stage(context, tool=tool)
    runner = ApprovalRunner(stage, context, MemoryRunLocks())
    await stage.ainvoke(  
        ApprovalInput(
            workflow_run_id=run_id,
            issue_report_id=proposal.arguments.issue_report_id,
            proposed_action=proposal,
        ),
        approval_config(run_id),
    )
    with pytest.raises(PermissionError):
        await runner.submit(run_id, reply(proposal))
    saved = await runner.submit(run_id, reply(proposal))
    assert "approval" in saved
    assert "tool_execution" not in saved
    assert "support_ticket_id" not in saved
    assert tool.calls == []


@pytest.mark.anyio
async def test_unknown_run_and_customer_submission_cannot_execute() -> None:
    proposal, run_id = action(), uuid4()
    customer = False

    async def context(_: UUID) -> RequestContext:
        return RequestContext(uuid4(), "customer" if customer else "support", None)

    tool = SimulatedCreateTicketTool()
    stage = build_approval_stage(context, tool=tool)
    runner = ApprovalRunner(stage, context, MemoryRunLocks())
    with pytest.raises(ValueError, match="does not exist"):
        await runner.submit(run_id, reply(proposal))
    await stage.ainvoke(  
        ApprovalInput(
            workflow_run_id=run_id,
            issue_report_id=proposal.arguments.issue_report_id,
            proposed_action=proposal,
        ),
        approval_config(run_id),
    )
    customer = True
    with pytest.raises(PermissionError):
        await runner.submit(run_id, reply(proposal))
    assert tool.calls == []


@pytest.mark.anyio
async def test_changed_proposal_after_decision_cannot_reuse_saved_outcome() -> None:
    proposal, run_id = action(), uuid4()

    async def context(_: UUID) -> RequestContext:
        return RequestContext(uuid4(), "support", None)

    tool = SimulatedCreateTicketTool()
    stage = build_approval_stage(context, tool=tool)
    runner = ApprovalRunner(stage, context, MemoryRunLocks())
    await stage.ainvoke(  
        ApprovalInput(
            workflow_run_id=run_id,
            issue_report_id=proposal.arguments.issue_report_id,
            proposed_action=proposal,
        ),
        approval_config(run_id),
    )
    await runner.submit(run_id, reply(proposal))
    payload = proposal.model_dump(mode="json")
    payload["arguments"]["title"] = "Changed after execution"
    changed = ProposedAction.model_validate(payload)
    await stage.aupdate_state(
        approval_config(run_id), {"proposed_action": changed}, as_node="__start__"
    )
    with pytest.raises(ValueError, match="different proposal"):
        await runner.submit(run_id, reply(changed))
    assert len(tool.calls) == 1
