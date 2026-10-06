"""Separate-process fixture for restart tests; no live model or customer data."""

import asyncio
import json
import os
import sys
from dataclasses import is_dataclass
from typing import cast
from uuid import UUID, uuid5

from langgraph.types import Command  # pyright: ignore[reportMissingTypeStubs]
from pydantic import BaseModel

from api.extraction.clarification import ClarificationDecision
from api.extraction.provider import ModelSettings, ProviderResult
from api.extraction.schemas import Confidence, ExtractionResult
from api.extraction.service import ExtractionCallRecord
from api.identity.context import RequestContext
from api.workflow.actions import (
    ActionRisk,
    CreateTicketArguments,
    ProposedAction,
    RiskLevel,
    propose_create_ticket,
)
from api.workflow.approval import ApprovalDecision
from api.workflow.approval_graph import approval_config, build_approval_stage
from api.workflow.approval_runner import ApprovalRunner, PostgresRunLocks
from api.workflow.checkpoints import open_checkpointer, workflow_config
from api.workflow.clarification import ClarificationTurn, PendingClarification
from api.workflow.execution import (
    SimulatedCreateTicketTool,
    SimulatedTicketResult,
    ToolExecutionFailure,
    ToolExecutionResult,
)
from api.workflow.graph import build_workflow
from api.workflow.state import (
    ApprovalInput,
    CustomerSafeReport,
    WorkflowInput,
    WorkflowState,
)
from api.workflow.timeline import ExecutionEvent


class WorkerProvider:
    settings = ModelSettings(model="fake-restart", reasoning_effort="low")
    calls = 0

    def __init__(self, mode: str) -> None:
        self.mode = mode

    async def generate(
        self,
        instructions: str,
        input_text: str,
        output_schema: type[BaseModel] | None = None,
    ) -> ProviderResult:
        assert self.mode in {"start", "answer"}, "Resume repeated extraction"
        self.calls += 1
        if self.mode == "answer":
            data = json.loads(input_text)
            assert data["original_report"] == "Synthetic pending payment report"
            assert data["clarification_turns"][0]["answers"] == ["Two payments"]
        return ProviderResult(
            text=ExtractionResult(
                summary="Customer reports pending payments",
                service_code="payments",
                severity=None,
                confidence=Confidence.HIGH,
                reported_facts=["Customer reports pending payments"],
                missing_data=["Final outcome"],
                contradictions=[],
                questions=["What was the final outcome?"]
                if self.mode == "answer"
                else ["How many payments?"],
            ).model_dump_json()
        )


async def run(mode: str, run_id: UUID, report_id: UUID, schema: str) -> None:
    if mode.startswith(("approval-", "tool-")):
        await run_approval(mode, run_id, report_id, schema)
        return

    async def load(identifier: UUID) -> str:
        assert identifier == report_id
        return "Synthetic pending payment report"

    provider = WorkerProvider(mode)
    config = workflow_config(run_id)
    async with open_checkpointer(os.environ["TEST_DATABASE_URL"], schema) as saver:
        graph = build_workflow(load, provider, checkpointer=saver)
        if mode == "start":
            await graph.ainvoke(
                WorkflowInput(workflow_run_id=run_id, issue_report_id=report_id),
                config,
                durability="sync",
            )
        else:
            snapshot = await graph.aget_state(config)
            state = cast(WorkflowState, snapshot.values)
            assert state["workflow_run_id"] == run_id
            assert state["issue_report_id"] == report_id
            assert isinstance(state.get("extraction"), ExtractionResult)
            assert isinstance(state.get("extraction_call"), ExtractionCallRecord)
            assert isinstance(state.get("clarification"), ClarificationDecision)
            assert isinstance(state.get("customer_update"), CustomerSafeReport)
            pending = state.get("pending_clarification")
            if mode != "inspect":
                assert isinstance(pending, PendingClarification)
                # Polling a restored pause must preserve its ID without extraction.
                await graph.ainvoke(None, config, durability="sync")
                polled = await graph.aget_state(config)
                assert polled.values["pending_clarification"] == pending
                payload: dict[str, object] = {
                    "pending_id": str(pending.pending_id),
                    "action": "answer" if mode == "answer" else "continue_incomplete",
                }
                if mode == "answer":
                    payload["answers"] = ["Two payments"]
                await graph.ainvoke(
                    Command(resume=payload),
                    config,
                    durability="sync",
                )
        snapshot = await graph.aget_state(config)
        state = cast(WorkflowState, snapshot.values)
        pending = state.get("pending_clarification")
        call = state.get("extraction_call")
        assert isinstance(call, ExtractionCallRecord)
        assert all(isinstance(event, ExecutionEvent) for event in state["timeline"])
        turns = state.get("clarification_turns", ())
        assert all(isinstance(turn, ClarificationTurn) for turn in turns)
        if mode == "inspect":
            assert is_dataclass(state.get("diagnosis"))
            assert snapshot.next == ()
        print(
            json.dumps(
                {
                    "run_id": str(state["workflow_run_id"]),
                    "report_id": str(state["issue_report_id"]),
                    "pending": pending.model_dump(mode="json") if pending else None,
                    "turn_count": len(turns),
                    "model_calls": provider.calls,
                    "prompt_version": call.prompt_version,
                    "model": call.model_settings.model,
                    "continued_incomplete": state.get("continued_incomplete", False),
                    "next": snapshot.next,
                    "timeline": [
                        event.model_dump(mode="json") for event in state["timeline"]
                    ],
                }
            )
        )


async def run_approval(mode: str, run_id: UUID, report_id: UUID, schema: str) -> None:
    actor_id = uuid5(run_id, "synthetic-support-actor")
    step = mode.split("-", 1)[1]

    class FailingTool(SimulatedCreateTicketTool):
        async def create_ticket(
            self, arguments: CreateTicketArguments, idempotency_key: UUID
        ) -> SimulatedTicketResult:
            await super().create_ticket(arguments, idempotency_key)
            raise RuntimeError("Synthetic private failure")

    tool = (
        FailingTool()
        if step in {"fail", "failed-replay"}
        else SimulatedCreateTicketTool()
        if mode.startswith("tool-")
        else None
    )

    async def context(identifier: UUID) -> RequestContext:
        assert identifier == report_id
        return RequestContext(actor_id, "support", None)

    config = approval_config(run_id)
    async with open_checkpointer(os.environ["TEST_DATABASE_URL"], schema) as saver:
        stage = build_approval_stage(context, checkpointer=saver, tool=tool)
        if step == "start":
            action = propose_create_ticket(
                CreateTicketArguments(
                    issue_report_id=report_id,
                    title="Synthetic ticket",
                    description="Synthetic report",
                    service_code=None,
                    severity=None,
                ),
                explanation="Support review",
                expected_effect="Simulated ticket creation",
                risk=ActionRisk(level=RiskLevel.LOW, reason="Simulation"),
            )
            await stage.ainvoke(
                ApprovalInput(
                    workflow_run_id=run_id,
                    issue_report_id=report_id,
                    proposed_action=action,
                ),
                config,
                durability="sync",
            )
        elif step in {"approve", "fail", "failed-replay"}:
            snapshot = await stage.aget_state(config)
            action = snapshot.values["proposed_action"]
            assert isinstance(action, ProposedAction)
            runner = ApprovalRunner(
                stage,
                context,
                PostgresRunLocks(os.environ["TEST_DATABASE_URL"], schema),
            )
            await runner.submit(
                run_id,
                {
                    "action_id": str(action.action_id),
                    "version": action.version,
                    "fingerprint": action.fingerprint(),
                    "decision": "approve",
                },
            )
        snapshot = await stage.aget_state(config)
        action = snapshot.values["proposed_action"]
        assert isinstance(action, ProposedAction)
        assert all(
            isinstance(event, ExecutionEvent) for event in snapshot.values["timeline"]
        )
        decision = snapshot.values.get("approval")
        if step != "start":
            assert isinstance(decision, ApprovalDecision)
            assert decision.permits(action)
            assert decision.actor_id == actor_id
            assert snapshot.next == ()
        execution = snapshot.values.get("tool_execution")
        failure = snapshot.values.get("tool_failure")
        if step in {"fail", "failed-replay"}:
            assert isinstance(failure, ToolExecutionFailure)
            assert failure.outcome == "unknown"
            assert "tool_execution" not in snapshot.values
            assert "support_ticket_id" not in snapshot.values
        elif tool is not None and step != "start":
            assert isinstance(execution, ToolExecutionResult)
            assert execution.result.simulated is True
            assert (
                snapshot.values["support_ticket_id"]
                == execution.result.support_ticket_id
            )
        else:
            assert "support_ticket_id" not in snapshot.values
        print(
            json.dumps(
                {
                    "run_id": str(snapshot.values["workflow_run_id"]),
                    "action_id": str(action.action_id),
                    "fingerprint": action.fingerprint(),
                    "key": str(action.idempotency_key),
                    "approved": decision is not None,
                    "timeline": [
                        event.model_dump(mode="json")
                        for event in snapshot.values["timeline"]
                    ],
                    "actor_id": str(decision.actor_id) if decision else None,
                    "decided_at": decision.decided_at.isoformat() if decision else None,
                    "tool_calls": len(tool.calls) if tool else 0,
                    "failure": failure.model_dump(mode="json") if failure else None,
                    "execution": execution.model_dump(mode="json")
                    if execution
                    else None,
                }
            )
        )


if __name__ == "__main__":
    asyncio.run(run(sys.argv[1], UUID(sys.argv[2]), UUID(sys.argv[3]), sys.argv[4]))
