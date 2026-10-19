"""Turn a customer report into validated, application-owned extraction data."""

import asyncio
import json
from dataclasses import dataclass, replace
from enum import StrEnum
from uuid import uuid4

from pydantic import ValidationError

from api.accounting.recording import generate
from api.extraction.clarification import ClarificationDecision, decide_clarification
from api.extraction.prompts import EXTRACTION_PROMPT, PromptSpec
from api.extraction.provider import (
    LLMProvider,
    ModelSettings,
    ProviderError,
    ProviderFailureKind,
    ProviderResult,
    ProviderUsage,
)
from api.extraction.schemas import ExtractionResult
from api.observability import trace


@dataclass(frozen=True)
class ExtractionCallRecord:
    prompt_id: str
    prompt_version: str
    model_settings: ModelSettings
    output_schema: str
    attempts: int = 0
    usage: ProviderUsage | None = None


@dataclass(frozen=True)
class ExtractionOutcome:
    result: ExtractionResult
    call: ExtractionCallRecord
    clarification: ClarificationDecision


class ExtractionFailureReason(StrEnum):
    REFUSAL = "refusal"
    EMPTY_OUTPUT = "empty_output"
    MALFORMED_JSON = "malformed_json"
    INVALID_DATA = "invalid_data"
    PROVIDER_ERROR = "provider_error"


class ExtractionError(Exception):
    def __init__(
        self,
        reason: ExtractionFailureReason,
        call: ExtractionCallRecord,
        provider_failure_kind: ProviderFailureKind | None = None,
    ) -> None:
        self.reason = reason
        self.call = call
        self.provider_failure_kind = provider_failure_kind
        super().__init__(reason.value)


@dataclass(frozen=True)
class RetryPolicy:
    max_attempts: int = 3
    timeout_seconds: float = 30.0
    base_delay_seconds: float = 0.25

    def __post_init__(self) -> None:
        if self.max_attempts < 1:
            raise ValueError("max_attempts must be at least 1")
        if self.timeout_seconds <= 0:
            raise ValueError("timeout_seconds must be positive")
        if self.base_delay_seconds < 0:
            raise ValueError("base_delay_seconds cannot be negative")


DEFAULT_RETRY_POLICY = RetryPolicy()


async def extract_issue_report(
    report: str,
    provider: LLMProvider,
    retry_policy: RetryPolicy = DEFAULT_RETRY_POLICY,
    *,
    prompt: PromptSpec = EXTRACTION_PROMPT,
) -> ExtractionOutcome:
    with trace(
        "model", component="extraction", call_id=uuid4(), error_code="invalid_output"
    ) as model_span:
        base_call = ExtractionCallRecord(
            prompt_id=prompt.id,
            prompt_version=prompt.version,
            model_settings=provider.settings,
            output_schema=ExtractionResult.__name__,
        )
        result: ProviderResult | None = None
        call = base_call
        for attempt in range(1, retry_policy.max_attempts + 1):
            call = replace(base_call, attempts=attempt)
            try:
                with trace(
                    "provider",
                    component="extraction",
                    attempt=attempt,
                    error_code="provider",
                ):
                    result = await generate(
                        provider,
                        prompt.instructions,
                        report,
                        ExtractionResult,
                        component="extraction",
                        prompt_id=prompt.id,
                        prompt_version=prompt.version,
                        attempt=attempt,
                        timeout_seconds=retry_policy.timeout_seconds,
                    )
            except TimeoutError as error:
                failure = ProviderError(
                    "Extraction call timed out", ProviderFailureKind.TIMEOUT
                )
                failure.__cause__ = error
            except ProviderError as error:
                failure = error
            else:
                break

            if (
                failure.kind
                in (ProviderFailureKind.TIMEOUT, ProviderFailureKind.TRANSIENT)
                and attempt < retry_policy.max_attempts
            ):
                await asyncio.sleep(
                    retry_policy.base_delay_seconds * 2 ** (attempt - 1)
                )
                continue
            model_span.failure_code = "provider"
            model_span.outcome = (
                "timeout" if failure.kind == ProviderFailureKind.TIMEOUT else "error"
            )
            raise ExtractionError(
                ExtractionFailureReason.PROVIDER_ERROR, call, failure.kind
            ) from failure

        assert result is not None
        call = replace(call, usage=result.usage)

        if result.refusal is not None:
            model_span.failure_code = "refusal"
            model_span.outcome = "rejected"
            raise ExtractionError(ExtractionFailureReason.REFUSAL, call)
        if result.text is None or not result.text.strip():
            raise ExtractionError(ExtractionFailureReason.EMPTY_OUTPUT, call)

        try:
            payload = json.loads(result.text)
        except json.JSONDecodeError as error:
            raise ExtractionError(
                ExtractionFailureReason.MALFORMED_JSON, call
            ) from error

        try:
            extraction = ExtractionResult.model_validate(payload)
        except ValidationError as error:
            raise ExtractionError(ExtractionFailureReason.INVALID_DATA, call) from error
        return ExtractionOutcome(extraction, call, decide_clarification(extraction))
