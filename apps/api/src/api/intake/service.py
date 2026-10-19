"""Short-lived authorized reads and serialized, explicitly requested execution."""

import asyncio
import hashlib
import json
from typing import cast
from uuid import UUID, uuid4, uuid5

from fastapi import HTTPException
from langgraph.types import Command
from pydantic import ValidationError
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from api.accounting.contracts import Mode
from api.accounting.recording import Scope, recording
from api.db.models import IssueReport
from api.identity.context import RequestContext
from api.identity.dependencies import resolve_request_context
from api.intake.models import IntakeOperation, IntakeRun
from api.intake.projection import failed, processing, project
from api.intake.runtime import IntakeRuntime
from api.intake.schemas import ClarificationRequest, CustomerRun
from api.observability import attach, trace
from api.streaming.transport import CustomerSnapshot
from api.workflow.checkpoints import workflow_config
from api.workflow.clarification import validate_reply
from api.workflow.state import WorkflowInput, WorkflowState
from api.workflow.timeline import EventType

EXECUTION_TIMEOUT_SECONDS = 120


def payload_hash(payload: dict[str, object]) -> str:
    return hashlib.sha256(
        json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()


def saved_view(run: IntakeRun) -> CustomerRun:
    view = CustomerRun.model_validate_json(json.dumps(run.public_view))
    if (
        view.run_id != run.id
        or view.report_id != run.report_id
        or view.revision != run.revision
        or view.provider_mode != run.provider_mode
        or view.simulated != (run.provider_mode == "offline")
        or view.snapshot.run_id != run.id
        or view.snapshot.revision != run.revision
    ):
        raise ValueError("Inconsistent public projection")
    expected_progress = {
        "processing": "processing",
        "needs_clarification": "waiting_input",
        "needs_confirmation": "stage_finished",
        "failed": "stage_failed",
    }[view.status]
    if (
        view.snapshot.progress != expected_progress
        or view.snapshot.customer_update != view.message
        or view.operation_pending != (run.pending_operation_id is not None)
        or (view.pending is not None) != (view.status == "needs_clarification")
    ):
        raise ValueError("Inconsistent customer state")
    return view


class IntakeService:
    def __init__(self, runtime: IntakeRuntime, token: str):
        self.runtime = runtime
        self.token = token  # Request lifetime only; never saved in a run/checkpoint.

    async def context(self, session: AsyncSession) -> RequestContext:
        context = await resolve_request_context(self.token, session)
        if context.user_type != "customer" or context.customer_account_id is None:
            raise HTTPException(403, "Not permitted")
        return context

    async def report(
        self, session: AsyncSession, report_id: UUID
    ) -> tuple[IssueReport, RequestContext]:
        context = await self.context(session)
        report = await session.scalar(
            select(IssueReport).where(
                IssueReport.id == report_id,
                IssueReport.customer_account_id == context.customer_account_id,
                IssueReport.status != "deleted",
            )
        )
        if report is None:
            raise HTTPException(404, "Intake unavailable")
        return report, context

    async def run(self, session: AsyncSession, run_id: UUID) -> IntakeRun:
        context = await self.context(session)
        run = await session.scalar(
            select(IntakeRun)
            .join(IssueReport, IssueReport.id == IntakeRun.report_id)
            .where(
                IntakeRun.id == run_id,
                IntakeRun.customer_account_id == context.customer_account_id,
                IssueReport.customer_account_id == IntakeRun.customer_account_id,
                IssueReport.status != "deleted",
            )
        )
        if run is None:
            raise HTTPException(404, "Intake unavailable")
        attach(run_id=run.id)
        return run

    async def get(self, run_id: UUID) -> CustomerRun:
        async with self.runtime.sessions() as session:
            return saved_view(await self.run(session, run_id))

    async def for_report(self, report_id: UUID) -> CustomerRun:
        async with self.runtime.sessions() as session:
            await self.report(session, report_id)
            run_id = await session.scalar(
                select(IntakeRun.id).where(IntakeRun.report_id == report_id)
            )
            if run_id is None:
                raise HTTPException(404, "Intake unavailable")
        return await self.get(run_id)

    async def authorize(self, run_id: UUID) -> None:
        await self.get(run_id)

    async def read(self, run_id: UUID) -> CustomerSnapshot:
        return (await self.get(run_id)).snapshot

    async def start(self, report_id: UUID) -> tuple[CustomerRun, bool]:
        async with self.runtime.sessions() as session:
            await self.report(session, report_id)
            existing = await session.scalar(
                select(IntakeRun.id).where(IntakeRun.report_id == report_id)
            )
        if existing is not None:
            return await self.get(existing), False
        async with self.runtime.locks.hold(report_id):
            run_id = uuid4()
            async with self.runtime.sessions() as session:
                _, context = await self.report(session, report_id)
                existing = await session.scalar(
                    select(IntakeRun.id).where(IntakeRun.report_id == report_id)
                )
                if existing is None:
                    operation_id = uuid4()
                    view = processing(run_id, report_id, self.runtime.mode, 1)
                    run = IntakeRun(
                        id=run_id,
                        report_id=report_id,
                        customer_account_id=context.customer_account_id,
                        initiated_by=context.user_id,
                        provider_mode=self.runtime.mode,
                        revision=1,
                        public_view=view.model_dump(mode="json"),
                        pending_operation_id=operation_id,
                    )
                    session.add(run)
                    run.accounting_version = 1
                    await session.flush()
                    session.add(
                        IntakeOperation(
                            run_id=run_id,
                            id=operation_id,
                            kind="start",
                            payload={},
                            payload_hash=payload_hash({}),
                            completed=False,
                        )
                    )
                    await session.commit()
            if existing is not None:
                return await self.get(existing), False
            await self.execute(run_id)
            return await self.get(run_id), True

    async def clarify(self, run_id: UUID, request: ClarificationRequest) -> CustomerRun:
        current = await self.get(run_id)
        async with self.runtime.locks.hold(current.report_id):
            async with self.runtime.sessions() as session:
                run = await self.run(session, run_id)
                view = saved_view(run)
                payload = request.model_dump(mode="json")
                previous = await session.get(
                    IntakeOperation, (run_id, request.operation_id)
                )
                if previous is not None:
                    if (
                        previous.kind != "clarification"
                        or previous.payload_hash != payload_hash(payload)
                    ):
                        raise HTTPException(409, "Operation identity already used")
                    # Do not recover an unfinished operation by retrying its POST.
                    return view
                if (
                    run.pending_operation_id is not None
                    or request.expected_revision != view.revision
                    or view.pending is None
                    or request.pending_id != view.pending.pending_id
                ):
                    raise HTTPException(409, "Intake state changed; refresh")
                # Validate against the exact saved public pause before any graph call.
                pending = view.pending
                if request.action == "answer":
                    valid = (
                        pending.mode == "answer_or_continue"
                        and len(request.answers) == len(pending.questions)
                        and bool(request.answers)
                    )
                else:
                    valid = not request.answers
                if not valid:
                    raise HTTPException(422, "Invalid clarification reply")
                session.add(
                    IntakeOperation(
                        run_id=run_id,
                        id=request.operation_id,
                        kind="clarification",
                        payload=payload,
                        payload_hash=payload_hash(payload),
                        completed=False,
                    )
                )
                run.pending_operation_id = request.operation_id
                next_view = processing(
                    run_id, run.report_id, view.provider_mode, view.revision + 1
                ).model_copy(
                    update={"turns": view.turns, "incomplete": view.incomplete}
                )
                self.publish(run, next_view)
                await session.commit()
            await self.execute(run_id)
            return await self.get(run_id)

    async def recover(self, run_id: UUID, expected_revision: int) -> CustomerRun:
        current = await self.get(run_id)
        async with self.runtime.locks.hold(current.report_id):
            async with self.runtime.sessions() as session:
                run = await self.run(session, run_id)
                view = saved_view(run)
                if (
                    view.revision != expected_revision
                    or run.pending_operation_id is None
                ):
                    raise HTTPException(409, "No matching interrupted operation")
                if not view.operation_pending:
                    raise HTTPException(409, "Intake needs review")
                if view.status != "processing":
                    next_view = processing(
                        run_id, run.report_id, view.provider_mode, view.revision + 1
                    ).model_copy(
                        update={"turns": view.turns, "incomplete": view.incomplete}
                    )
                    self.publish(run, next_view)
                    await session.commit()
            await self.execute(run_id)
            return await self.get(run_id)

    @staticmethod
    def publish(run: IntakeRun, view: CustomerRun) -> None:
        run.revision = view.revision
        run.public_view = view.model_dump(mode="json")

    async def execute(self, run_id: UUID) -> None:
        # Caller holds the report lock until final publication, never a row transaction.
        async with self.runtime.sessions() as session:
            run = await self.run(session, run_id)
            if run.pending_operation_id is None:
                return
            operation = await session.get(
                IntakeOperation, (run_id, run.pending_operation_id)
            )
            if (
                operation is None
                or operation.completed
                or operation.payload_hash != payload_hash(operation.payload)
            ):
                raise HTTPException(503, "Intake needs review")
            report_id, mode = run.report_id, run.provider_mode
            operation_id, kind, payload = (
                operation.id,
                operation.kind,
                operation.payload,
            )
        with (
            recording(
                self.runtime.sessions,
                Scope(
                    report_id,
                    run.customer_account_id,
                    "intake",
                    run_id,
                    operation_id,
                    cast(Mode, mode),
                ),
            ),
            trace("run", component="intake", run_id=run_id, operation_id=operation_id),
        ):
            if mode != self.runtime.mode:
                raise HTTPException(
                    503, "Configured intake mode does not match saved run"
                )

            async def loader(requested_id: UUID) -> str:
                if requested_id != report_id:
                    raise ValueError("Report binding mismatch")
                await self.get(run_id)
                async with self.runtime.sessions() as session:
                    report, _ = await self.report(session, report_id)
                    return report.description

            try:
                async with asyncio.timeout(EXECUTION_TIMEOUT_SECONDS):
                    async with self.runtime.graph(loader) as graph:
                        config = workflow_config(run_id)
                        snapshot = await graph.aget_state(config)
                        state = cast(WorkflowState, snapshot.values)
                        command: WorkflowInput | Command[object] | None = None
                        invoke = False
                        if not state:
                            if kind != "start":
                                raise ValueError("Missing resume checkpoint")
                            command = WorkflowInput(
                                workflow_run_id=run_id, issue_report_id=report_id
                            )
                            invoke = True
                        else:
                            if (
                                state["workflow_run_id"] != run_id
                                or state["issue_report_id"] != report_id
                            ):
                                raise ValueError("Checkpoint binding mismatch")
                            interrupts = [
                                interrupt
                                for task in snapshot.tasks
                                for interrupt in task.interrupts
                            ]
                            if kind == "clarification":
                                request = ClarificationRequest.model_validate(payload)
                                if request.operation_id != operation_id:
                                    raise ValueError("Operation binding mismatch")
                                event_type = (
                                    EventType.CLARIFICATION_ANSWERED
                                    if request.action == "answer"
                                    else EventType.CONTINUED_INCOMPLETE
                                )
                                event_id = uuid5(
                                    run_id,
                                    f"resolveflow:intake:{event_type}:{request.pending_id}",
                                )
                                consumed = any(
                                    event.event_id == event_id
                                    for event in state.get("timeline", [])
                                )
                                if not consumed:
                                    pending = state.get("pending_clarification")
                                    if (
                                        pending is None
                                        or validate_reply(request.reply(), pending)
                                        is None
                                        or len(interrupts) != 1
                                    ):
                                        raise ValueError(
                                            "Cannot establish saved reply ownership"
                                        )
                                    # Target the saved interrupt; never replay a reply into a later pause.
                                    command = Command(
                                        resume={interrupts[0].id: request.reply()}
                                    )
                                    invoke = True
                                else:
                                    invoke = bool(snapshot.next) and not interrupts
                            elif kind == "start":
                                invoke = bool(snapshot.next) and not interrupts
                            else:
                                raise ValueError("Unknown operation")
                        if invoke:
                            await graph.ainvoke(command, config, durability="sync")
                        snapshot = await graph.aget_state(config)
                        state = cast(WorkflowState, snapshot.values)
                        interrupts = [
                            interrupt
                            for task in snapshot.tasks
                            for interrupt in task.interrupts
                        ]
                        if snapshot.next and not interrupts:
                            raise ValueError("Graph work is unfinished")
                        if kind == "clarification":
                            request = ClarificationRequest.model_validate(payload)
                            event_type = (
                                EventType.CLARIFICATION_ANSWERED
                                if request.action == "answer"
                                else EventType.CONTINUED_INCOMPLETE
                            )
                            event_id = uuid5(
                                run_id,
                                f"resolveflow:intake:{event_type}:{request.pending_id}",
                            )
                            if not any(
                                event.event_id == event_id
                                for event in state.get("timeline", [])
                            ):
                                raise ValueError("Reply did not commit")
                async with self.runtime.sessions() as session:
                    run = await self.run(
                        session, run_id
                    )  # Recheck access before publication.
                    base = saved_view(run)
                    try:
                        view = project(base, state)
                    except (ValidationError, ValueError):
                        view = failed(base, recoverable=False)
                    self.publish(run, view)
                    run.pending_operation_id = None
                    operation = await session.get(
                        IntakeOperation, (run_id, operation_id)
                    )
                    if operation is None:
                        raise ValueError("Missing accepted operation")
                    operation.completed = True
                    await session.commit()
            except HTTPException:
                raise
            except Exception as error:
                # Checkpoint commits may precede this registry write. Keep the accepted
                # payload for explicit recovery, and never expose the raw exception.
                try:
                    async with self.runtime.sessions() as session:
                        run = await self.run(session, run_id)
                        self.publish(run, failed(saved_view(run), recoverable=True))
                        await session.commit()
                except Exception:
                    pass  # Infrastructure may be unavailable; original pending state persists.
                raise HTTPException(
                    503, "Intake interrupted; inspect saved state"
                ) from error
