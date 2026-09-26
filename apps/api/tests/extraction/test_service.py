"""Extraction outcomes are deterministic without a live model."""

import asyncio
import json

import pytest
from pydantic import BaseModel

from api.extraction.clarification import ClarificationReason
from api.extraction.prompts import EXTRACTION_PROMPT
from api.extraction.provider import (
    FakeProvider,
    ModelSettings,
    ProviderError,
    ProviderFailureKind,
    ProviderResult,
    ProviderUsage,
)
from api.extraction.schemas import Confidence, ExtractionResult
from api.extraction.service import (
    ExtractionError,
    ExtractionFailureReason,
    RetryPolicy,
    extract_issue_report,
)


@pytest.fixture
def anyio_backend() -> str:
    return "asyncio"


def valid_payload() -> dict[str, object]:
    return {
        "summary": "Payments sometimes remain pending",
        "service_code": None,
        "severity": None,
        "confidence": "low",
        "reported_facts": ["Customer reports pending payments"],
        "missing_data": ["Number of affected payments"],
        "contradictions": [],
        "questions": ["How many payments are affected?"],
    }


@pytest.mark.anyio
async def test_valid_extraction_uses_schema_and_returns_validated_result() -> None:
    provider = FakeProvider(
        ProviderResult(
            text=json.dumps(valid_payload()), usage=ProviderUsage(12, 23, 35)
        )
    )

    outcome = await extract_issue_report("Payments remain pending", provider)

    assert isinstance(outcome.result, ExtractionResult)
    assert outcome.result.confidence is Confidence.LOW
    assert outcome.result.severity is None
    assert outcome.call.prompt_id == EXTRACTION_PROMPT.id
    assert outcome.call.prompt_version == EXTRACTION_PROMPT.version
    assert outcome.call.model_settings == ModelSettings(model="fake")
    assert outcome.call.output_schema == "ExtractionResult"
    assert outcome.call.attempts == 1
    assert outcome.call.usage == ProviderUsage(12, 23, 35)
    assert outcome.clarification.needs_clarification
    assert ClarificationReason.UNKNOWN_SEVERITY in outcome.clarification.reasons
    assert outcome.clarification.questions == ("How many payments are affected?",)
    assert provider.calls[0][0] == EXTRACTION_PROMPT.instructions
    assert provider.calls[0][1:] == ("Payments remain pending", ExtractionResult)


@pytest.mark.anyio
@pytest.mark.parametrize(
    ("provider_result", "reason"),
    [
        (ProviderResult(text="{"), ExtractionFailureReason.MALFORMED_JSON),
        (ProviderResult(text="  "), ExtractionFailureReason.EMPTY_OUTPUT),
        (ProviderResult(), ExtractionFailureReason.EMPTY_OUTPUT),
        (ProviderResult(refusal="Cannot help"), ExtractionFailureReason.REFUSAL),
    ],
)
async def test_unusable_provider_results_have_typed_reasons(
    provider_result: ProviderResult, reason: ExtractionFailureReason
) -> None:
    provider = FakeProvider(provider_result)
    with pytest.raises(ExtractionError) as error:
        await extract_issue_report("report", provider)

    assert error.value.reason is reason
    assert error.value.call.attempts == 1
    assert error.value.call.prompt_id == EXTRACTION_PROMPT.id
    assert error.value.call.model_settings.model == "fake"
    assert len(provider.calls) == 1


@pytest.mark.anyio
async def test_missing_required_field_is_invalid_data() -> None:
    payload = valid_payload()
    del payload["summary"]
    provider = FakeProvider(ProviderResult(text=json.dumps(payload)))

    with pytest.raises(ExtractionError) as error:
        await extract_issue_report("report", provider)

    assert error.value.reason is ExtractionFailureReason.INVALID_DATA
    assert len(provider.calls) == 1


@pytest.mark.anyio
async def test_provider_error_is_mapped_without_exposing_sdk_details() -> None:
    class FailingProvider:
        settings = ModelSettings(model="failed-model", max_output_tokens=400)

        async def generate(
            self,
            instructions: str,
            input_text: str,
            output_schema: type[BaseModel] | None = None,
        ) -> ProviderResult:
            raise ProviderError("private SDK details")

    with pytest.raises(ExtractionError) as error:
        await extract_issue_report("report", FailingProvider())

    assert error.value.reason is ExtractionFailureReason.PROVIDER_ERROR
    assert error.value.provider_failure_kind is ProviderFailureKind.PERMANENT
    assert error.value.call.attempts == 1
    assert error.value.call.model_settings == ModelSettings(
        model="failed-model", max_output_tokens=400
    )
    assert "private SDK details" not in str(error.value)


@pytest.mark.anyio
async def test_transient_error_retries_then_succeeds() -> None:
    class RecoveringProvider:
        settings = ModelSettings(model="test-model")
        calls = 0

        async def generate(
            self,
            instructions: str,
            input_text: str,
            output_schema: type[BaseModel] | None = None,
        ) -> ProviderResult:
            self.calls += 1
            if self.calls == 1:
                raise ProviderError("temporary", ProviderFailureKind.TRANSIENT)
            return ProviderResult(text=json.dumps(valid_payload()))

    provider = RecoveringProvider()
    outcome = await extract_issue_report(
        "report", provider, RetryPolicy(base_delay_seconds=0)
    )

    assert provider.calls == 2
    assert outcome.call.attempts == 2


@pytest.mark.anyio
async def test_transient_error_stops_at_max_attempts() -> None:
    class FailingProvider:
        settings = ModelSettings(model="test-model")
        calls = 0

        async def generate(
            self,
            instructions: str,
            input_text: str,
            output_schema: type[BaseModel] | None = None,
        ) -> ProviderResult:
            self.calls += 1
            raise ProviderError("temporary", ProviderFailureKind.TRANSIENT)

    provider = FailingProvider()
    with pytest.raises(ExtractionError) as error:
        await extract_issue_report(
            "report", provider, RetryPolicy(base_delay_seconds=0)
        )

    assert provider.calls == 3
    assert error.value.call.attempts == 3
    assert error.value.provider_failure_kind is ProviderFailureKind.TRANSIENT


@pytest.mark.anyio
async def test_timeout_is_bounded_and_classified() -> None:
    class HangingProvider:
        settings = ModelSettings(model="test-model")
        calls = 0

        async def generate(
            self,
            instructions: str,
            input_text: str,
            output_schema: type[BaseModel] | None = None,
        ) -> ProviderResult:
            self.calls += 1
            await asyncio.Event().wait()
            return ProviderResult(text=json.dumps(valid_payload()))

    provider = HangingProvider()
    with pytest.raises(ExtractionError) as error:
        await extract_issue_report(
            "report",
            provider,
            RetryPolicy(max_attempts=2, timeout_seconds=0.01, base_delay_seconds=0),
        )

    assert provider.calls == 2
    assert error.value.call.attempts == 2
    assert error.value.provider_failure_kind is ProviderFailureKind.TIMEOUT


@pytest.mark.parametrize(
    "policy",
    [
        {"max_attempts": 0},
        {"timeout_seconds": 0},
        {"base_delay_seconds": -1},
    ],
)
def test_invalid_retry_policy_is_rejected(policy: dict[str, int]) -> None:
    with pytest.raises(ValueError):
        RetryPolicy(**policy)
