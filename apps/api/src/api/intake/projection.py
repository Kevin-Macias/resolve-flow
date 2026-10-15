from typing import Literal
from uuid import UUID

from api.intake.schemas import CustomerPause, CustomerRun, CustomerTurn
from api.streaming.transport import CustomerSnapshot, Progress
from api.workflow.state import ReportStatus, WorkflowState

Mode = Literal["offline", "live"]


def processing(run_id: UUID, report_id: UUID, mode: Mode, revision: int) -> CustomerRun:
    message = (
        "Intake is processing. If interrupted, explicitly recover the saved operation."
    )
    return CustomerRun(
        run_id=run_id,
        report_id=report_id,
        revision=revision,
        status="processing",
        provider_mode=mode,
        simulated=mode == "offline",
        message=message,
        operation_pending=True,
        pending=None,
        turns=(),
        incomplete=False,
        snapshot=CustomerSnapshot(
            run_id=run_id,
            revision=revision,
            progress="processing",
            customer_update=message,
        ),
    )


def project(base: CustomerRun, state: WorkflowState) -> CustomerRun:
    update = state.get("customer_update")
    if update is None:
        raise ValueError("Missing customer result")
    status: Literal["needs_clarification", "needs_confirmation", "failed"]
    progress: Progress
    if update.status == ReportStatus.NEEDS_CLARIFICATION:
        status, progress = "needs_clarification", "waiting_input"
    elif update.status == ReportStatus.NEEDS_CONFIRMATION:
        status, progress = "needs_confirmation", "stage_finished"
    elif update.status == ReportStatus.EXTRACTION_FAILED:
        status, progress = "failed", "stage_failed"
    else:
        raise ValueError("Not an intake status")
    pending = state.get("pending_clarification")
    public_pause = (
        CustomerPause.model_validate(pending.model_dump(exclude={"reasons"}))
        if pending is not None
        else None
    )
    if (status == "needs_clarification") != (public_pause is not None):
        raise ValueError("Inconsistent pause")
    turns = tuple(
        CustomerTurn.model_validate(turn.model_dump())
        for turn in state.get("clarification_turns", [])
    )
    revision = base.revision + 1
    return CustomerRun(
        run_id=base.run_id,
        report_id=base.report_id,
        revision=revision,
        status=status,
        provider_mode=base.provider_mode,
        simulated=base.simulated,
        message=update.message,
        operation_pending=False,
        pending=public_pause,
        turns=turns,
        incomplete=update.incomplete,
        snapshot=CustomerSnapshot(
            run_id=base.run_id,
            revision=revision,
            progress=progress,
            customer_update=update.message,
        ),
    )


def failed(base: CustomerRun, *, recoverable: bool) -> CustomerRun:
    message = (
        "Intake was interrupted. Recover the saved operation explicitly."
        if recoverable
        else "Intake could not publish a valid customer result. It needs review."
    )
    revision = base.revision + 1
    return CustomerRun(
        run_id=base.run_id,
        report_id=base.report_id,
        revision=revision,
        status="failed",
        provider_mode=base.provider_mode,
        simulated=base.simulated,
        message=message,
        operation_pending=recoverable,
        pending=None,
        turns=base.turns,
        incomplete=base.incomplete,
        snapshot=CustomerSnapshot(
            run_id=base.run_id,
            revision=revision,
            progress="stage_failed",
            customer_update=message,
        ),
    )
