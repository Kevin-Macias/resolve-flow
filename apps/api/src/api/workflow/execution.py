"""Application-controlled execution of the simulated create-ticket tool."""

from collections.abc import Awaitable, Callable
from typing import Literal
from uuid import UUID, uuid5

from api.identity.context import RequestContext
from api.observability import trace
from api.workflow.actions import (
    CreateTicketArguments,
    ImmutableContract,
    ProposedAction,
)
from api.workflow.approval import ApprovalDecision


class SimulatedTicketResult(ImmutableContract):
    support_ticket_id: UUID
    status: Literal["open"] = "open"
    simulated: Literal[True] = True


class ToolExecutionResult(ImmutableContract):
    action_id: UUID
    version: int
    fingerprint: str
    idempotency_key: UUID
    executed_by_user_id: UUID
    result: SimulatedTicketResult


class ToolExecutionFailure(ImmutableContract):
    action_id: UUID
    version: int
    fingerprint: str
    idempotency_key: UUID
    reason: Literal["tool_failed"] = "tool_failed"
    outcome: Literal["unknown"] = "unknown"


class ToolCallError(Exception):
    """Sanitized failure; the adapter may have acted before raising."""


type ExecutionHandler = Callable[
    [
        ProposedAction,
        ApprovalDecision | None,
        RequestContext,
        "SimulatedCreateTicketTool",
    ],
    Awaitable[ToolExecutionResult],
]


class SimulatedCreateTicketTool:
    """Deterministic adapter with no database or external writes."""

    def __init__(self) -> None:
        self.calls: list[tuple[CreateTicketArguments, UUID]] = []

    async def create_ticket(
        self, arguments: CreateTicketArguments, idempotency_key: UUID
    ) -> SimulatedTicketResult:
        arguments = CreateTicketArguments.model_validate(arguments)
        self.calls.append((arguments, idempotency_key))
        return SimulatedTicketResult(
            support_ticket_id=uuid5(
                idempotency_key, "resolveflow-simulated-create-ticket"
            )
        )


async def execute_approved_action(
    proposal: ProposedAction,
    approval: ApprovalDecision | None,
    context: RequestContext,
    tool: SimulatedCreateTicketTool,
) -> ToolExecutionResult:
    """Context must already authorize access to this proposal's issue report.

    Revalidate saved contracts and approval at the application boundary. The
    adapter is internal and is never dispatched from model-selected code.
    """
    proposal = validate_execution(proposal, approval, context)
    with trace(
        "tool",
        component="execution",
        execution_id=proposal.idempotency_key,
        error_code="tool_unknown",
    ):
        try:
            result = SimulatedTicketResult.model_validate(
                await tool.create_ticket(proposal.arguments, proposal.idempotency_key)
            )
        except Exception:
            raise ToolCallError(
                "Tool execution failed; outcome requires review"
            ) from None
        return ToolExecutionResult(
            action_id=proposal.action_id,
            version=proposal.version,
            fingerprint=proposal.fingerprint(),
            idempotency_key=proposal.idempotency_key,
            executed_by_user_id=context.user_id,
            result=result,
        )


def validate_execution(
    proposal: ProposedAction,
    approval: ApprovalDecision | None,
    context: RequestContext,
) -> ProposedAction:
    """Validate before reserving an operation or dispatching an effect."""
    proposal = ProposedAction.model_validate(proposal)
    if context.user_type != "support":
        raise PermissionError("Only authorized support can execute an action")
    if approval is None:
        raise PermissionError("Execution requires approval of the current proposal")
    approval = ApprovalDecision.model_validate(approval)
    if not approval.permits(proposal):
        raise PermissionError("Execution requires approval of the current proposal")
    return proposal
