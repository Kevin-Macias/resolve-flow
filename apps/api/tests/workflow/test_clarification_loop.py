"""Offline checks for the approved human clarification policy."""

import json
from dataclasses import dataclass
from typing import cast
from uuid import UUID, uuid4

import pytest
from langchain_core.runnables import RunnableConfig
from langgraph.graph.state import (  # pyright: ignore[reportMissingTypeStubs]
    CompiledStateGraph,
)
from langgraph.types import Command  # pyright: ignore[reportMissingTypeStubs]
from pydantic import BaseModel

from api.extraction.provider import ModelSettings, ProviderResult
from api.extraction.schemas import Confidence, ExtractionResult, Severity
from api.workflow.clarification import PendingClarification
from api.workflow.graph import build_workflow
from api.workflow.state import ReportStatus, WorkflowInput, WorkflowState


@pytest.fixture
def anyio_backend() -> str:
    return "asyncio"


def proposal(*, gap: bool = True, questions: bool = True) -> ProviderResult:
    result = ExtractionResult(
        summary="Customer reports pending payments",
        service_code="payments",
        severity=None if gap else Severity.LOW,
        confidence=Confidence.HIGH,
        reported_facts=["Customer reports pending payments"],
        missing_data=["Affected count"] if gap else [],
        contradictions=["Reported outcomes conflict"] if gap else [],
        questions=(
            ["How many payments?", "What final outcome?"] if gap and questions else []
        ),
    )
    return ProviderResult(text=result.model_dump_json())


class ScriptedProvider:
    settings = ModelSettings(model="fake-scripted")

    def __init__(self, outputs: list[ProviderResult]) -> None:
        self.outputs = outputs
        self.inputs: list[str] = []

    async def generate(
        self,
        instructions: str,
        input_text: str,
        output_schema: type[BaseModel] | None = None,
    ) -> ProviderResult:
        self.inputs.append(input_text)
        return self.outputs[len(self.inputs) - 1]


@dataclass
class Run:
    graph: CompiledStateGraph[WorkflowState, None, WorkflowInput, WorkflowState]
    provider: ScriptedProvider
    inputs: WorkflowInput
    config: RunnableConfig

    async def start(self) -> WorkflowState:
        result = await self.graph.ainvoke(self.inputs, self.config)
        return cast(WorkflowState, result)

    async def reply(self, payload: object) -> WorkflowState:
        result = await self.graph.ainvoke(Command(resume=payload), self.config)
        return cast(WorkflowState, result)

    async def poll(self) -> WorkflowState:
        result = await self.graph.ainvoke(None, self.config)
        return cast(WorkflowState, result)


def make_run(outputs: list[ProviderResult]) -> Run:
    async def load(identifier: UUID) -> str:
        return "Payments remain pending."

    provider = ScriptedProvider(outputs)
    run_id = uuid4()
    return Run(
        build_workflow(load, provider),
        provider,
        WorkflowInput(workflow_run_id=run_id, issue_report_id=uuid4()),
        {"configurable": {"thread_id": str(run_id)}},
    )


def pending(state: WorkflowState) -> PendingClarification:
    value = state.get("pending_clarification")
    assert value is not None
    return value


def answer_payload(state: WorkflowState) -> dict[str, object]:
    return {
        "pending_id": str(pending(state).pending_id),
        "action": "answer",
        "answers": ["Two payments", "Still pending"],
    }


def continue_payload(state: WorkflowState) -> dict[str, object]:
    return {
        "pending_id": str(pending(state).pending_id),
        "action": "continue_incomplete",
    }


@pytest.mark.anyio
async def test_answer_reextracts_once_and_preserves_original_and_turn() -> None:
    run = make_run([proposal(), proposal(gap=False)])
    state = await run.start()
    assert pending(state).round_number == 1
    saved_pending = pending(state)
    state = await run.poll()
    assert pending(state) == saved_pending
    assert len(run.provider.inputs) == 1
    assert "diagnosis" not in state
    update = state.get("customer_update")
    assert update is not None and update.status is ReportStatus.NEEDS_CLARIFICATION
    state = await run.reply(answer_payload(state))
    assert state.get("pending_clarification") is None
    assert len(run.provider.inputs) == 2
    turns = state.get("clarification_turns", ())
    assert len(turns) == 1
    assert turns[0].round_number == 1
    assert turns[0].answers == ("Two payments", "Still pending")
    input_data = json.loads(run.provider.inputs[1])
    assert input_data["original_report"] == "Payments remain pending."
    assert input_data["clarification_turns"][0]["questions"] == [
        "How many payments?",
        "What final outcome?",
    ]
    update = state.get("customer_update")
    assert update is not None
    assert update.status is ReportStatus.NEEDS_CONFIRMATION


@pytest.mark.anyio
async def test_two_rounds_then_explicit_incomplete_continuation() -> None:
    run = make_run([proposal(), proposal(), proposal()])
    state = await run.start()
    first_reply = answer_payload(state)
    state = await run.reply(first_reply)
    assert pending(state).round_number == 2
    state = await run.reply(first_reply)
    assert pending(state).round_number == 2
    assert len(run.provider.inputs) == 2
    state = await run.reply(answer_payload(state))
    assert pending(state).round_number is None
    assert pending(state).cause == "round_limit"
    assert pending(state).questions == ()
    assert len(run.provider.inputs) == 3
    assert "diagnosis" not in state
    state = await run.reply(answer_payload(state))
    assert pending(state).cause == "round_limit"
    assert len(run.provider.inputs) == 3
    assert [turn.round_number for turn in state.get("clarification_turns", ())] == [
        1,
        2,
    ]
    state = await run.reply(continue_payload(state))
    assert len(run.provider.inputs) == 3
    assert state.get("continued_incomplete") is True
    diagnosis = state.get("diagnosis")
    assert diagnosis is not None
    assert diagnosis.missing_data == ("Affected count",)
    assert diagnosis.contradictions == ("Reported outcomes conflict",)
    update = state.get("customer_update")
    assert update is not None and update.incomplete
    assert update.status is ReportStatus.NEEDS_CONFIRMATION


@pytest.mark.anyio
@pytest.mark.parametrize("questions", [True, False])
async def test_can_continue_without_fabricated_answers(questions: bool) -> None:
    run = make_run([proposal(questions=questions)])
    state = await run.start()
    assert pending(state).cause == (
        "questions_available" if questions else "no_questions"
    )
    state = await run.reply(continue_payload(state))
    assert state.get("continued_incomplete") is True
    assert state.get("clarification_turns", ()) == ()
    assert len(run.provider.inputs) == 1


@pytest.mark.anyio
@pytest.mark.parametrize(
    "bad", ["partial", "blank", "stale", "extra", "false", "mixed"]
)
async def test_invalid_reply_keeps_questions_and_does_not_advance(bad: str) -> None:
    run = make_run([proposal(), proposal(gap=False)])
    state = await run.start()
    original_pending = pending(state)
    payload = answer_payload(state)
    if bad == "partial":
        payload["answers"] = ["Two payments"]
    elif bad == "blank":
        payload["answers"] = ["   ", "Still pending"]
    elif bad == "stale":
        payload["pending_id"] = str(uuid4())
    elif bad == "extra":
        payload["extra"] = "ignored?"
    elif bad == "mixed":
        payload["action"] = "continue_incomplete"
    invalid: object = False if bad == "false" else payload
    state = await run.reply(invalid)
    assert pending(state) == original_pending
    assert state.get("clarification_turns", ()) == ()
    assert len(run.provider.inputs) == 1
    assert "diagnosis" not in state
    state = await run.reply(answer_payload(state))
    assert len(state.get("clarification_turns", ())) == 1
    assert len(run.provider.inputs) == 2


@pytest.mark.anyio
async def test_answers_not_accepted_when_no_question_exists() -> None:
    run = make_run([proposal(questions=False)])
    state = await run.start()
    state = await run.reply(answer_payload(state))
    assert pending(state).mode == "continue_only"
    assert len(run.provider.inputs) == 1
    state = await run.reply(continue_payload(state))
    assert state.get("continued_incomplete") is True


@pytest.mark.anyio
async def test_access_is_checked_again_on_resume_before_accepting_answers() -> None:
    allowed = True

    async def load(identifier: UUID) -> str:
        if not allowed:
            raise PermissionError("Access denied")
        return "Payments remain pending."

    provider = ScriptedProvider([proposal(), proposal(gap=False)])
    run_id = uuid4()
    run = Run(
        build_workflow(load, provider),
        provider,
        WorkflowInput(workflow_run_id=run_id, issue_report_id=uuid4()),
        {"configurable": {"thread_id": str(run_id)}},
    )
    state = await run.start()
    allowed = False
    with pytest.raises(PermissionError):
        await run.reply(answer_payload(state))
    snapshot = await run.graph.aget_state(run.config)
    assert "clarification_turns" not in snapshot.values
    assert len(provider.inputs) == 1


@pytest.mark.anyio
async def test_failure_after_answer_preserves_history_without_diagnosis() -> None:
    run = make_run([proposal(), ProviderResult(refusal="Private refusal details")])
    state = await run.start()
    state = await run.reply(answer_payload(state))
    assert len(state.get("clarification_turns", ())) == 1
    assert state.get("pending_clarification") is None
    assert "diagnosis" not in state
    update = state.get("customer_update")
    assert update is not None and update.status is ReportStatus.EXTRACTION_FAILED
    assert "Private" not in update.message
    assert len(run.provider.inputs) == 2
