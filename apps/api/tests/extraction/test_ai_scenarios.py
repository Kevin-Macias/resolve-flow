"""Customer-report scenarios run through the extraction boundary offline."""

import asyncio
import json
from dataclasses import dataclass

import pytest
from pydantic import BaseModel

from api.extraction.provider import (
    FakeProvider,
    ModelSettings,
    ProviderResult,
)
from api.extraction.schemas import Confidence, Severity
from api.extraction.service import (
    ExtractionError,
    ExtractionFailureReason,
    RetryPolicy,
    extract_issue_report,
)


@pytest.fixture
def anyio_backend() -> str:
    return "asyncio"


@dataclass(frozen=True)
class ReportScenario:
    report: str
    summary: str
    service_code: str | None
    severity: Severity | None
    confidence: Confidence
    reported_facts: tuple[str, ...]
    missing_data: tuple[str, ...]
    contradictions: tuple[str, ...]
    questions: tuple[str, ...]

    def provider_output(self) -> str:
        return json.dumps(
            {
                "summary": self.summary,
                "service_code": self.service_code,
                "severity": self.severity,
                "confidence": self.confidence,
                "reported_facts": self.reported_facts,
                "missing_data": self.missing_data,
                "contradictions": self.contradictions,
                "questions": self.questions,
            }
        )


@pytest.mark.anyio
@pytest.mark.parametrize(
    "scenario",
    [
        ReportScenario(
            report="Our team cannot submit invoices, and we have no workaround.",
            summary="Team cannot submit invoices",
            service_code="invoicing",
            severity=Severity.MEDIUM,
            confidence=Confidence.HIGH,
            reported_facts=("Customer says their team cannot submit invoices",),
            missing_data=("When the failure began",),
            contradictions=(),
            questions=("When did invoice submission stop working?",),
        ),
        ReportScenario(
            report="Payments sometimes remain pending after checkout.",
            summary="Payments sometimes remain pending",
            service_code="payments",
            severity=None,
            confidence=Confidence.LOW,
            reported_facts=("Customer reports some payments remain pending",),
            missing_data=("Affected payment count", "Final payment outcome"),
            contradictions=(),
            questions=("How many payments are affected?",),
        ),
        ReportScenario(
            report="Something broke yesterday, maybe exports.",
            summary="Customer reports an unclear problem since yesterday",
            service_code=None,
            severity=None,
            confidence=Confidence.LOW,
            reported_facts=("Customer reports a problem since yesterday",),
            missing_data=("Affected feature", "Observed error", "Impact"),
            contradictions=(),
            questions=("Which action fails, and what happens when you try it?",),
        ),
    ],
    ids=["clear-impact", "ambiguous-impact", "low-confidence"],
)
async def test_report_scenarios_preserve_tentative_extraction(
    scenario: ReportScenario,
) -> None:
    provider = FakeProvider(ProviderResult(text=scenario.provider_output()))

    outcome = await extract_issue_report(scenario.report, provider)

    assert outcome.result.summary == scenario.summary
    assert outcome.result.service_code == scenario.service_code
    assert outcome.result.severity is scenario.severity
    assert outcome.result.confidence is scenario.confidence
    assert outcome.result.reported_facts == list(scenario.reported_facts)
    assert outcome.result.missing_data == list(scenario.missing_data)
    assert outcome.result.contradictions == list(scenario.contradictions)
    assert outcome.result.questions == list(scenario.questions)
    assert outcome.call.attempts == 1
    assert len(provider.calls) == 1
    assert provider.calls[0][1] == scenario.report


@pytest.mark.anyio
@pytest.mark.parametrize(
    ("result", "reason"),
    [
        (ProviderResult(text="{bad json"), ExtractionFailureReason.MALFORMED_JSON),
        (ProviderResult(refusal="Cannot process"), ExtractionFailureReason.REFUSAL),
    ],
    ids=["malformed", "refusal"],
)
async def test_unusable_ai_outputs_stop_without_retry(
    result: ProviderResult, reason: ExtractionFailureReason
) -> None:
    provider = FakeProvider(result)

    with pytest.raises(ExtractionError) as error:
        await extract_issue_report("A customer issue", provider)

    assert error.value.reason is reason
    assert error.value.call.attempts == 1
    assert len(provider.calls) == 1


@pytest.mark.anyio
async def test_hanging_ai_call_times_out_offline() -> None:
    class HangingProvider:
        settings = ModelSettings(model="fake-hanging")
        calls = 0

        async def generate(
            self,
            instructions: str,
            input_text: str,
            output_schema: type[BaseModel] | None = None,
        ) -> ProviderResult:
            self.calls += 1
            await asyncio.Event().wait()
            return ProviderResult(text="{}")

    provider = HangingProvider()
    with pytest.raises(ExtractionError) as error:
        await extract_issue_report(
            "A customer issue",
            provider,
            RetryPolicy(max_attempts=1, timeout_seconds=0.01, base_delay_seconds=0),
        )

    assert error.value.reason is ExtractionFailureReason.PROVIDER_ERROR
    assert error.value.provider_failure_kind == "timeout"
    assert error.value.call.attempts == 1
    assert provider.calls == 1
