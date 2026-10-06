"""The RF-303 subset of the reviewed workflow state."""

from dataclasses import dataclass
from enum import StrEnum
from typing import Annotated, NotRequired, TypedDict
from uuid import UUID

from api.extraction.clarification import ClarificationDecision
from api.extraction.provider import ProviderFailureKind
from api.extraction.schemas import ExtractionResult
from api.extraction.service import ExtractionCallRecord, ExtractionFailureReason
from api.workflow.actions import ProposedAction
from api.workflow.approval import ApprovalDecision
from api.workflow.clarification import ClarificationTurn, PendingClarification
from api.workflow.execution import ToolExecutionFailure, ToolExecutionResult
from api.workflow.timeline import ExecutionEvent, append_events


class ReportStatus(StrEnum):
    NEEDS_CLARIFICATION = "needs_clarification"
    NEEDS_CONFIRMATION = "needs_confirmation"
    EXTRACTION_FAILED = "extraction_failed"
    ACTION_REJECTED = "action_rejected"
    AWAITING_EXECUTION = "awaiting_execution"
    TOOL_EXECUTION_FAILED = "tool_execution_failed"
    SIMULATED_TICKET_CREATED = "simulated_ticket_created"


@dataclass(frozen=True)
class DiagnosisDraft:
    reported_facts: tuple[str, ...]
    missing_data: tuple[str, ...]
    contradictions: tuple[str, ...]
    cause: None = None
    evidence_available: bool = False

    def __post_init__(self) -> None:
        object.__setattr__(self, "reported_facts", tuple(self.reported_facts))
        object.__setattr__(self, "missing_data", tuple(self.missing_data))
        object.__setattr__(self, "contradictions", tuple(self.contradictions))


@dataclass(frozen=True)
class SafeWorkflowFailure:
    stage: str
    reason: ExtractionFailureReason
    provider_failure_kind: ProviderFailureKind | None


@dataclass(frozen=True)
class CustomerSafeReport:
    status: ReportStatus
    message: str
    questions: tuple[str, ...] = ()
    incomplete: bool = False

    def __post_init__(self) -> None:
        object.__setattr__(self, "questions", tuple(self.questions))


class WorkflowInput(TypedDict):
    workflow_run_id: UUID
    issue_report_id: UUID


class ApprovalInput(WorkflowInput):
    proposed_action: ProposedAction


class ApprovalState(ApprovalInput):
    timeline: Annotated[list[ExecutionEvent], append_events]
    approval: NotRequired[ApprovalDecision]
    customer_update: NotRequired[CustomerSafeReport]
    tool_failure: NotRequired[ToolExecutionFailure]
    tool_execution: NotRequired[ToolExecutionResult]
    support_ticket_id: NotRequired[UUID]


class WorkflowState(WorkflowInput):
    timeline: Annotated[list[ExecutionEvent], append_events]
    extraction: NotRequired[ExtractionResult]
    extraction_call: NotRequired[ExtractionCallRecord]
    clarification: NotRequired[ClarificationDecision]
    diagnosis: NotRequired[DiagnosisDraft]
    customer_update: NotRequired[CustomerSafeReport]
    failure: NotRequired[SafeWorkflowFailure]
    clarification_turns: NotRequired[list[ClarificationTurn]]
    pending_clarification: NotRequired[PendingClarification | None]
    continued_incomplete: NotRequired[bool]
    proposed_action: NotRequired[ProposedAction]
    approval: NotRequired[ApprovalDecision]
    tool_failure: NotRequired[ToolExecutionFailure]
    tool_execution: NotRequired[ToolExecutionResult]
    support_ticket_id: NotRequired[UUID]


class WorkflowUpdate(TypedDict, total=False):
    timeline: list[ExecutionEvent]
    extraction: ExtractionResult
    extraction_call: ExtractionCallRecord
    clarification: ClarificationDecision
    diagnosis: DiagnosisDraft
    customer_update: CustomerSafeReport
    failure: SafeWorkflowFailure
    clarification_turns: list[ClarificationTurn]
    pending_clarification: PendingClarification | None
    continued_incomplete: bool
    proposed_action: ProposedAction
    approval: ApprovalDecision
    tool_failure: ToolExecutionFailure
    tool_execution: ToolExecutionResult
    support_ticket_id: UUID
