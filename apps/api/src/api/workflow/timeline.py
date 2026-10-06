"""Ordered transition records with a closed metadata contract."""

from datetime import UTC, datetime
from enum import StrEnum
from typing import Annotated, Literal
from uuid import UUID, uuid5

from pydantic import AwareDatetime, Field

from api.extraction.clarification import ClarificationReason
from api.extraction.provider import ProviderFailureKind
from api.extraction.service import ExtractionFailureReason
from api.workflow.actions import ImmutableContract


class EventType(StrEnum):
    WORKFLOW_STARTED = "workflow_started"
    EXTRACTION_SUCCEEDED = "extraction_succeeded"
    EXTRACTION_FAILED = "extraction_failed"
    CLARIFICATION_EVALUATED = "clarification_evaluated"
    CLARIFICATION_REQUESTED = "clarification_requested"
    CLARIFICATION_ANSWERED = "clarification_answered"
    CONTINUED_INCOMPLETE = "continued_incomplete"
    DIAGNOSIS_PREPARED = "diagnosis_prepared"
    REPORT_READY = "report_ready"
    APPROVAL_REQUESTED = "approval_requested"
    ACTION_APPROVED = "action_approved"
    ACTION_REJECTED = "action_rejected"
    TOOL_SUCCEEDED = "tool_succeeded"
    TOOL_FAILED = "tool_failed"


class EventMetadata(ImmutableContract):
    # No generic dictionary or free text: callers cannot accidentally attach
    # customer content, prompts, arguments, or raw exception messages.
    round_number: Annotated[int, Field(strict=True, ge=0)] | None = None
    attempts: Annotated[int, Field(strict=True, ge=1)] | None = None
    reasons: tuple[ClarificationReason, ...] = ()
    question_count: Annotated[int, Field(strict=True, ge=0, le=2)] | None = None
    clarification_cause: (
        Literal["questions_available", "no_questions", "round_limit"] | None
    ) = None
    extraction_failure: ExtractionFailureReason | None = None
    provider_failure: ProviderFailureKind | None = None
    action_id: UUID | None = None
    action_version: Annotated[int, Field(strict=True, ge=1)] | None = None
    fingerprint: Annotated[str, Field(pattern=r"^[0-9a-f]{64}$")] | None = None
    actor_id: UUID | None = None
    support_ticket_id: UUID | None = None
    outcome: Literal["unknown", "simulated"] | None = None
    incomplete: bool | None = None


class ExecutionEvent(ImmutableContract):
    event_id: UUID
    workflow_run_id: UUID
    stage: Literal["intake", "approval"]
    sequence: Annotated[int, Field(strict=True, ge=1)]
    occurred_at: AwareDatetime
    event_type: EventType
    metadata: EventMetadata


def append_events(
    existing: list[ExecutionEvent], incoming: list[ExecutionEvent]
) -> list[ExecutionEvent]:
    """LangGraph reducer: append in order; replay cannot replace saved events."""
    result = [ExecutionEvent.model_validate(event) for event in existing]
    by_id = {event.event_id: event for event in result}
    for raw in incoming:
        event = ExecutionEvent.model_validate(raw)
        previous = by_id.get(event.event_id)
        if previous is not None:
            if previous.model_dump(exclude={"occurred_at"}) != event.model_dump(
                exclude={"occurred_at"}
            ):
                raise ValueError("A timeline event cannot be changed")
            continue
        if event.sequence != len(result) + 1:
            raise ValueError("Timeline sequence must be contiguous")
        if result and (
            event.workflow_run_id != result[0].workflow_run_id
            or event.stage != result[0].stage
        ):
            raise ValueError("Timeline events must belong to one run and stage")
        result.append(event)
        by_id[event.event_id] = event
    return result


def transition_event(
    run_id: UUID,
    existing: list[ExecutionEvent],
    stage: Literal["intake", "approval"],
    event_type: EventType,
    key: str,
    metadata: EventMetadata | None = None,
) -> list[ExecutionEvent]:
    """Return a delta; a committed transition keeps its original ID and time."""
    metadata = EventMetadata.model_validate(metadata or EventMetadata())
    event_id = uuid5(run_id, f"resolveflow:{stage}:{event_type}:{key}")
    for previous in existing:
        if previous.event_id == event_id:
            if previous.event_type != event_type or previous.metadata != metadata:
                raise ValueError("A timeline event cannot be changed")
            return []
    return [
        ExecutionEvent(
            event_id=event_id,
            workflow_run_id=run_id,
            stage=stage,
            sequence=len(existing) + 1,
            occurred_at=datetime.now(UTC),
            event_type=event_type,
            metadata=metadata,
        )
    ]


def combined_timeline(
    intake: list[ExecutionEvent], approval: list[ExecutionEvent]
) -> tuple[ExecutionEvent, ...]:
    """Read-only view of the run's separate intake and approval checkpoint streams.

    Sequence is local to each stage. The product flow places intake before
    approval; clocks are not used to reorder causally dependent transitions.
    """
    first = append_events([], intake)
    second = append_events([], approval)
    if any(event.stage != "intake" for event in first) or any(
        event.stage != "approval" for event in second
    ):
        raise ValueError("Timeline streams must use their designated stages")
    if first and second and first[0].workflow_run_id != second[0].workflow_run_id:
        raise ValueError("Cannot combine timelines from different runs")
    return (*first, *second)
