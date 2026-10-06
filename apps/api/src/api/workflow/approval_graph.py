"""A reusable approval stage for a saved, reviewed proposal."""

from collections.abc import Awaitable, Callable
from typing import Literal
from uuid import UUID

from langchain_core.runnables import RunnableConfig
from langgraph.checkpoint.base import (  # pyright: ignore[reportMissingTypeStubs]
    BaseCheckpointSaver,
)
from langgraph.checkpoint.memory import (  # pyright: ignore[reportMissingTypeStubs]
    InMemorySaver,
)
from langgraph.graph import (  # pyright: ignore[reportMissingTypeStubs]
    END,
    START,
    StateGraph,
)
from langgraph.graph.state import (  # pyright: ignore[reportMissingTypeStubs]
    CompiledStateGraph,
)
from langgraph.types import interrupt  # pyright: ignore[reportMissingTypeStubs]

from api.identity.context import RequestContext
from api.workflow.actions import ProposedAction
from api.workflow.approval import (
    ApprovalChoice,
    record_approval,
    validate_approval_reply,
)
from api.workflow.checkpoints import checkpoint_serializer
from api.workflow.execution import (
    SimulatedCreateTicketTool,
    ToolCallError,
    ToolExecutionFailure,
    execute_approved_action,
)
from api.workflow.state import (
    ApprovalInput,
    ApprovalState,
    CustomerSafeReport,
    ReportStatus,
    WorkflowUpdate,
)
from api.workflow.timeline import EventMetadata, EventType, transition_event

type ApprovalContextLoader = Callable[[UUID], Awaitable[RequestContext]]


def approval_config(run_id: UUID) -> RunnableConfig:
    # Separate stage storage from the intake graph while retaining the run UUID.
    return {"configurable": {"thread_id": f"{run_id}:approval"}}


def build_approval_stage(
    load_context: ApprovalContextLoader,
    *,
    checkpointer: BaseCheckpointSaver[str] | None = None,
    tool: SimulatedCreateTicketTool | None = None,
) -> CompiledStateGraph[ApprovalState, None, ApprovalInput, ApprovalState]:
    """load_context must authenticate the current actor and authorize this report.

    Saved proposal input comes from trusted application orchestration, never
    directly from a customer's or model's request. Injecting the simulated tool
    enables execution after approval; otherwise this remains approval-only.
    """

    def event(
        state: ApprovalState,
        kind: EventType,
        *,
        actor_id: UUID | None = None,
        ticket_id: UUID | None = None,
        outcome: Literal["unknown", "simulated"] | None = None,
    ) -> WorkflowUpdate:
        proposal = ProposedAction.model_validate(state["proposed_action"])
        return {
            "timeline": transition_event(
                state["workflow_run_id"],
                state.get("timeline", []),
                "approval",
                kind,
                proposal.fingerprint(),
                EventMetadata(
                    action_id=proposal.action_id,
                    action_version=proposal.version,
                    fingerprint=proposal.fingerprint(),
                    actor_id=actor_id,
                    support_ticket_id=ticket_id,
                    outcome=outcome,
                ),
            )
        }

    def prepare_review(state: ApprovalState) -> WorkflowUpdate:
        proposal = ProposedAction.model_validate(state["proposed_action"])
        if proposal.arguments.issue_report_id != state["issue_report_id"]:
            raise ValueError("Proposal must belong to this workflow's issue report")
        return event(state, EventType.APPROVAL_REQUESTED)

    async def review_action(state: ApprovalState) -> WorkflowUpdate:
        context = await load_context(state["issue_report_id"])
        if context.user_type != "support":
            raise PermissionError("Only authorized support can review an action")
        proposal = ProposedAction.model_validate(state["proposed_action"])
        if proposal.arguments.issue_report_id != state["issue_report_id"]:
            raise ValueError("Proposal must belong to this workflow's issue report")
        payload = {
            "proposal": proposal.model_dump(mode="json"),
            "fingerprint": proposal.fingerprint(),
            "choices": ["approve", "reject"],
        }
        while True:
            raw: object = interrupt(payload)
            reply = validate_approval_reply(raw, proposal)
            if reply is not None:
                break
            payload = {**payload, "error": "invalid_or_stale_approval"}
        decision = record_approval(reply, proposal, context)
        rejected = decision.decision is ApprovalChoice.REJECT
        return {
            **event(
                state,
                EventType.ACTION_REJECTED if rejected else EventType.ACTION_APPROVED,
                actor_id=decision.actor_id,
            ),
            "approval": decision,
            "customer_update": CustomerSafeReport(
                ReportStatus.ACTION_REJECTED
                if rejected
                else ReportStatus.AWAITING_EXECUTION,
                "The proposed action was rejected. No ticket was created."
                if rejected
                else "The proposed action is approved and awaiting execution.",
            ),
        }

    def after_review(state: ApprovalState) -> Literal["execute_action", "finish"]:
        decision = state.get("approval")
        return (
            "execute_action"
            if tool is not None
            and decision is not None
            and decision.decision is ApprovalChoice.APPROVE
            else "finish"
        )

    async def execute_action(state: ApprovalState) -> WorkflowUpdate:
        assert tool is not None
        context = await load_context(state["issue_report_id"])
        proposal = ProposedAction.model_validate(state["proposed_action"])
        if proposal.arguments.issue_report_id != state["issue_report_id"]:
            raise ValueError("Proposal must belong to this workflow's issue report")
        try:
            execution = await execute_approved_action(
                proposal, state.get("approval"), context, tool
            )
        except ToolCallError:
            return {
                **event(
                    state,
                    EventType.TOOL_FAILED,
                    actor_id=context.user_id,
                    outcome="unknown",
                ),
                "tool_failure": ToolExecutionFailure(
                    action_id=proposal.action_id,
                    version=proposal.version,
                    fingerprint=proposal.fingerprint(),
                    idempotency_key=proposal.idempotency_key,
                ),
                "customer_update": CustomerSafeReport(
                    ReportStatus.TOOL_EXECUTION_FAILED,
                    "Ticket creation could not be confirmed. Support review is required.",
                ),
            }
        return {
            **event(
                state,
                EventType.TOOL_SUCCEEDED,
                actor_id=execution.executed_by_user_id,
                ticket_id=execution.result.support_ticket_id,
                outcome="simulated",
            ),
            "tool_execution": execution,
            "support_ticket_id": execution.result.support_ticket_id,
            "customer_update": CustomerSafeReport(
                ReportStatus.SIMULATED_TICKET_CREATED,
                "A simulated support ticket was created; its status is open.",
            ),
        }

    builder = StateGraph(ApprovalState, input_schema=ApprovalInput)
    builder.add_node("prepare_review", prepare_review)
    builder.add_node("review_action", review_action)
    builder.add_edge(START, "prepare_review")
    builder.add_edge("prepare_review", "review_action")
    builder.add_node("execute_action", execute_action)
    builder.add_conditional_edges(
        "review_action",
        after_review,
        {"execute_action": "execute_action", "finish": END},
    )
    builder.add_edge("execute_action", END)
    saver = (
        checkpointer
        if checkpointer is not None
        else InMemorySaver(serde=checkpoint_serializer())
    )
    return builder.compile(checkpointer=saver)
