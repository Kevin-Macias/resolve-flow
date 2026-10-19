"""Durable application intent and a transactional simulated destination."""

import hashlib
from collections.abc import Awaitable, Callable
from uuid import UUID

from sqlalchemy import select, text
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from api.identity.context import RequestContext
from api.observability import emit, trace
from api.support.action_models import ExecutionOperation, SimulatedTicketEffect
from api.workflow.actions import ProposedAction
from api.workflow.approval import ApprovalDecision
from api.workflow.execution import (
    SimulatedCreateTicketTool,
    ToolCallError,
    ToolExecutionResult,
    execute_approved_action,
    validate_execution,
)


def checked_result(value: object, proposal: ProposedAction) -> ToolExecutionResult:
    result = ToolExecutionResult.model_validate(value)
    if (
        result.action_id != proposal.action_id
        or result.version != proposal.version
        or result.fingerprint != proposal.fingerprint()
        or result.idempotency_key != proposal.idempotency_key
    ):
        raise ValueError("Execution receipt does not bind the approved proposal")
    return result


class DurableSimulation:
    def __init__(
        self,
        sessions: async_sessionmaker[AsyncSession],
        run_id: UUID,
        load_context: Callable[[], Awaitable[RequestContext]] | None = None,
    ):
        self.sessions = sessions
        self.run_id = run_id
        self.load_context = load_context

    def check_operation(
        self,
        operation: ExecutionOperation,
        proposal: ProposedAction,
        approval: ApprovalDecision,
    ) -> None:
        if (
            operation.run_id != self.run_id
            or operation.idempotency_key != proposal.idempotency_key
            or operation.fingerprint != proposal.fingerprint()
            or ProposedAction.model_validate(operation.proposal) != proposal
            or ApprovalDecision.model_validate(operation.approval) != approval
        ):
            raise ValueError("Operation key is bound to a different approved action")

    async def reserve(
        self, proposal: ProposedAction, approval: ApprovalDecision
    ) -> ToolExecutionResult | None:
        async with self.sessions() as session, session.begin():
            await session.execute(
                insert(ExecutionOperation)
                .values(
                    idempotency_key=proposal.idempotency_key,
                    run_id=self.run_id,
                    fingerprint=proposal.fingerprint(),
                    proposal=proposal.model_dump(mode="json"),
                    approval=approval.model_dump(mode="json"),
                )
                .on_conflict_do_nothing()
            )
            operation = await session.get(ExecutionOperation, proposal.idempotency_key)
            if operation is None:
                raise ValueError("This run is bound to a different operation")
            self.check_operation(operation, proposal, approval)
            return (
                checked_result(operation.result, proposal)
                if operation.result is not None
                else None
            )

    async def destination(
        self,
        proposal: ProposedAction,
        approval: ApprovalDecision,
        context: RequestContext,
        tool: SimulatedCreateTicketTool,
    ) -> ToolExecutionResult:
        """The local fake's effect and receipt commit together, without a checkpoint.

        Only the pure simulated adapter belongs here. A real remote write cannot
        join this transaction and must provide its own idempotency contract.
        """
        proposal = validate_execution(proposal, approval, context)
        digest = hashlib.sha256(
            f"resolveflow:simulated-destination:{proposal.idempotency_key}".encode()
        ).digest()
        key = int.from_bytes(digest[:8], "big", signed=True)
        async with self.sessions() as session, session.begin():
            await session.execute(
                text("SELECT pg_advisory_xact_lock(:key)"), {"key": key}
            )
            existing = await session.get(
                SimulatedTicketEffect, proposal.idempotency_key
            )
            if existing is not None:
                result = checked_result(existing.result, proposal)
                if (
                    existing.fingerprint != proposal.fingerprint()
                    or existing.ticket_id != result.result.support_ticket_id
                ):
                    raise ValueError("Invalid simulated destination receipt")
                emit(
                    "execution.receipt_reused",
                    component="execution",
                    outcome="reused",
                    execution_id=proposal.idempotency_key,
                    run_id=self.run_id,
                )
                return result
            if self.load_context is not None:
                context = await self.load_context()
            result = await execute_approved_action(proposal, approval, context, tool)
            session.add(
                SimulatedTicketEffect(
                    idempotency_key=proposal.idempotency_key,
                    fingerprint=proposal.fingerprint(),
                    ticket_id=result.result.support_ticket_id,
                    result=result.model_dump(mode="json"),
                )
            )
            return result

    async def complete(
        self,
        proposal: ProposedAction,
        approval: ApprovalDecision,
        result: ToolExecutionResult,
    ) -> None:
        async with self.sessions() as session, session.begin():
            operation = await session.scalar(
                select(ExecutionOperation)
                .where(ExecutionOperation.idempotency_key == proposal.idempotency_key)
                .with_for_update()
            )
            if operation is None:
                raise ValueError("Missing durable operation")
            self.check_operation(operation, proposal, approval)
            result = checked_result(result, proposal)
            if (
                operation.result is not None
                and checked_result(operation.result, proposal) != result
            ):
                raise ValueError("Conflicting operation result")
            operation.result = result.model_dump(mode="json")

    async def execute(
        self,
        proposal: ProposedAction,
        approval: ApprovalDecision | None,
        context: RequestContext,
        tool: SimulatedCreateTicketTool,
    ) -> ToolExecutionResult:
        proposal = validate_execution(proposal, approval, context)
        assert approval is not None
        with trace(
            "execution",
            component="execution",
            run_id=self.run_id,
            execution_id=proposal.idempotency_key,
            error_code="tool_unknown",
        ) as span:
            try:
                saved = await self.reserve(proposal, approval)
                if saved is not None:
                    span.outcome = "reused"
                    return saved
                emit("execution.intent_ready", component="execution")
                result = await self.destination(proposal, approval, context, tool)
                emit("execution.destination_committed", component="execution")
                await self.complete(proposal, approval, result)
                emit("execution.result_committed", component="execution")
                return result
            except Exception:
                raise ToolCallError(
                    "Simulated execution could not be confirmed"
                ) from None
