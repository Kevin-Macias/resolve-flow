"""Trusted preparation and exact-version decisions over durable approval stages."""

import hashlib
import json
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
from typing import cast
from uuid import UUID

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from api.db.models import IssueReport, Service
from api.identity.context import RequestContext
from api.identity.dependencies import resolve_request_context
from api.intake.locks import IntakeLocks
from api.intake.models import IntakeRun
from api.intake.schemas import CustomerRun, CustomerTurn
from api.knowledge.metadata import KnowledgeContract
from api.support.access import allowed_accounts
from api.support.action_models import ProposalPreparation, SupportActionRun
from api.support.action_schemas import ProposalRequest, SupportAction
from api.workflow.actions import (
    ActionRisk,
    CreateTicketArguments,
    ProposedAction,
    RiskLevel,
    propose_create_ticket,
    revise_create_ticket,
)
from api.workflow.approval import ApprovalDecision, ApprovalReply
from api.workflow.approval_graph import approval_config, build_approval_stage
from api.workflow.approval_runner import ApprovalRunner, PostgresRunLocks
from api.workflow.checkpoints import CHECKPOINT_SCHEMA, open_checkpointer
from api.workflow.execution import (
    SimulatedCreateTicketTool,
    ToolExecutionFailure,
    ToolExecutionResult,
)
from api.workflow.langgraph_types import WorkflowGraph
from api.workflow.state import ApprovalInput, ApprovalState


class ActionObservations(KnowledgeContract):
    description: str
    service_code: str | None
    run_id: UUID | None
    revision: int | None
    turns: tuple[CustomerTurn, ...]
    intake_status: str | None
    operation_pending: bool
    report_status: str

    def fingerprint(self) -> str:
        return hashlib.sha256(self.model_dump_json().encode()).hexdigest()

    def eligible(self) -> bool:
        return (
            self.report_status != "deleted"
            and self.intake_status == "needs_confirmation"
            and not self.operation_pending
        )


def payload_hash(body: ProposalRequest) -> str:
    return hashlib.sha256(body.model_dump_json().encode()).hexdigest()


class SupportActions:
    def __init__(
        self,
        sessions: async_sessionmaker[AsyncSession],
        database_url: str,
        checkpoint_schema: str = CHECKPOINT_SCHEMA,
    ):
        self.sessions = sessions
        self.database_url = database_url
        self.checkpoint_schema = checkpoint_schema
        self.report_locks = IntakeLocks(database_url)
        self.run_locks = PostgresRunLocks(database_url, namespace=checkpoint_schema)

    async def observations(
        self, token: str, report_id: UUID
    ) -> tuple[UUID, ActionObservations, RequestContext]:
        async with self.sessions() as session:
            accounts = await allowed_accounts(token, session)
            context = await resolve_request_context(token, session)
            report = await session.scalar(
                select(IssueReport).where(
                    IssueReport.id == report_id,
                    IssueReport.customer_account_id.in_(accounts),
                )
            )
            if report is None:
                raise HTTPException(404, "Report unavailable")
            service = (
                await session.get(Service, report.affected_service_id)
                if report.affected_service_id is not None
                else None
            )
            run = await session.scalar(
                select(IntakeRun).where(IntakeRun.report_id == report_id)
            )
            view = (
                CustomerRun.model_validate_json(json.dumps(run.public_view))
                if run is not None
                else None
            )
            if run is not None and (
                run.customer_account_id != report.customer_account_id
                or view is None
                or view.report_id != report_id
                or view.run_id != run.id
                or view.revision != run.revision
            ):
                raise ValueError("Invalid intake binding")
            return (
                report.customer_account_id,
                ActionObservations(
                    description=report.description,
                    service_code=service.code if service else None,
                    run_id=run.id if run else None,
                    revision=run.revision if run else None,
                    turns=view.turns if view else (),
                    intake_status=view.status if view else None,
                    operation_pending=bool(
                        run and run.pending_operation_id is not None
                    ),
                    report_status=report.status,
                ),
                context,
            )

    async def registry(self, report_id: UUID) -> SupportActionRun | None:
        async with self.sessions() as session:
            return await session.scalar(
                select(SupportActionRun).where(SupportActionRun.report_id == report_id)
            )

    async def context(
        self, token: str, report_id: UUID, row: SupportActionRun, *, fresh: bool
    ) -> RequestContext:
        owner, current, context = await self.observations(token, report_id)
        original = ActionObservations.model_validate(row.input_record)
        if (
            owner != row.customer_account_id
            or current.run_id != row.run_id
            or original.run_id != row.run_id
            or original.fingerprint() != row.input_hash
        ):
            raise RuntimeError("Invalid approval input binding")
        if fresh and (
            not current.eligible() or current.fingerprint() != row.input_hash
        ):
            raise HTTPException(
                409, "Observations changed or this report cannot accept an action"
            )
        return context

    @asynccontextmanager
    async def stage(
        self, token: str, report_id: UUID, row: SupportActionRun, *, fresh: bool = False
    ) -> AsyncGenerator[WorkflowGraph[ApprovalInput], None]:
        async def load_context(bound_report_id: UUID) -> RequestContext:
            if bound_report_id != report_id:
                raise ValueError("Approval report mismatch")
            return await self.context(token, report_id, row, fresh=fresh)

        async with open_checkpointer(
            self.database_url, self.checkpoint_schema
        ) as saver:
            # A request-scoped adapter avoids accumulating tool call history on app.state.
            yield build_approval_stage(
                load_context, checkpointer=saver, tool=self.tool()
            )

    def tool(self) -> SimulatedCreateTicketTool:
        return SimulatedCreateTicketTool()

    async def snapshot(
        self, stage: WorkflowGraph[ApprovalInput], row: SupportActionRun
    ) -> tuple[ApprovalState | None, bool]:
        snapshot = await stage.aget_state(approval_config(row.run_id))
        if not snapshot.values:
            return None, False
        state = cast(ApprovalState, snapshot.values)
        if (
            state.get("workflow_run_id") != row.run_id
            or state.get("issue_report_id") != row.report_id
        ):
            raise RuntimeError("Invalid checkpoint identity")
        return state, any(task.interrupts for task in snapshot.tasks)

    async def get(self, token: str, report_id: UUID) -> SupportAction:
        owner, inputs, _ = await self.observations(token, report_id)
        row = await self.registry(report_id)
        if row is None:
            final_owner, final, _ = await self.observations(token, report_id)
            if final_owner != owner or final.run_id != inputs.run_id:
                raise ValueError("Report binding changed")
            return SupportAction(
                report_id=report_id,
                run_id=final.run_id,
                status="absent",
                archived=final.report_status == "deleted",
                input_stale=False,
                can_prepare=final.eligible(),
                proposal=None,
                fingerprint=None,
                preparation_id=None,
                pending_preparation=None,
                decision=None,
                execution=None,
                failure=None,
                timeline=(),
            )
        await self.context(token, report_id, row, fresh=False)
        proposal = ProposedAction.model_validate(row.proposal)
        async with self.stage(token, report_id, row) as stage:
            state, interrupted = await self.snapshot(stage, row)
        if row.preparing:
            if state is not None and state.get("approval") is not None:
                raise ValueError("Preparation cannot replace a decided path")
            async with self.sessions() as session:
                operation = await session.get(
                    ProposalPreparation, (row.run_id, row.operation_id)
                )
            if (
                operation is None
                or operation.completed
                or operation.proposal_fingerprint != proposal.fingerprint()
            ):
                raise ValueError("Invalid preparation binding")
            body = ProposalRequest.model_validate(operation.payload)
            if payload_hash(body) != operation.payload_hash:
                raise ValueError("Invalid preparation payload")
            decision, execution, failure = None, None, None
            timeline = ()
            status = "preparing"
        else:
            body = None
            if (
                state is None
                or ProposedAction.model_validate(state["proposed_action"]) != proposal
            ):
                raise ValueError("Saved proposal and checkpoint disagree")
            decision = (
                ApprovalDecision.model_validate(state.get("approval"))
                if state.get("approval") is not None
                else None
            )
            execution = (
                ToolExecutionResult.model_validate(state.get("tool_execution"))
                if state.get("tool_execution") is not None
                else None
            )
            failure = (
                ToolExecutionFailure.model_validate(state.get("tool_failure"))
                if state.get("tool_failure") is not None
                else None
            )
            if decision is None and not interrupted:
                raise ValueError("Stage is not awaiting a decision")
            if state.get("support_ticket_id") != (
                execution.result.support_ticket_id if execution else None
            ):
                raise ValueError("Invalid simulated ticket binding")
            timeline = tuple(state.get("timeline", []))
            status = (
                "awaiting_decision"
                if decision is None
                else "rejected"
                if decision.decision == "reject"
                else "simulated_success"
                if execution
                else "execution_unknown"
                if failure
                else "approved_unconfirmed"
            )
        final_owner, final, _ = await self.observations(token, report_id)
        current_row = await self.registry(report_id)
        if (
            final_owner != owner
            or current_row is None
            or current_row.proposal != row.proposal
            or current_row.preparing != row.preparing
        ):
            raise HTTPException(409, "Action changed while reading")
        return SupportAction.model_validate(
            dict(
                report_id=report_id,
                run_id=row.run_id,
                status=status,
                archived=final.report_status == "deleted",
                input_stale=final.fingerprint() != row.input_hash,
                can_prepare=final.eligible() and status == "awaiting_decision",
                proposal=proposal,
                fingerprint=proposal.fingerprint(),
                preparation_id=row.operation_id,
                pending_preparation=body,
                decision=decision,
                execution=execution,
                failure=failure,
                timeline=timeline,
            )
        )

    async def prepare(
        self, token: str, report_id: UUID, body: ProposalRequest
    ) -> SupportAction:
        await self.observations(token, report_id)
        async with self.report_locks.hold(report_id):
            owner, inputs, _ = await self.observations(token, report_id)
            if inputs.run_id is None:
                raise HTTPException(
                    409, "Complete customer intake before proposing an action"
                )
            async with self.run_locks(inputs.run_id):
                row = await self.registry(report_id)
                async with self.sessions() as session:
                    operation = (
                        await session.get(
                            ProposalPreparation, (inputs.run_id, body.operation_id)
                        )
                        if row
                        else None
                    )
                if operation is not None:
                    if operation.payload_hash != payload_hash(body):
                        raise HTTPException(
                            409, "Operation UUID was already used with different fields"
                        )
                    if operation.completed:
                        return await self.get(token, report_id)
                    if (
                        row is None
                        or not row.preparing
                        or row.operation_id != body.operation_id
                    ):
                        raise ValueError("Invalid interrupted preparation")
                    await self.context(token, report_id, row, fresh=False)
                    if not inputs.eligible():
                        raise HTTPException(
                            409, "This report cannot finish proposal preparation"
                        )
                else:
                    if not inputs.eligible():
                        raise HTTPException(
                            409, "Complete active intake before proposing an action"
                        )
                    previous: ProposedAction | None = None
                    if row is not None:
                        await self.context(token, report_id, row, fresh=False)
                        if row.preparing:
                            raise HTTPException(
                                409, "Finish the accepted preparation first"
                            )
                        async with self.stage(token, report_id, row) as stage:
                            state, _ = await self.snapshot(stage, row)
                        if state is None or state.get("approval") is not None:
                            raise HTTPException(
                                409, "A decided action cannot be revised"
                            )
                        previous = ProposedAction.model_validate(row.proposal)
                        if (
                            ProposedAction.model_validate(state["proposed_action"])
                            != previous
                        ):
                            raise ValueError("Invalid current proposal")
                    if body.expected_fingerprint != (
                        previous.fingerprint() if previous else None
                    ):
                        raise HTTPException(
                            409, "Proposal changed; refresh before revising"
                        )
                    arguments = CreateTicketArguments(
                        issue_report_id=report_id,
                        title=body.title,
                        description=body.description,
                        service_code=body.service_code,
                        severity=body.severity,
                    )
                    risk = ActionRisk(
                        level=RiskLevel.LOW,
                        reason="This adapter only simulates ticket creation.",
                    )
                    effect = (
                        "Simulate creating one internal ticket linked to this report."
                    )
                    proposal = (
                        revise_create_ticket(
                            previous,
                            arguments,
                            explanation=body.explanation,
                            expected_effect=effect,
                            risk=risk,
                        )
                        if previous
                        else propose_create_ticket(
                            arguments,
                            explanation=body.explanation,
                            expected_effect=effect,
                            risk=risk,
                        )
                    )
                    async with self.sessions() as session:
                        persisted = await session.get(SupportActionRun, inputs.run_id)
                        if persisted is None:
                            persisted = SupportActionRun(
                                run_id=inputs.run_id,
                                report_id=report_id,
                                customer_account_id=owner,
                            )
                            session.add(persisted)
                        persisted.proposal = proposal.model_dump(mode="json")
                        persisted.input_record = inputs.model_dump(mode="json")
                        persisted.input_hash = inputs.fingerprint()
                        persisted.preparing = True
                        persisted.operation_id = body.operation_id
                        await session.flush()
                        session.add(
                            ProposalPreparation(
                                run_id=inputs.run_id,
                                id=body.operation_id,
                                payload=body.model_dump(mode="json"),
                                payload_hash=payload_hash(body),
                                proposal_fingerprint=proposal.fingerprint(),
                                completed=False,
                            )
                        )
                        await session.commit()
                        row = persisted
                assert row is not None
                await self.initialize(token, report_id, row)
                async with self.sessions() as session:
                    persisted = await session.get(SupportActionRun, row.run_id)
                    operation = await session.get(
                        ProposalPreparation, (row.run_id, body.operation_id)
                    )
                    if persisted is None or operation is None:
                        raise ValueError("Missing preparation")
                    persisted.preparing = False
                    operation.completed = True
                    await session.commit()
                return await self.get(token, report_id)

    async def initialize(
        self, token: str, report_id: UUID, row: SupportActionRun
    ) -> None:
        await self.context(token, report_id, row, fresh=False)
        _, current, _ = await self.observations(token, report_id)
        if not current.eligible():
            raise HTTPException(409, "This report cannot prepare an action")
        proposal = ProposedAction.model_validate(row.proposal)
        # Preparing a stale review is safe; deciding it still requires a new version.
        async with self.stage(token, report_id, row, fresh=False) as stage:
            state, interrupted = await self.snapshot(stage, row)
            if state is not None and (
                state.get("approval") is not None
                or state.get("tool_execution") is not None
                or state.get("tool_failure") is not None
            ):
                raise ValueError("Preparation cannot resume a decided action")
            if (
                state is not None
                and ProposedAction.model_validate(state["proposed_action"]) == proposal
                and interrupted
            ):
                return
            await stage.ainvoke(
                {
                    "workflow_run_id": row.run_id,
                    "issue_report_id": report_id,
                    "proposed_action": proposal,
                },
                approval_config(row.run_id),
                durability="sync",
            )

    async def decide(
        self, token: str, report_id: UUID, run_id: UUID, reply: ApprovalReply
    ) -> SupportAction:
        await self.observations(token, report_id)
        async with self.report_locks.hold(report_id):
            row = await self.registry(report_id)
            if row is None or row.run_id != run_id:
                raise HTTPException(404, "Action unavailable")
            await self.context(token, report_id, row, fresh=False)
            if row.preparing:
                raise HTTPException(409, "Proposal is still preparing")
            # Choose freshness under the same lock that protects runner submission.
            fresh = True

            async def load_context(bound_report_id: UUID) -> RequestContext:
                if bound_report_id != report_id:
                    raise ValueError("Invalid report binding")
                return await self.context(token, report_id, row, fresh=fresh)

            async with open_checkpointer(
                self.database_url, self.checkpoint_schema
            ) as saver:
                stage = build_approval_stage(
                    load_context, checkpointer=saver, tool=self.tool()
                )

                @asynccontextmanager
                async def bound_lock(bound_run_id: UUID) -> AsyncGenerator[None]:
                    nonlocal fresh
                    async with self.run_locks(bound_run_id):
                        current, _ = await self.snapshot(stage, row)
                        if current is None or ProposedAction.model_validate(
                            current["proposed_action"]
                        ) != ProposedAction.model_validate(row.proposal):
                            raise RuntimeError(
                                "Checkpoint does not bind the registered proposal"
                            )
                        fresh = current.get("approval") is None
                        yield

                runner = ApprovalRunner(stage, load_context, bound_lock)
                try:
                    await runner.submit(run_id, reply.model_dump(mode="json"))
                except ValueError:
                    raise HTTPException(
                        409, "Proposal changed; refresh before deciding"
                    ) from None
            return await self.get(token, report_id)
