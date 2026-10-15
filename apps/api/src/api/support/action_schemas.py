"""Closed support projections; client decisions cannot replace action arguments."""

from typing import Annotated, Literal, Self
from uuid import UUID

from pydantic import Field, StringConstraints, model_validator

from api.extraction.schemas import Severity
from api.intake.schemas import Contract
from api.workflow.actions import ProposedAction
from api.workflow.approval import ApprovalChoice, ApprovalDecision, matches
from api.workflow.execution import ToolExecutionFailure, ToolExecutionResult
from api.workflow.timeline import ExecutionEvent, append_events

type Fingerprint = Annotated[str, Field(pattern=r"^[0-9a-f]{64}$")]
type DraftText = Annotated[
    str, StringConstraints(strip_whitespace=True, min_length=1, max_length=5000)
]


class ProposalRequest(Contract):
    operation_id: UUID
    expected_fingerprint: Fingerprint | None
    title: Annotated[
        str, StringConstraints(strip_whitespace=True, min_length=1, max_length=200)
    ]
    description: DraftText
    service_code: (
        Annotated[
            str, StringConstraints(strip_whitespace=True, min_length=1, max_length=100)
        ]
        | None
    )
    severity: Severity | None
    explanation: Annotated[
        str, StringConstraints(strip_whitespace=True, min_length=1, max_length=2000)
    ]


class SupportAction(Contract):
    version: Literal[1] = 1
    report_id: UUID
    run_id: UUID | None
    status: Literal[
        "absent",
        "preparing",
        "awaiting_decision",
        "rejected",
        "approved_unconfirmed",
        "simulated_success",
        "execution_unknown",
    ]
    archived: bool
    input_stale: bool
    can_prepare: bool
    proposal: ProposedAction | None
    fingerprint: Fingerprint | None
    preparation_id: UUID | None
    pending_preparation: ProposalRequest | None
    decision: ApprovalDecision | None
    execution: ToolExecutionResult | None
    failure: ToolExecutionFailure | None
    timeline: tuple[ExecutionEvent, ...]

    @model_validator(mode="after")
    def consistent_saved_state(self) -> Self:
        proposal = self.proposal
        if self.can_prepare and (self.archived or self.run_id is None):
            raise ValueError("Invalid preparation availability")
        if proposal is None:
            if (
                self.status != "absent"
                or any(
                    value is not None
                    for value in (
                        self.fingerprint,
                        self.preparation_id,
                        self.pending_preparation,
                        self.decision,
                        self.execution,
                        self.failure,
                    )
                )
                or self.timeline
                or self.input_stale
            ):
                raise ValueError("Absent proposal cannot contain an outcome")
            return self
        if (
            self.run_id is None
            or self.preparation_id is None
            or proposal.arguments.issue_report_id != self.report_id
            or self.fingerprint != proposal.fingerprint()
        ):
            raise ValueError("Invalid proposal binding")
        if self.status == "absent" or (self.status == "preparing") != (
            self.pending_preparation is not None
        ):
            raise ValueError("Invalid preparation state")
        if self.can_prepare and (
            self.archived or self.status not in ("awaiting_decision",)
        ):
            raise ValueError("Invalid revision availability")
        events = append_events([], list(self.timeline))
        if len(events) != len(self.timeline) or any(
            event.workflow_run_id != self.run_id or event.stage != "approval"
            for event in events
        ):
            raise ValueError("Invalid approval timeline")
        if self.decision is not None and not matches(self.decision, proposal):
            raise ValueError("Decision does not bind proposal")
        if self.execution is not None and self.failure is not None:
            raise ValueError("Conflicting execution outcomes")
        for result in (self.execution, self.failure):
            if result is not None and (
                result.action_id != proposal.action_id
                or result.version != proposal.version
                or result.fingerprint != self.fingerprint
                or result.idempotency_key != proposal.idempotency_key
                or self.decision is None
                or self.decision.decision != ApprovalChoice.APPROVE
            ):
                raise ValueError("Execution does not bind approval")
        expected = (
            "preparing"
            if self.pending_preparation is not None
            else (
                "awaiting_decision"
                if self.decision is None
                else "rejected"
                if self.decision.decision == ApprovalChoice.REJECT
                else "simulated_success"
                if self.execution is not None
                else "execution_unknown"
                if self.failure is not None
                else "approved_unconfirmed"
            )
        )
        if self.status != expected or (
            self.status == "preparing" and (self.decision is not None or self.timeline)
        ):
            raise ValueError("Invalid saved outcome")
        return self
