"""Timeline contracts and transition history without report content."""

from datetime import UTC, datetime, timedelta
from typing import cast
from uuid import UUID, uuid4

import pytest
from langgraph.types import Command  # pyright: ignore[reportMissingTypeStubs]
from pydantic import ValidationError

from api.extraction.provider import FakeProvider, ProviderResult
from api.extraction.schemas import Confidence, ExtractionResult, Severity
from api.extraction.service import ExtractionFailureReason
from api.workflow.checkpoints import checkpoint_serializer, workflow_config
from api.workflow.clarification import PendingClarification
from api.workflow.graph import build_workflow
from api.workflow.state import WorkflowInput, WorkflowState
from api.workflow.timeline import (
    EventMetadata,
    EventType,
    ExecutionEvent,
    append_events,
    combined_timeline,
    transition_event,
)


@pytest.fixture
def anyio_backend() -> str:
    return "asyncio"


def test_event_replay_preserves_id_timestamp_and_order() -> None:
    run_id = uuid4()
    first = transition_event(run_id, [], "intake", EventType.WORKFLOW_STARTED, "start")
    assert first[0].sequence == 1
    assert (
        transition_event(run_id, first, "intake", EventType.WORKFLOW_STARTED, "start")
        == []
    )
    replay = transition_event(run_id, [], "intake", EventType.WORKFLOW_STARTED, "start")
    assert replay[0].event_id == first[0].event_id
    replay = [
        replay[0].model_copy(
            update={"occurred_at": datetime.now(UTC) + timedelta(seconds=1)}
        )
    ]
    assert append_events(first, replay) == first
    second = transition_event(run_id, first, "intake", EventType.REPORT_READY, "0")
    assert append_events(first, second) == [*first, *second]
    assert first[0].sequence == 1  # Reducer never mutates the original list.
    serde = checkpoint_serializer()
    restored: object = serde.loads_typed(serde.dumps_typed(first[0]))
    assert isinstance(restored, ExecutionEvent)
    assert isinstance(restored.metadata, EventMetadata)
    assert restored == first[0]


@pytest.mark.parametrize("case", ["changed", "gap", "other_run", "other_stage"])
def test_reducer_rejects_changed_or_misordered_events(case: str) -> None:
    run_id = uuid4()
    first = transition_event(run_id, [], "intake", EventType.WORKFLOW_STARTED, "start")
    second = transition_event(run_id, first, "intake", EventType.REPORT_READY, "0")[0]
    if case == "changed":
        second = first[0].model_copy(
            update={"metadata": EventMetadata(incomplete=True)}
        )
    elif case == "gap":
        second = second.model_copy(update={"sequence": 3})
    elif case == "other_run":
        second = second.model_copy(update={"workflow_run_id": uuid4()})
    else:
        second = second.model_copy(update={"stage": "approval"})
    with pytest.raises(ValueError):
        append_events(first, [second])


@pytest.mark.parametrize(
    "field", ["report_text", "answers", "prompt", "arguments", "exception", "message"]
)
def test_metadata_forbids_free_text_and_unknown_fields(field: str) -> None:
    with pytest.raises(ValidationError):
        EventMetadata.model_validate({field: "PRIVATE CONTENT"})


def test_event_contracts_are_frozen_and_require_aware_timestamps() -> None:
    event = transition_event(
        uuid4(), [], "intake", EventType.WORKFLOW_STARTED, "start"
    )[0]
    with pytest.raises(ValidationError):
        event.sequence = 99
    with pytest.raises(ValidationError):
        event.metadata.incomplete = True
    with pytest.raises(ValidationError):
        ExecutionEvent.model_validate(
            {**event.model_dump(), "occurred_at": datetime(2026, 1, 1)}
        )
    with pytest.raises(ValidationError):
        transition_event(
            event.workflow_run_id,
            [event],
            "intake",
            EventType.REPORT_READY,
            "0",
            EventMetadata().model_copy(update={"attempts": 0}),
        )


def extraction(ambiguous: bool) -> ExtractionResult:
    return ExtractionResult(
        summary="PRIVATE model summary",
        service_code="invoicing",
        severity=None if ambiguous else Severity.MEDIUM,
        confidence=Confidence.HIGH,
        reported_facts=["PRIVATE customer observation"],
        missing_data=[],
        contradictions=[],
        questions=["PRIVATE question?"] if ambiguous else [],
    )


async def load(_: UUID) -> str:
    return "PRIVATE original report"


@pytest.mark.anyio
async def test_success_timeline_explains_intake_without_content() -> None:
    provider = FakeProvider(ProviderResult(text=extraction(False).model_dump_json()))
    graph = build_workflow(load, provider)
    run_id = uuid4()
    await graph.ainvoke(  
        WorkflowInput(workflow_run_id=run_id, issue_report_id=uuid4()),
        workflow_config(run_id),
    )
    snapshot = await graph.aget_state(workflow_config(run_id))
    state = cast(WorkflowState, snapshot.values)
    events = state["timeline"]
    assert [event.event_type for event in events] == [
        EventType.WORKFLOW_STARTED,
        EventType.EXTRACTION_SUCCEEDED,
        EventType.CLARIFICATION_EVALUATED,
        EventType.DIAGNOSIS_PREPARED,
        EventType.REPORT_READY,
    ]
    assert [event.sequence for event in events] == list(range(1, 6))
    assert all(event.workflow_run_id == run_id for event in events)
    assert events[1].metadata.attempts == 1
    assert "PRIVATE" not in repr(events)


@pytest.mark.anyio
async def test_poll_invalid_reply_answers_and_round_limit_preserve_history() -> None:
    provider = FakeProvider(ProviderResult(text=extraction(True).model_dump_json()))
    graph = build_workflow(load, provider)
    run_id = uuid4()
    config = workflow_config(run_id)
    await graph.ainvoke(  
        WorkflowInput(workflow_run_id=run_id, issue_report_id=uuid4()), config
    )
    initial = await graph.aget_state(config)
    initial_state = cast(WorkflowState, initial.values)
    history = initial_state["timeline"]
    assert history[-1].event_type == EventType.CLARIFICATION_REQUESTED
    for payload in [None, Command(resume={"invalid": "PRIVATE input"})]:
        await graph.ainvoke(payload, config)  
        polled = await graph.aget_state(config)
        assert polled.values["timeline"] == history
    for round_number in [1, 2]:
        current = await graph.aget_state(config)
        pending = current.values["pending_clarification"]
        assert isinstance(pending, PendingClarification)
        await graph.ainvoke(  
            Command(
                resume={
                    "pending_id": str(pending.pending_id),
                    "action": "answer",
                    "answers": ["PRIVATE answer"],
                }
            ),
            config,
        )
        snapshot = await graph.aget_state(config)
        state = cast(WorkflowState, snapshot.values)
        answered = [
            event
            for event in state["timeline"]
            if event.event_type == EventType.CLARIFICATION_ANSWERED
        ]
        assert len(answered) == round_number
        assert answered[-1].metadata.round_number == round_number
        assert state["timeline"][: len(history)] == history
        history = state["timeline"]
    assert history[-1].metadata.clarification_cause == "round_limit"
    pending = state.get("pending_clarification")
    assert pending is not None
    await graph.ainvoke(  
        Command(
            resume={
                "pending_id": str(pending.pending_id),
                "action": "continue_incomplete",
            }
        ),
        config,
    )
    final = await graph.aget_state(config)
    state = cast(WorkflowState, final.values)
    events = state["timeline"]
    assert [event.event_type for event in events[-3:]] == [
        EventType.CONTINUED_INCOMPLETE,
        EventType.DIAGNOSIS_PREPARED,
        EventType.REPORT_READY,
    ]
    assert events[-1].metadata.incomplete is True
    assert [event.sequence for event in events] == list(range(1, len(events) + 1))
    assert len({event.event_id for event in events}) == len(events)
    assert "PRIVATE" not in repr(events)


@pytest.mark.anyio
async def test_extraction_failure_records_only_typed_reason() -> None:
    graph = build_workflow(
        load, FakeProvider(ProviderResult(refusal="PRIVATE refusal"))
    )
    run_id = uuid4()
    await graph.ainvoke(  
        WorkflowInput(workflow_run_id=run_id, issue_report_id=uuid4()),
        workflow_config(run_id),
    )
    snapshot = await graph.aget_state(workflow_config(run_id))
    state = cast(WorkflowState, snapshot.values)
    events = state["timeline"]
    assert [event.event_type for event in events] == [
        EventType.WORKFLOW_STARTED,
        EventType.EXTRACTION_FAILED,
        EventType.REPORT_READY,
    ]
    assert events[1].metadata.extraction_failure is ExtractionFailureReason.REFUSAL
    assert "PRIVATE" not in repr(events)


def test_combined_view_preserves_stage_order_and_rejects_other_runs() -> None:
    run_id = uuid4()
    intake = transition_event(run_id, [], "intake", EventType.WORKFLOW_STARTED, "start")
    approval = transition_event(
        run_id, [], "approval", EventType.APPROVAL_REQUESTED, "snapshot"
    )
    # A clock adjustment must not move support approval before customer intake.
    approval = [
        approval[0].model_copy(
            update={"occurred_at": intake[0].occurred_at - timedelta(seconds=10)}
        )
    ]
    assert combined_timeline(intake, approval) == (*intake, *approval)
    assert combined_timeline(intake, []) == tuple(intake)
    with pytest.raises(ValueError, match="different runs"):
        combined_timeline(
            intake, [approval[0].model_copy(update={"workflow_run_id": uuid4()})]
        )
    with pytest.raises(ValueError, match="designated stages"):
        combined_timeline(approval, intake)
