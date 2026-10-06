"""Exercise graph routing and application results without live model calls."""

from uuid import UUID, uuid4

import pytest
from pydantic import BaseModel

from api.extraction.provider import (
    FakeProvider,
    ModelSettings,
    ProviderError,
    ProviderFailureKind,
    ProviderResult,
)
from api.extraction.schemas import Confidence, ExtractionResult, Severity
from api.extraction.service import ExtractionFailureReason, RetryPolicy
from api.workflow.graph import build_workflow
from api.workflow.state import ReportStatus, WorkflowInput


@pytest.fixture
def anyio_backend() -> str:
    return "asyncio"


def extraction(*, ambiguous: bool = False, questions: bool = True) -> ExtractionResult:
    return ExtractionResult(
        summary="Customer reports blocked invoice submission",
        service_code="invoicing",
        severity=None if ambiguous else Severity.MEDIUM,
        confidence=Confidence.HIGH,
        reported_facts=["Customer says their team cannot submit invoices"],
        missing_data=["Affected count"] if ambiguous else [],
        contradictions=[],
        questions=["How many users are affected?"] if ambiguous and questions else [],
    )


@pytest.mark.anyio
async def test_transition_nodes_preserve_facts_and_report_gaps() -> None:
    ambiguous, questions, status = False, True, ReportStatus.NEEDS_CONFIRMATION
    proposal = extraction(ambiguous=ambiguous, questions=questions)
    provider = FakeProvider(ProviderResult(text=proposal.model_dump_json()))
    report_id = uuid4()
    loaded: list[UUID] = []

    async def load_report(identifier: UUID) -> str:
        loaded.append(identifier)
        return "Our team cannot submit invoices."

    graph = build_workflow(load_report, provider)
    inputs = WorkflowInput(workflow_run_id=uuid4(), issue_report_id=report_id)
    steps = [
        step
        async for step in graph.astream(  
            inputs, {"configurable": {"thread_id": uuid4().hex}}, stream_mode="updates"
        )
    ]  

    assert [next(iter(step)) for step in steps] == [
        "start",
        "classify",
        "evaluate",
        "diagnose",
        "report",
    ]
    diagnosis = steps[3]["diagnose"]["diagnosis"]
    update = steps[4]["report"]["customer_update"]
    assert diagnosis.reported_facts == tuple(proposal.reported_facts)
    assert diagnosis.missing_data == tuple(proposal.missing_data)
    assert diagnosis.cause is None
    assert diagnosis.evidence_available is False
    assert update.status is status
    assert update.questions == tuple(proposal.questions)
    assert loaded == [report_id]
    assert len(provider.calls) == 1


@pytest.mark.anyio
@pytest.mark.parametrize(
    ("result", "reason"),
    [
        (ProviderResult(text="{bad"), ExtractionFailureReason.MALFORMED_JSON),
        (ProviderResult(refusal="sensitive SDK text"), ExtractionFailureReason.REFUSAL),
    ],
)
async def test_failed_extraction_skips_assessment_and_sanitizes_report(
    result: ProviderResult, reason: ExtractionFailureReason
) -> None:
    async def load_report(identifier: UUID) -> str:
        return "Private report text"

    provider = FakeProvider(result)
    graph = build_workflow(load_report, provider)
    state = await graph.ainvoke(  
        WorkflowInput(workflow_run_id=uuid4(), issue_report_id=uuid4()),
        {"configurable": {"thread_id": uuid4().hex}},
    )
    assert "diagnosis" not in state
    assert "clarification" not in state
    assert state["failure"].reason is reason
    assert state["failure"].stage == "classify"
    assert state["extraction_call"].attempts == 1
    assert state["customer_update"].status is ReportStatus.EXTRACTION_FAILED
    assert "Private" not in state["customer_update"].message
    assert "sensitive" not in state["customer_update"].message
    assert len(provider.calls) == 1


@pytest.mark.anyio
async def test_provider_retry_budget_is_not_multiplied_by_graph() -> None:
    async def load_report(identifier: UUID) -> str:
        return "Our team cannot submit invoices."

    class FailingProvider:
        settings = ModelSettings(model="fake")
        calls = 0

        async def generate(
            self,
            instructions: str,
            input_text: str,
            output_schema: type[BaseModel] | None = None,
        ) -> ProviderResult:
            self.calls += 1
            raise ProviderError("sensitive details", ProviderFailureKind.TRANSIENT)

    provider = FailingProvider()
    graph = build_workflow(
        load_report, provider, RetryPolicy(max_attempts=3, base_delay_seconds=0)
    )
    state = await graph.ainvoke(  
        WorkflowInput(workflow_run_id=uuid4(), issue_report_id=uuid4()),
        {"configurable": {"thread_id": uuid4().hex}},
    )
    assert provider.calls == 3
    assert state["failure"].provider_failure_kind is ProviderFailureKind.TRANSIENT
    assert state["extraction_call"].attempts == 3
    assert "diagnosis" not in state


@pytest.mark.anyio
async def test_loader_denial_stops_before_model_call() -> None:
    async def deny(identifier: UUID) -> str:
        raise PermissionError("Access denied")

    provider = FakeProvider(ProviderResult(text=extraction().model_dump_json()))
    graph = build_workflow(deny, provider)
    with pytest.raises(PermissionError):
        await graph.ainvoke(  
            WorkflowInput(workflow_run_id=uuid4(), issue_report_id=uuid4()),
            {"configurable": {"thread_id": uuid4().hex}},
        )
    assert provider.calls == []
